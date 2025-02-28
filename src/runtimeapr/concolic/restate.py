import ast
from enum import Enum
from functools import partial
import random
import struct


from runtimeapr.concolic import FunctionGenerator
from runtimeapr.concolic.fuzzing import Fuzzer

from .defusegraph import DefUseGraph
from ..loop.repairutils import (
    PickledObject,
    SetObject,
    compare_object,
    is_default_global,
    is_default_local,
    pickle_object,
    prune_default_global_var,
    prune_default_local_var,
)

from typing import Dict, List, Set, Tuple
from types import FunctionType, ModuleType
import inspect
from copy import deepcopy, copy
import torch  # type: ignore
import torch.nn as nn  # type: ignore


class StateReproducer:
    def __init__(
        self,
        fn: FunctionType,
        args_names: ast.arguments,
        buggy_local_vars: Dict[str, object],
        buggy_global_vars: Dict[str, object],
        #  args:List[object],kwargs:Dict[str,object],def_use_chain:List[DefUseGraph.Node]):
        args: List[object],
        kwargs: Dict[str, object],
        global_vars: Dict[str, object],
        def_use_chain: Dict[str, List[str]],
        exception: Exception,
    ):
        self.fn = fn
        self.args_names = args_names
        self.buggy_local_vars = prune_default_local_var(self.fn, buggy_local_vars)
        self.buggy_global_vars = prune_default_global_var(self.fn, buggy_global_vars)
        self.args = args
        self.arg_names = list(inspect.signature(self.fn).parameters.keys())
        self.kwargs = kwargs
        self.global_vars = prune_default_global_var(self.fn, global_vars)
        self.def_use_chains = def_use_chain
        self.exception = exception
        self.solution = None
        self.examples: List[Tuple[Dict[str, object], Dict[str, object], Dict[str, object]]] = []
        """
            [ (previous_globals, after_locals, after_globals) ]
        """

        self.diffs: List[tuple] = []
        """
            [
                (args, kwargs, globals, local_diffs, global_diffs)
            ]
        """

        if torch.cuda.is_available():
            self.device = torch.device('cuda')
            print('Using GPU')
        else:
            self.device = torch.device('cpu')
            print('Using CPU')

    def run(
        self,
        new_args: List[object],
        new_kwargs: Dict[str, object],
        new_globals: Dict[str, object],
        verbose=True,
    ):
        # Prune default variables
        next_globals = prune_default_global_var(self.fn, new_globals)
        args, kwargs, globals = deepcopy([new_args, new_kwargs, next_globals])
        for name, obj in globals.items():
            self.fn.__globals__[name] = obj

        try:
            global is_concolic_execution
            is_concolic_execution = True
            result = self.fn(*args, **kwargs)
        except Exception as _exc:
            if not (type(_exc) is type(self.exception) and _exc.args == self.exception.args):
                return None, None
            if verbose:
                print(f'Exception raised: {type(_exc)}: {_exc}')
            innerframes = inspect.getinnerframes(_exc.__traceback__)
            innerframes.reverse()
            inner_info: inspect.FrameInfo = innerframes[0]
            cur_index = 0

            while not inner_info.filename.endswith('.py') or (
                inner_info.function.startswith('<') and inner_info.function.endswith('>')
            ):
                cur_index += 1
                inner_info = innerframes[cur_index]

            return inner_info.frame.f_locals, inner_info.frame.f_globals

        return None, None

    def is_vars_same(self, local_vars: Dict[str, object], global_vars: Dict[str, object], verbose=True):
        is_same = True
        local_diffs: Dict[str, Tuple[object, object]] = dict()
        global_diffs: Dict[str, Tuple[object, object]] = dict()

        if verbose:
            print('Compare local variables...')
        for name, obj in local_vars.items():
            if is_default_local(self.fn, name, obj):
                continue

            if name not in self.buggy_local_vars:
                is_same = False
                if verbose:
                    print(f'New local var {name}: {obj}')
                local_diffs[name] = (obj, None)
                continue

            _obj = pickle_object(self.fn, name, obj)
            base_obj = pickle_object(self.fn, name, self.buggy_local_vars[name])
            if _obj is not None:
                _is_same = compare_object(_obj, base_obj)
                if not _is_same:
                    local_diffs[name] = (obj, self.buggy_local_vars[name])
                if is_same:
                    is_same = _is_same
            else:
                is_same = False
            # if not is_same:
            #     break

        if verbose:
            print('Compare global variables...')
        for name, obj in global_vars.items():
            if is_default_global(self.fn, name, obj):
                continue

            if name not in self.buggy_global_vars:
                # is_same=False
                if verbose:
                    print(f'New global var {name}: {obj}')
                global_diffs[name] = (obj, None)
                continue

            _obj = pickle_object(self.fn, name, obj, is_global=True)
            base_obj = pickle_object(self.fn, name, self.buggy_global_vars[name], is_global=True)
            if _obj is not None:
                _is_same = compare_object(_obj, base_obj)
                if not _is_same:
                    global_diffs[name] = (obj, self.buggy_global_vars[name])
                if is_same:
                    is_same = _is_same
            else:
                is_same = False
            # if not is_same:
            #     break
        if verbose:
            if is_same:
                print(f'Same result in restate!')
            else:
                print(f'Different result!')

        return local_diffs, global_diffs

    def find_candidate_inputs(
        self, local_vars: Dict[str, Tuple[object, object]], global_vars: Dict[str, Tuple[object, object]], verbose=True
    ):
        pos_args = []
        for arg in self.args_names.posonlyargs:
            pos_args.append(arg.arg)
        for arg in self.args_names.args:
            pos_args.append(arg.arg)
        var_arg = self.args_names.vararg.arg if self.args_names.vararg else []
        kwonly_args = []
        for arg in self.args_names.kwonlyargs:
            kwonly_args.append(arg.arg)
        kw_arg = self.args_names.kwarg.arg if self.args_names.kwarg else []

        cand_args: Set[str] = set()
        cand_kwargs: Set[str] = set()
        cand_globals: Set[str] = set()
        if len(local_vars) != 0:
            if verbose:
                print('Mutate local variables...')
            for name, (obj, base_obj) in local_vars.items():
                if base_obj is None:
                    if verbose:
                        print(f'New local var {name}: {obj}')
                    # TODO new local var found
                else:
                    if verbose:
                        print(f'Mutate local var {name}: {base_obj} -> {obj}')
                    # Find the corresponding argument, kwargs, globals
                    cand_args = set(pos_args)
                    cand_kwargs = set(kw_arg)
                    cand_globals = set(self.global_vars.keys())
                    # for use in self.def_use_chains[name]:
                    #     if use.split('.')[0] in pos_args and not is_default_local(self.fn,use.split('.')[0],self.args[self.arg_names.index(use.split('.')[0])]):
                    #         cand_args.add(use)
                    #     elif use.split('.')[0] in kwonly_args and not is_default_local(self.fn,use.split('.')[0],self.kwargs[use.split('.')[0]]):
                    #         cand_kwargs.add(use)
                    #     elif use.split('.')[0] in self.global_vars:
                    #         cand_globals.add(use)

        if len(global_vars) != 0:
            if verbose:
                print('Mutate global variables...')
            for name, (obj, base_obj) in global_vars.items():
                if base_obj is None:
                    if verbose:
                        print(f'New global var {name}: {obj}')
                    # TODO new global var found
                else:
                    if verbose:
                        try:  # obj can be some non-utf-8-representable characters
                            print(f'Mutate global var {name}: {base_obj} -> {obj}')
                        except:
                            pass
                    # Find the corresponding argument, kwargs, globals
                    cand_args = set(pos_args)
                    cand_kwargs = set(kw_arg)
                    cand_globals = set(self.global_vars.keys())
                    # for use in self.def_use_chains[name]:
                    #     if use.split('.')[0] in pos_args and not is_default_local(self.fn,use.split('.')[0],self.args[self.arg_names.index(use.split('.')[0])]):
                    #         cand_args.add(use)
                    #     elif use.split('.')[0] in kwonly_args and not is_default_local(self.fn,use.split('.')[0],self.kwargs[use.split('.')[0]]):
                    #         cand_kwargs.add(use)
                    #     elif use.split('.')[0] in self.global_vars:
                    #         cand_globals.add(use)
        if verbose:
            if len(cand_args) != 0:
                print(f'Candidate args: {cand_args}')
            if len(cand_kwargs) != 0:
                print(f'Candidate kwargs: {cand_kwargs}')
            if len(cand_globals) != 0:
                print(f'Candidate globals: {cand_globals}')

        return cand_args, cand_kwargs, cand_globals

    def mutate_object(self, obj: object, name: str, candidate_name: List[str], mutated_values=dict(), verbose=True):
        if name in candidate_name:
            if (
                isinstance(obj, FunctionType)
                or isinstance(obj, ModuleType)
                or inspect.isclass(obj)
                or isinstance(obj, partial)
            ):
                mutated_values[name] = obj
                return obj

            if verbose:
                print(f'Mutate {name}')
            if isinstance(obj, Enum):
                # For Enum object, select a random value
                candidates = []
                for elem in obj.__class__:
                    candidates.append(elem)
                index = random.randint(0, len(candidates) - 1)
                mutated_values[name] = candidates[index]
                return mutated_values[name]

            elif isinstance(obj, bool):
                # For boolean object, negate the value
                mutated_values[name] = not obj
                return mutated_values[name]

            elif isinstance(obj, int):
                # For integer object, flip a random bit
                MAX_INT_BIT = 16
                bit = random.randint(0, MAX_INT_BIT - 1)
                mutated_values[name] = obj ^ (1 << bit)
                return mutated_values[name]

            elif isinstance(obj, str):
                # For str object, erase/insert/mutate a random character
                new_str = copy(obj)
                MAX_STR_LEN = len(new_str)

                # Erase random characters
                while len(new_str) != 0 and random.randint(0, 1) == 1:
                    index = random.randint(0, len(new_str) - 1)
                    new_str = new_str[:index] + new_str[index + 1 :]

                # Insert random characters
                while len(new_str) <= MAX_STR_LEN and random.randint(0, 1) == 1:
                    index = random.randint(0, len(new_str))
                    new_char = chr(random.randint(32, 255))
                    while '\\' in new_char or '"' in new_char or ';' in new_char:
                        new_char = chr(random.randint(32, 255))
                    new_str = new_str[:index] + new_char + new_str[index:]

                if new_str != obj:
                    mutated_values[name] = new_str
                    return new_str

                if len(new_str) == 0:
                    new_char = chr(random.randint(32, 255))
                    while '\\' in new_char or '"' in new_char or ';' in new_char:
                        new_char = chr(random.randint(32, 255))
                    mutated_values[name] = new_char
                    return mutated_values[name]
                else:
                    # Still the same string, mutate a random character
                    index = random.randint(0, len(new_str) - 1)
                    new_char = chr(random.randint(32, 255))
                    while '\\' in new_char or '"' in new_char or ';' in new_char:
                        new_char = chr(random.randint(32, 255))
                    mutated_values[name] = new_str[:index] + new_char + new_str[index + 1 :]
                    return mutated_values[name]

            elif isinstance(obj, bytes):
                # For bytes object, erase/insert/mutate a random character
                new_byte = obj
                MAX_STR_LEN = len(new_byte)

                # Erase random characters
                while len(new_byte) != 0 and random.randint(0, 1) == 1:
                    index = random.randint(0, len(new_byte) - 1)
                    new_byte = new_byte[:index] + new_byte[index + 1 :]

                # Insert random characters
                while len(new_byte) <= MAX_STR_LEN and random.randint(0, 1) == 1:
                    index = random.randint(0, len(new_byte))
                    new_byte = new_byte[:index] + bytes(random.randint(0, 255)) + new_byte[index:]

                if new_byte != obj:
                    mutated_values[name] = new_byte
                    return new_byte

                if len(new_byte) == 0:
                    mutated_values[name] = bytes(random.randint(0, 255))
                    return mutated_values[name]
                else:
                    # Still the same string, mutate a random character
                    index = random.randint(0, len(new_byte) - 1)
                    mutated_values[name] = new_byte[:index] + bytes(random.randint(0, 255)) + new_byte[index + 1 :]
                    return mutated_values[name]

            elif isinstance(obj, float):
                # For float object, flip a random bitwise and bytewise
                binary = struct.pack('d', obj)
                index = random.randint(0, 15)
                bytewise = index // 8
                bitwise = index % 8

                new_binary = binary[:bytewise] + bytes([binary[bytewise] ^ (1 << bitwise)]) + binary[bytewise + 1 :]
                mutated_values[name] = struct.unpack('d', new_binary)[0]
                return mutated_values[name]

        else:
            continue_mutate = False
            for cand in candidate_name:
                if cand.startswith(name + '.'):
                    continue_mutate = True
                    break

            if continue_mutate and hasattr(obj, '__dict__'):
                # Custom classes
                names = list(getattr(obj, '__dict__').keys())
                for name in names.copy():
                    if is_default_global(self.fn, name, getattr(obj, '__dict__')[name]):
                        names.remove(name)

                if len(names) == 0:
                    return obj
                index = random.randint(0, len(names) - 1)
                key_name = names[index]

                if name + '.' + key_name in candidate_name:
                    do_remove = random.randint(0, 2)
                else:
                    do_remove = 0

                if do_remove == 1:
                    delattr(obj, name)
                elif do_remove == 2:
                    setattr(obj, name, None)
                else:
                    new_field = self.mutate_object(
                        getattr(obj, '__dict__')[key_name],
                        name + '.' + key_name,
                        candidate_name,
                    )
                    setattr(obj, name, new_field)
                return obj

        return obj

    def torch_predict(self, target_x: Dict[str, object]):
        # self.diffs = list(filter(lambda diff: diff[3], self.diffs))
        if len(self.diffs) < 2:
            print("Not enough tests for the model")
            return target_x
        x, y = [], []
        input_keys = []
        output_keys = []

        def is_mutable_obj(obj: object):
            return (
                isinstance(obj, int)
                or isinstance(obj, float)
                # or isinstance(obj, str)
                or isinstance(obj, bytes)
                or isinstance(obj, Enum)
                or isinstance(obj, list)
                or isinstance(obj, set)
                or isinstance(obj, dict)
                or isinstance(obj, tuple)
                or hasattr(obj, '__dict__')
            )

        # Store args and vars keys first for the order and padding
        for diff in self.diffs[1:]:
            args, kwargs, globals, mutated_objects, local_vars, global_vars = diff
            for name, obj in mutated_objects.items():
                if name not in input_keys and is_mutable_obj(obj) and not isinstance(obj, str):
                    input_keys.append(name)
            for name, obj in local_vars.items():
                if name not in output_keys:
                    output_keys.append(name)
            for name, obj in global_vars.items():
                if name not in output_keys:
                    output_keys.append(name)

        def get_original_value(obj: object, cur_name: str, target_name: str):
            if cur_name == target_name:
                return obj
            elif target_name.startswith(cur_name):
                if hasattr(obj, '__dict__'):
                    for name, field in getattr(obj, '__dict__').items():
                        if target_name.startswith(cur_name + '.' + name):
                            return get_original_value(field, cur_name + '.' + name, target_name)
            return None

        # Create x and y
        # Now we assume different state is only one``
        # We ignore first element because it uses original inputs
        y_types = []
        for diff in self.diffs[1:]:
            args, kwargs, globals, mutated_objects, local_vars, global_vars = diff
            y_values = []
            # y is args, kwargs, globals that we want to predict
            for name in input_keys:
                if name in mutated_objects:
                    y_orig_value = mutated_objects[name]
                else:
                    root_name = name.split('.')[0]
                    if root_name in kwargs.keys():
                        y_orig_value = get_original_value(kwargs[root_name], root_name, name)
                    elif root_name in globals.keys():
                        y_orig_value = get_original_value(globals[root_name], root_name, name)
                    else:
                        # args
                        y_orig_value = get_original_value(args[self.arg_names.index(root_name)], root_name, name)

                if isinstance(y_orig_value, str):
                    # Convert string to unicode number
                    unicode_values: List[int] = []
                    unicode_values.extend(ord(c) for c in y_orig_value)
                    y_orig_value = unicode_values
                if is_mutable_obj(y_orig_value):
                    y_values.append(y_orig_value)
                    y_types.append(type(y_orig_value))

            y.append(y_values)

            # x is current states
            x_values = []
            for name in output_keys:
                if name in local_vars:
                    x_value = local_vars[name]
                elif name in global_vars:
                    x_value = global_vars[name]
                # If the variable is not exist, use buggy one
                elif name in self.buggy_local_vars:
                    x_value = self.buggy_local_vars[name]
                elif name in self.buggy_global_vars:
                    x_value = self.buggy_global_vars[name]

                if is_mutable_obj(x_value):
                    if isinstance(x_value, str):
                        # Convert string to unicode number
                        unicode_values = []
                        unicode_values.extend(ord(c) for c in x_value)
                        x_value = unicode_values
                    x_values.append(x_value)
            x.append(x_values)

        temp_x = dict()
        for name, obj in target_x.items():
            if name in output_keys:
                if is_mutable_obj(obj):
                    if isinstance(obj, str):
                        # Convert string to unicode number
                        unicode_values = []
                        unicode_values.extend(ord(c) for c in obj)
                        new_obj = unicode_values
                    else:
                        new_obj = obj
                    temp_x[output_keys.index(name)] = new_obj
        x_keys = sorted(list(temp_x.keys()))
        t_x = []
        for i in x_keys:
            t_x.append(temp_x[i])

        # with open('data.json','w') as f:
        #     import json
        #     json.dump({'x':x,'y':y,'target_x':t_x},f,indent=4)

        # Create model
        y_tensor = torch.tensor(y, dtype=torch.float64, device=self.device)
        x_tensor = torch.tensor(x, dtype=torch.float64, device=self.device)
        diff = y_tensor - x_tensor
        mask = diff == diff[0]
        recognized = {}
        for index in range(len(diff[0])):
            if mask[:, index].all():
                print("Pattern recognised for", input_keys[index])
                y_value = t_x[index] + diff[0][index].item()
                if isinstance(y[0][i], int):
                    y_value = round(y_value)
                recognized[input_keys[index]] = y_value

        quotient = y_tensor / x_tensor
        mask_quot = quotient == quotient[0]
        for index in range(len(quotient[0])):
            if input_keys[index] not in recognized and mask_quot[:, index].all():
                print("Pattern recognised for", input_keys[index])
                y_value = t_x[index] * quotient[0][index].item()
                if isinstance(y[0][i], int):
                    y_value = round(y_value)
                recognized[input_keys[index]] = y_value

        if len(recognized) == len(t_x):
            print(f'Recognized all: {recognized} from {t_x}')
            return recognized

        if diff.nelement() and (diff == diff[0]).all():  # torch.cat([a[:,1].unsqueeze(1), a[:,2].unsqueeze(1)], dim=1)
            print("Pattern recognised")
            target_x_tensor = torch.tensor(t_x, dtype=torch.float64, device=self.device)
            target_y = list((target_x_tensor + diff[0]).numpy(force=True))
            for i, y_value in enumerate(target_y):
                if isinstance(y[0][i], int):
                    target_y[i] = round(y_value)

            predicted: Dict[str, object] = dict()
            for key, _y in zip(input_keys, target_y):
                predicted[key] = _y

            print(f'Predicted: {predicted} from {t_x}')
            return predicted

        # This is the model. We now assumed the input and output is number.
        # TODO: Find and implememnt the model for string
        class Model(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.model = nn.Sequential(
                    nn.Linear(len(x[0]), 128, dtype=torch.float64),
                    nn.ReLU(),
                    nn.Linear(128, 64, dtype=torch.float64),
                    nn.ReLU(),
                    nn.Linear(64, len(y[0]), dtype=torch.float64),
                )

            def forward(self, x):
                return self.model(x)

        model = Model().to(self.device)
        learning_rate = 1e-4
        epochs = 100
        loss = nn.MSELoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

        print('Training the model...')
        model.train()
        for t in range(epochs):
            for batch, (x_v, y_v) in enumerate(zip(x_tensor, y_tensor)):
                output = model(x_v)
                l = loss(output, y_v)
                optimizer.zero_grad()
                l.backward()
                optimizer.step()

            if t % 50 == 49:
                print(f'Epoch {t+1} Batch {batch+1} Loss {l.item()}')

        # Predict target args, kwargs, globals
        print('Predicting target args, kwargs, globals...')
        model.eval()
        with torch.no_grad():
            target_x_tensor = torch.tensor(t_x, dtype=torch.float64, device=self.device)
            target_y_tensor: torch.Tensor = model(target_x_tensor)
            target_y: list = target_y_tensor.cpu().numpy().tolist()

        for i, y_value in enumerate(target_y.copy()):
            if isinstance(y[0][i], int):
                target_y[i] = round(y_value)

        predicted: Dict[str, object] = dict()
        for key, _y in zip(input_keys, target_y):
            predicted[key] = _y

        print(f'Predicted: {predicted} from {t_x}')

        return predicted
        # Try with predicted y
        new_args, new_kwargs, new_globals = deepcopy([self.args, self.kwargs, self.global_vars])
        for name, obj in predicted.items():
            if name in self.arg_names:
                index = self.arg_names.index(name)
                new_args[index] = obj
            elif name in new_kwargs:
                new_kwargs[name] = obj
            elif name in new_globals:
                new_globals[name] = obj
        reproduced_local_vars, reproduced_global_vars = self.run(new_args, new_kwargs, new_globals)
        if reproduced_local_vars is None:
            pass
        local_diffs, global_diffs = self.is_vars_same(
            prune_default_local_var(self.fn, reproduced_local_vars),
            prune_default_global_var(self.fn, reproduced_global_vars),
        )
        if len(local_diffs) == 0 and len(global_diffs) == 0:
            print(f'States reproduced by model')
            return predicted
        else:
            # If different states, train with new state
            print('Different states, train again...')
            # x is current states
            x_values = []
            for name in output_keys:
                if name in reproduced_local_vars:
                    x_value = reproduced_local_vars[name]
                elif name in reproduced_global_vars:
                    x_value = reproduced_global_vars[name]
                # If the variable is not exist, use buggy one
                elif name in self.buggy_local_vars:
                    x_value = self.buggy_local_vars[name]
                elif name in self.buggy_global_vars:
                    x_value = self.buggy_global_vars[name]

                if is_mutable_obj(x_value):
                    if isinstance(x_value, str):
                        # Convert string to unicode number
                        unicode_values = []
                        unicode_values.extend(ord(c) for c in x_value)
                        x_value = unicode_values
                    x_values.append(x_value)

            y_values = []
            # y is args, kwargs, globals that we want to predict
            for name in input_keys:
                if name in predicted:
                    y_orig_value = predicted[name]
                else:
                    root_name = name.split('.')[0]
                    if root_name in kwargs.keys():
                        y_orig_value = get_original_value(kwargs[root_name], root_name, name)
                    elif root_name in globals.keys():
                        y_orig_value = get_original_value(globals[root_name], root_name, name)
                    else:
                        # args
                        y_orig_value = get_original_value(args[self.arg_names.index(root_name)], root_name, name)

                if isinstance(y_orig_value, str):
                    # Convert string to unicode number
                    unicode_values = []
                    unicode_values.extend(ord(c) for c in y_orig_value)
                    y_orig_value = unicode_values
                if is_mutable_obj(y_orig_value):
                    y_values.append(y_orig_value)
                    y_types.append(type(y_orig_value))

            new_x = torch.tensor(x_values, dtype=torch.float64, device=self.device)
            new_y = torch.tensor(y_values, dtype=torch.float64, device=self.device)
            model.train()
            for t in range(epochs):
                output = model(new_x)
                l = loss(output, new_y)
                optimizer.zero_grad()
                l.backward()
                optimizer.step()

                if t % 50 == 49:
                    print(f'Epoch {t+1} Loss {l.item()}')

    def generate_args(
        self, verbose=False, ignore_first=False
    ) -> List[Tuple[Dict[str, object], Dict[str, object], Dict[str, object]]]:
        MAX_TRIALS = 500
        new_args, new_kwargs, new_globals = deepcopy([self.args, self.kwargs, self.global_vars])
        new_args_only, new_kwargs_only, new_globals_only = dict(), dict(), dict()
        mutated_objects = dict()
        examples = []
        if not verbose:
            print()
        with open('states.log', 'w') as f:
            for trial in range(1, MAX_TRIALS):
                if verbose:
                    print(f'Trial {trial}')
                else:
                    progress = int((trial + 1) / MAX_TRIALS * 10)
                    print("\033[F\rGenerating args: [" + "#" * progress + " " * (10 - progress) + "]")

                prev_args, prev_kwargs, prev_globals = deepcopy([new_args, new_kwargs, new_globals])
                new_args, new_kwargs, new_globals = deepcopy([new_args, new_kwargs, new_globals])
                reproduced_local_vars, reproduced_global_vars = self.run(prev_args, prev_kwargs, prev_globals, verbose)
                if reproduced_local_vars is None:
                    if verbose:
                        print(f'Exception not raised, skip!')
                    copied_args, copied_kwargs, copied_globals = deepcopy([self.args, self.kwargs, self.global_vars])
                    new_args_only, new_kwargs_only, new_globals_only = (
                        dict(),
                        dict(),
                        dict(),
                    )
                    mutated_objects = dict()
                    # Mutate arguments
                    for cand_arg in cand_args:
                        arg_name = cand_arg.split('.')[0]
                        if arg_name in self.arg_names:
                            index = self.arg_names.index(arg_name)
                            new_args[index] = self.mutate_object(
                                copied_args[index], arg_name, cand_args, mutated_objects, verbose
                            )
                            new_args_only[index] = new_args[index]
                    # Mutate kwargs
                    for cand_kwarg in cand_kwargs:
                        kwarg_name = cand_kwarg.split('.')[0]
                        if kwarg_name in new_kwargs:
                            new_kwargs[kwarg_name] = self.mutate_object(
                                copied_kwargs[kwarg_name],
                                kwarg_name,
                                cand_kwargs,
                                mutated_objects,
                                verbose,
                            )
                            new_kwargs_only[kwarg_name] = new_kwargs[kwarg_name]
                    # Mutate globals
                    for cand_global in cand_globals:
                        global_name = cand_global.split('.')[0]
                        if global_name in new_globals:
                            new_globals[global_name] = self.mutate_object(
                                copied_globals[global_name],
                                global_name,
                                cand_globals,
                                mutated_objects,
                                verbose,
                            )
                            new_globals_only[global_name] = new_globals[global_name]

                    continue

                cleaned_reproduced_local_vars = prune_default_local_var(self.fn, reproduced_local_vars)
                cleaned_reproduced_global_vars = prune_default_global_var(self.fn, reproduced_global_vars)
                local_diffs, global_diffs = self.is_vars_same(
                    cleaned_reproduced_local_vars,
                    cleaned_reproduced_global_vars,
                    verbose,
                )
                if len(local_diffs) == 0 and len(global_diffs) == 0:
                    print(f'States reproduced in trial {trial}')
                    self.solution = (cleaned_reproduced_local_vars, cleaned_reproduced_global_vars)
                    return examples

                cur_local_values = dict()
                for name, local in local_diffs.items():
                    cur_local_values[name] = local[0]
                cur_global_values = dict()
                for name, local in global_diffs.items():
                    cur_global_values[name] = local[0]
                examples.append(
                    (
                        prune_default_global_var(self.fn, prev_globals),
                        prune_default_local_var(self.fn, reproduced_local_vars),
                        prune_default_global_var(self.fn, reproduced_global_vars),
                    )
                )
                if not ignore_first:
                    self.diffs.append(
                        (
                            new_args,
                            prune_default_local_var(self.fn, new_kwargs),
                            prune_default_global_var(self.fn, new_globals),
                            mutated_objects,
                            cur_local_values,
                            cur_global_values,
                        )
                    )
                else:
                    ignore_first = False
                print(f'Trial: {trial}', file=f)
                print(f'Args: {new_args}', file=f)
                print(f'Kwargs: {new_kwargs}', file=f)
                print(f'Globals: {new_globals}', file=f)
                print(f'Local diffs: {cur_local_values}', file=f)
                print(f'Global diffs: {cur_global_values}', file=f)

                cand_args, cand_kwargs, cand_globals = self.find_candidate_inputs(local_diffs, global_diffs, verbose)

                new_args_only, new_kwargs_only, new_globals_only = (
                    dict(),
                    dict(),
                    dict(),
                )
                mutated_objects = dict()
                # Mutate arguments
                for cand_arg in cand_args:
                    arg_name = cand_arg.split('.')[0]
                    if arg_name in self.arg_names:
                        index = self.arg_names.index(arg_name)
                        new_args[index] = self.mutate_object(
                            new_args[index], arg_name, cand_args, mutated_objects, verbose
                        )
                        new_args_only[cand_arg] = new_args[index]
                # Mutate kwargs
                for cand_kwarg in cand_kwargs:
                    kwarg_name = cand_kwarg.split('.')[0]
                    if kwarg_name in new_kwargs:
                        new_kwargs[kwarg_name] = self.mutate_object(
                            new_kwargs[kwarg_name],
                            kwarg_name,
                            cand_kwargs,
                            mutated_objects,
                            verbose,
                        )
                        new_kwargs_only[cand_kwarg] = new_kwargs[kwarg_name]
                # Mutate globals
                for cand_global in cand_globals:
                    global_name = cand_global.split('.')[0]
                    if global_name in new_globals:
                        new_globals[global_name] = self.mutate_object(
                            new_globals[global_name],
                            global_name,
                            cand_globals,
                            mutated_objects,
                            verbose,
                        )
                        new_globals_only[cand_global] = new_globals[global_name]

                print(f'Candidate args: {cand_args}', file=f)
                print(f'Candidate kwargs: {cand_kwargs}', file=f)
                print(f'Candidate globals: {cand_globals}', file=f)
                print('-----------------------------', file=f)

        print(f'States collected!')
        return examples

    def reproduce_int(self) -> Dict[str, object]:
        buggy_vars = deepcopy(self.buggy_global_vars)
        buggy_vars.update(self.buggy_local_vars)
        return self.torch_predict(buggy_vars)

    def improve(
        self,
        str_states,
        fun_gens: Dict[str, FunctionGenerator],
        reproduced_int,
        *,
        reproduced_local_vars=None,
        reproduced_global_vars=None,
        local_diffs=None,
        global_diffs=None,
    ):
        examples = self.generate_args(ignore_first=True)
        for varname, fun in fun_gens.items():
            fun.improve(
                str_states[varname],
                examples,
                reproduced_local_vars,
                reproduced_global_vars,
            )

    def reproduce(self) -> Dict[str, object]:
        print()
        examples = self.generate_args()
        if self.solution is not None:
            self.solution[1].update(self.solution[0])
            return self.solution[1]
        MAX_TRIALS = 100
        fun_gens: Dict[str, FunctionGenerator] = dict()
        for varname, value in self.buggy_global_vars.items():
            if isinstance(value, str):
                fun_gens[varname] = FunctionGenerator(varname, examples, self.buggy_local_vars, self.buggy_global_vars)

        str_states = {}

        for trial in range(1, MAX_TRIALS + 1):
            new_args, new_kwargs, new_globals = deepcopy((self.args, self.kwargs, self.global_vars))
            for varname, fun_gen in fun_gens.items():
                state = fun_gen.get_expected_state(debug=True)
                str_states[varname] = state
                if state is not None:
                    new_globals[varname] = state
            reproduced_int = self.reproduce_int()
            for varname, value in reproduced_int.items():
                if varname in self.arg_names:
                    new_args[self.arg_names.index(varname)] = value
                elif varname in self.kwargs:
                    new_kwargs[varname] = value
                else:
                    if not isinstance(value, str):
                        new_globals[varname] = value

            reproduced_local_vars, reproduced_global_vars = self.run(new_args, new_kwargs, new_globals, verbose=True)
            if reproduced_local_vars is None:
                self.improve(str_states, fun_gens, reproduced_int)
            local_diffs, global_diffs = self.is_vars_same(
                prune_default_local_var(self.fn, reproduced_local_vars),
                prune_default_global_var(self.fn, reproduced_global_vars),
                verbose=False,
            )
            if len(local_diffs) == 0 and len(global_diffs) == 0:
                print(f'States reproduced after {trial} trial(s)')
                dict_args = dict(zip(self.arg_names, new_args))
                return {**new_globals, **dict_args, **new_kwargs}
            print(f"Different output local: {local_diffs}, global: {global_diffs}")
            self.improve(
                str_states,
                fun_gens,
                reproduced_int,
                reproduced_local_vars=reproduced_local_vars,
                reproduced_global_vars=reproduced_global_vars,
                local_diffs=local_diffs,
                global_diffs=global_diffs,
            )
        raise TimeoutError
