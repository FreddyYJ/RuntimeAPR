from copy import deepcopy
import subprocess
from .lisp_generator import lisp_from_examples
from .lisp_interpret import function_from_string
from .ast_types import get_type
from ...fuzzing import Fuzzer
import os
from typing import Optional, Tuple, Union, Dict, List
import random as rd
import re

rd.seed(57)


class FunctionGenerator:
    ### TODO: check in the body of the function if there are hardcoded strings/integers and add them as a possible constants to make it faster

    def __init__(
        self,
        buggy_var: str,
        examples: List[Tuple[Dict[str, object], Dict[str, object], Dict[str, object]]],
        buggy_locals,
        buggy_globals,
        fuzzer: Fuzzer,
        # args,
        # kwargs,
        # global_vars,
        # local_diffs,
        # global_diffs,
        # examples: List[Tuple[List[Union[str, int, bool]], Union[str, int, bool]]],
    ):
        self.fuzzer = fuzzer
        self.buggy_var = buggy_var
        self.buggy_locals = buggy_locals
        self.buggy_globals = buggy_globals

        # the order of the dict keys should not be changed as the dict will not be modified
        self.examples: List[Tuple[Dict[Union[str, int, bool], Union[str, int, bool]], Union[str, int, bool]]] = list(
            map(
                lambda ex: (
                    {**ex[2], **ex[1]},
                    ex[0][buggy_var],
                ),
                examples,
            )
        )
        self.examples = list(
            map(
                lambda ex: (dict(filter(lambda x: type(x[1]) in (int, str, bool), ex[0].items())), ex[1]), self.examples
            )
        )
        # Duet cannot read it so ignore escaped caracters
        pattern = r'\\[ntrabfuvx]|[\[\(\)\]\'"]'
        self.examples = list(
            filter(
                lambda ex: not any(re.search(pattern, repr(k)[1:-1]) for k in ex[0].values() if type(k) == str),
                self.examples,
            )
        )
        self.arg_order = list(self.examples[0][0].keys())
        """
        [ (outputs, buggy_variable_input) ]
        """

        self.path_to_duet = '/'.join(__file__.split('/')[:-1]) + '/../duet/'
        self.additional_examples: List[Tuple[List[Union[str, int, bool]], Union[str, int, bool]]] = []
        self.timeout = 15
        self.max_examples = 100
        self.inTypes = list(map(get_type, self.examples[0][0].values()))

    def prune_heuristic(self):
        return rd.sample(self.examples, self.max_examples)
        ### TODO: get len global and local diff
        order = sorted(
            range(len(self.global_diff)),
            key=lambda k: len(self.local_diff[k]) + len(self.global_diff[k]),
        )
        return [self.fuzzer.examples[k] for k in order[: self.max_examples]]

    def example_subset(self):
        """
        extact a subset of possibly interesting examples to synthesize a function
        """
        return self.prune_heuristic() + self.additional_examples

    def improve(self, bad_in_state=None, good_in_state=None, good_out_state=None):
        if bad_in_state is None:
            self.timeout += 1
        else:
            # TODO: someting along the line of self.additional_examples.append((good_in_state, good_out_state))
            ...
        if self.max_examples > self.fuzzer.examples:
            # TODO: Do more fuzzing I guess and remember examples
            ...
        if self.max_examples > 10000:
            self.max_examples = 100
        else:
            self.max_examples = int(1.3 * self.max_examples)

    def get_file_name(self) -> str:
        return self.path_to_duet + '_spec_to_synth.sl'

    def generate_specification(self, file: str):
        """
        @param file: the file to write the specification.

        Writes the function specification in @file.
        """
        example_sample = self.example_subset()
        with open(file, 'w') as fd:
            normalized_specification = lisp_from_examples((self.inTypes, "String", example_sample))
            print(normalized_specification, file=fd)

    def synthesize(self, file: str, timeout: int, debug=False) -> Optional[str]:
        """
        Call the duet synthesizer.
        @param file: the file containing the specification
        @param timeout: the timeout in sec

        returns a function of the form (define-fun f (<(_arg_i inType_i)>) outType (<body>))
        """

        try:
            result = subprocess.run(
                [self.path_to_duet + 'main.native', file],
                stderr=subprocess.PIPE,
                universal_newlines=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            if debug:
                print("\033[91;1;4mTimeout reached\033[0m, longer duration expected")
            return None
        except Exception as e:
            raise e
        if "err" in result.stderr:
            print("\033[91mAn unexpected error occured:\033[0m", result.stderr)
            exit(3)
        # the output is in stderr
        return result.stderr.split('\n')[1]

    def get_expected_state(self, debug=False):
        """
        returns the expected input according to the current policy and examples
        """
        if debug:
            print('Searching an initial state')
        filename = self.get_file_name()
        self.generate_specification(filename)
        if debug:
            print('The specification has been written at', filename)

        function_string = self.synthesize(filename, self.timeout, debug=debug)
        if debug:
            print(
                'The program has been synthesized. The outputed program is',
                function_string,
            )
        if not function_string:
            return None
        function = function_from_string(function_string)
        args = {}
        for varname in self.arg_order:
            if varname in self.buggy_locals:
                if debug:
                    print("local:", varname, self.buggy_locals[varname])
                args[varname] = self.buggy_locals[varname]
            else:
                if debug:
                    print("global:", varname, self.buggy_globals[varname])
                args[varname] = self.buggy_globals[varname]

        out = function(*(args[varname] for varname in self.examples[0][0]))

        if debug:
            print('The function has been parsed:\n', function)
            print('Expected faulty input:', out)
        else:
            for file in os.listdir(self.path_to_duet):
                if file.startswith(filename.split("/")[-1]):
                    os.remove(file)

        return out
