from typing import Tuple, Union
from .ast_types import get_type
from typing import Dict, List


def pretty_in(inType: List[str], x: Tuple[int, Union[int, str, bool]]) -> str:
    index, object = x
    if inType[index] == 'String':
        new_object = object.replace('\\', '\\\\')
        return f'"{new_object}"'
    return str(object).lower()


def pretty_out(outType: str, object: Union[int, str, bool]) -> str:
    if outType == 'String':
        new_object = object.replace('\\', '\\\\')
        return f'"{new_object}"'
    return str(object).lower()


def lisp_from_examples(
    spec: Tuple[
        List[str],
        str,
        List[Tuple[Dict[str, Union[str, int, bool]], Union[str, int, bool]]],
    ],
    additional_int: List[int] = [],
    additional_str: List[str] = [],
) -> str:
    """
    Generate a string respecting the SysGus Language Specification.

    @param spec: the specification. Composed of the input types, the output type and the examples.
    @param additional_(int|str): some additional constant values to add to the specification.
    """

    # Make sure all examples have the same type
    inType, outType, examples = spec

    body = (
        """(set-logic SLIA)
(synth-fun f ("""
        + ' '.join([f'(_arg_{index} {curr_type})' for index, curr_type in enumerate(inType)])
        + f""") {outType}
((Start {outType} (nt{outType}))
 (ntString String (
    """
        + ' '.join([f'_arg_{index}' for index, curr_type in enumerate(inType) if curr_type == 'String'])
        + """
	"" " " """
        + ' '.join(str(new_str) for new_str in additional_str)
        + """
	(str.++ ntString ntString)
	(str.replace ntString ntString ntString)
	(str.at ntString ntInt)
	(int.to.str ntInt)
	(ite ntBool ntString ntString)
	(str.substr ntString ntInt ntInt)
    (str.rev ntString)
)) 
 (ntInt Int (
	"""
        + ' '.join([f'_arg_{index}' for index, curr_type in enumerate(inType) if curr_type == 'Int'])
        + """
    -1 0 1 2 5 """
        + ' '.join(str(new_int) for new_int in additional_int)
        + """
	(+ ntInt ntInt)
	(- ntInt ntInt)
	(/ ntInt ntInt)
    (* ntInt ntInt)
	(% ntInt ntInt)
	(str.len ntString)
	(str.to.int ntString)
	(ite ntBool ntInt ntInt)
	(str.indexof ntString ntString ntInt)
))
 (ntBool Bool (
    """
        + ' '.join([f'_arg_{index}' for index, curr_type in enumerate(inType) if curr_type == 'Bool'])
        + """
	true false
	(= ntInt ntInt)
    (< ntInt ntInt)
    (not ntBool)
	(str.prefixof ntString ntString)
	(str.suffixof ntString ntString)
	(str.contains ntString ntString)
)) ))

"""
    )

    for i, ex in enumerate(examples):
        if len(ex[0]) != len(inType):
            new_ex = dict()
            for key in ex[0]:
                if not (key.startswith("__") and key.endswith("__")):
                    new_ex[key] = ex[0][key]
            examples[i] = (new_ex, ex[1])

    str_examples = list(
        map(
            lambda ex: (
                list(map(lambda x: pretty_in(inType, x), enumerate(ex[0].values()))),
                pretty_out(outType, ex[1]),
            ),
            examples,
        )
    )
    constraints = '\n'.join(
        '(constraint(= (f ' + ' '.join(input for input in inputs) + ') ' + output + '))'
        for inputs, output in str_examples
    )

    checkSynth = '(check-synth)'

    return '\n'.join([body, constraints, checkSynth])
