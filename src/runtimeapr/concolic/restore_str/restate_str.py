from copy import deepcopy
from types import FunctionType
from typing import Callable, Tuple
from ..fuzzing import Fuzzer
from ..restate import StateReproducer
from ..restore_str.util_ast.runner import FunctionGenerator
from runtimeapr.loop.repairutils import (
    prune_default_global_var,
    prune_default_local_var,
)


class StrStateReprodcer(StateReproducer):
    def __init__(
        self,
        fuzzer: Fuzzer,
        fn: FunctionType,
        args_names,
        buggy_local_vars: dict[str, object],
        buggy_global_vars: dict[str, object],
        args: list[object],
        kwargs: dict[str, object],
        global_vars: dict[str, object],
        def_use_chain: dict[str, list[str]],
    ):
        super().__init__(
            self,
            fn,
            args_names,
            buggy_local_vars,
            buggy_global_vars,
            args,
            kwargs,
            global_vars,
            def_use_chain,
        )
        self.fuzzer = fuzzer

    def reproduce(self) -> dict[str, object]:
        """
        reproduce the state of all string global variables
        """

        if len(self.global_vars) == 1 and (
            varname := list(self.global_vars.keys())[0] and isinstance(self.global_vars[varname], str)
        ):
            return {varname: self.reproduce_str()}

        raise Exception('Unimplemented Yet')
        MAX_TRIALS = 10
        new_globals = dict()
        for varname, value in self.global_vars:
            if isinstance(value, str):
                new_globals[varname] = self.reproduce_var(varname)
        return new_globals

    def reproduce_all(self):
        """
        Restore a string global variable before the function call.

        May raise an exception if none is found.
        """
        MAX_TRIALS = 10

        print('Reproducing the state...')
        new_args, new_kwargs, new_globals = deepcopy([self.args, self.kwargs, self.global_vars])
        str_global_gens = dict()
        int_global_vars = dict()
        for varname, value in self.global_vars.items():
            if isinstance(value, str):
                str_global_gens[varname] = FunctionGenerator(self.fuzzer.examples, varname)
            elif isinstance(value, int):
                # to do something with int values
                int_global_vars[varname] = value
        for trial in range(MAX_TRIALS):
            print(f'\r{int(trial/MAX_TRIALS * 100)}% ', end='')
            for varname, value in self.global_vars:
                if isinstance(value, str):
                    state = str_global_gens[varname].get_expected_state()
                    if state is not None:
                        new_globals.update({varname: state})
                elif isinstance(value, int):
                    ### TODO: Do something with ints
                    pass
                else:
                    raise TypeError(f'Global variable type {type(value)} for variable {varname} not suported yet.')
            reproduced_local_vars, reproduced_global_vars = self.run(new_args, new_kwargs, new_globals)
            local_diffs, global_diffs = self.is_vars_same(
                prune_default_local_var(self.fn, reproduced_local_vars),
                prune_default_global_var(self.fn, reproduced_global_vars),
            )
            if len(local_diffs) == 0 and len(global_diffs) == 0:
                print(f'\r100%\nStates reproduced in trial {trial}')
                break
            for func_gen in str_global_gens.values():
                func_gen.improve(new_globals, reproduced_local_vars, reproduced_global_vars)

        else:
            raise Exception('No solution found')
        return new_globals[varname]

    def reproduce_str(self, varname):
        """
        Restore a string global variable before the function call.

        May raise an exception if none is found.
        """
        MAX_TRIALS = 10

        print('Reproducing the state...')
        new_args, new_kwargs, new_globals = deepcopy([self.args, self.kwargs, self.global_vars])
        fungen = FunctionGenerator(self.fuzzer.examples, varname)

        for trial in range(MAX_TRIALS):
            print(f'\r{int(trial/MAX_TRIALS * 100)}% ', end='')
            state = fungen.get_expected_state()
            if state is not None:
                new_globals.update({varname: state})
            else:
                print("State is None")

            reproduced_local_vars, reproduced_global_vars = self.run(new_args, new_kwargs, new_globals)
            local_diffs, global_diffs = self.is_vars_same(
                prune_default_local_var(self.fn, reproduced_local_vars),
                prune_default_global_var(self.fn, reproduced_global_vars),
            )
            if len(local_diffs) == 0 and len(global_diffs) == 0:
                print(f'\r100%\nStates reproduced in trial {trial}')
                break
            fungen.improve(new_globals, reproduced_local_vars, reproduced_global_vars)

        return new_globals[varname]
