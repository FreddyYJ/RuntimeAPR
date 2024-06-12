from .ast_types import *
from typing import List


def is_correct_char(c: str) -> bool:
    return c != "(" and c != ")" and not c.isspace() and c != "\""  # c.isalnum()


def normalize_str(string: str) -> List[str]:
    str_norm: List[str] = []
    last_c = ""
    is_in_str = False
    for c in string:
        if is_in_str:
            if c != '"':
                str_norm[-1] += c
            else:
                is_in_str = False
        elif c == '"':
            is_in_str = True
            str_norm.append("")
        elif is_correct_char(c):
            if is_correct_char(last_c):
                str_norm[-1] += c
            else:
                str_norm.append(c)
        elif not c.isspace():
            str_norm.append(c)
        last_c = c
    return str_norm


def list_ast_to_tast(last: Union[str, list]) -> TAST:
    # end cases
    if not last:
        assert False, "Empty Token"
    if isinstance(last, list) and len(last) == 1:
        return list_ast_to_tast(last[0])
    if not isinstance(last, list):
        if isinstance(last, str) and last.startswith("_arg_"):
            return Var(int(last[5:]))
        return Const(last)
    if len(last) == 1:
        return list_ast_to_tast(last[0])
    # operation last = [op, arg+]
    if last[0] == "=":
        return Equal(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "<":
        return Lt(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == ">":
        return Gt(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "<=":
        return Le(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == ">=":
        return Ge(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "and":
        return And(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "or":
        return Or(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "xor":
        return Xor(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "not":
        return Not(list_ast_to_tast(last[1]))
    if last[0] == "ite":
        return ITE(
            list_ast_to_tast(last[1]),
            list_ast_to_tast(last[2]),
            list_ast_to_tast(last[3]),
        )
    if last[0] == "str.len":
        return Len(list_ast_to_tast(last[1]))
    if last[0] == "str.to.int":
        return StrToInt(list_ast_to_tast(last[1]))
    if last[0] == "int.to.str":
        return IntToStr(list_ast_to_tast(last[1]))
    if last[0] == "str.at":
        return At(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "str.++":
        return Concat(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "str.contains":
        return Contains(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "str.prefixof":
        return PrefixOf(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "str.suffixof":
        return SuffixOf(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "str.indexof":
        return IndexOf(
            list_ast_to_tast(last[1]),
            list_ast_to_tast(last[2]),
            list_ast_to_tast(last[3]),
        )
    if last[0] == "str.replace":
        return Replace(
            list_ast_to_tast(last[1]),
            list_ast_to_tast(last[2]),
            list_ast_to_tast(last[3]),
        )
    if last[0] == "str.substr":
        return SubStr(
            list_ast_to_tast(last[1]),
            list_ast_to_tast(last[2]),
            list_ast_to_tast(last[3]),
        )
    if last[0] == "+":
        return Add(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "-":  # either unary or binary minus
        if len(last) == 2:
            return Neg(list_ast_to_tast(last[1]))
        return Sub(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "*":
        return Mul(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "/":
        return Div(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "%" or last[0] == "mod":
        return Modulo(list_ast_to_tast(last[1]), list_ast_to_tast(last[2]))
    if last[0] == "define-fun":  # ["define-fun", fun-name, list-inputs, output-type, fun-body]
        return F(list_ast_to_tast(last[4]))
    raise ValueError("Unknown Token:", str(last[0]))


def get_ast(input_norm: List[str]) -> List[Union[str, list]]:
    ast: List[Union[str, list]] = []
    i = 0
    while i < len(input_norm):
        symbol = input_norm[i]
        if symbol == "(":
            list_content = []
            match_ctr = 1
            while match_ctr != 0:
                i += 1
                if i >= len(input_norm):
                    raise ValueError("Invalid input: unmatched opening parenthesis")
                symbol = input_norm[i]
                if symbol == "(":
                    match_ctr += 1
                elif symbol == ")":
                    match_ctr -= 1
                if match_ctr != 0:
                    list_content.append(symbol)
            ast.append(get_ast(list_content))
        elif symbol == ")":
            raise ValueError("Invalid input: unmatched closing parenthesis")
        else:
            try:
                ast.append(str(int(symbol)))
            except ValueError:
                ast.append(symbol)
        i += 1
    return ast


def function_from_string(function_string: str):
    input_norm = normalize_str(function_string)
    ast = get_ast(input_norm)
    return list_ast_to_tast(ast)
