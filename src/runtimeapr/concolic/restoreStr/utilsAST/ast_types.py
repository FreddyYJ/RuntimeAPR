from typing import Union
import numpy as np


# trait for Typed Abstract Syntax Tree
class TAST:
    def __repr__(self): ...
    def __call__(self, *args) -> Union[int, str, bool]: ...  # type: ignore


# Binary Operations
class BinOp(TAST):
    def __init__(self, ob1, ob2):
        self.ob1 = ob1
        self.ob2 = ob2

    def __repr__(self):
        return "(" + self.ob1.__repr__() + ") " + self.__class__.__name__ + " (" + self.ob2.__repr__() + ")"


# Unary Operations
class UnOp(TAST):
    def __init__(self, ob):
        self.ob = ob

    def __repr__(self):
        return self.__class__.__name__ + " (" + self.ob.__repr__() + ")"


# k-ary (k from 1 to 3) functins
class F1(TAST):
    def __init__(self, x):
        self.x = x

    def __repr__(self):
        return self.__class__.__name__ + " (" + self.x.__repr__() + ")"


class F2(TAST):
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __repr__(self):
        return self.__class__.__name__ + " (" + self.x.__repr__() + ", " + self.y.__repr__() + ")"


class F3(TAST):
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z

    def __repr__(self):
        return (
            self.__class__.__name__
            + " ("
            + self.x.__repr__()
            + ", "
            + self.y.__repr__()
            + ", "
            + self.z.__repr__()
            + ")"
        )


# Boolean operations
class Equal(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) == self.ob2(*args)


class Lt(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) < self.ob2(*args)


class Gt(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) > self.ob2(*args)


class Le(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) <= self.ob2(*args)


class Ge(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) >= self.ob2(*args)


class And(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) and self.ob2(*args)


class Or(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) or self.ob2(*args)


class Xor(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) ^ self.ob2(*args)


class Not(UnOp):
    def __call__(self, *args):
        return not self.ob(*args)


class ITE(F3):
    def __call__(self, *args):
        if self.x(*args):
            return self.y(*args)
        return self.z(*args)


# String operations
class Len(F1):
    def __call__(self, *args):
        return len(self.x(*args))


class StrToInt(F1):
    def __call__(self, *args):
        return int(self.x(*args))


class IntToStr(F1):
    def __call__(self, *args):
        return str(self.x(*args))


class At(F2):
    def __call__(self, *args):
        return self.x(*args)[self.y(*args)]


class Concat(F2):
    def __call__(self, *args):
        return self.x(*args) + self.y(*args)


class Contains(F2):
    def __call__(self, *args):
        return self.y(*args) in self.x(*args)


class PrefixOf(F2):
    def __call__(self, *args):
        return self.y(*args).startswith(self.x(*args))


class SuffixOf(F2):
    def __call__(self, *args):
        return self.y(*args)[::-1].startswith(self.x(*args)[::-1])


class IndexOf(F3):
    def __call__(self, *args):
        return self.x(*args).index(self.y(*args), self.z(*args))


class Replace(F3):
    def __call__(self, *args):
        return self.x(*args).replace(self.y(*args), self.z(*args), 1)


class SubStr(F3):
    def __call__(self, *args):
        begin = self.y(*args)
        return self.x(*args)[begin : begin + self.z(*args)]


# Bit Vector operations
class BVAdd(BinOp):
    # I hope I will remember to use np arrays...
    def __call__(self, *args):
        return self.ob1(*args) + self.ob2(*args)


class BVSub(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) - self.ob2(*args)


class BVNeg(UnOp):
    def __call__(self, *args):
        return -self.ob


class BVNot(UnOp):
    def __call__(self, *args):
        return ~self.ob(*args)


class BVMul(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) * self.ob2(*args)


class BVUDiv(BinOp):
    def __call__(self, *args):  # weird manipulation for unsigned division
        return np.int64(np.uint64(self.ob1(*args)) // np.uint64(self.ob2(*args)))


# TODO or not to do: BV from bvsdiv to bvsge


# Integers operations
class Add(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) + self.ob2(*args)


class Sub(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) - self.ob2(*args)


class Neg(UnOp):
    def __call__(self, *args):
        return -self.ob(*args)


class Mul(BinOp):
    def __call__(self, *args):
        return self.ob1(*args) * self.ob2(*args)


class Div(BinOp):
    def __call__(self, *args):
        num = self.ob1(*args)
        den = self.ob2(*args)
        return abs(num) // abs(den) * (np.sign(num) * np.sign(den))


class Modulo(BinOp):
    def __call__(self, *args):
        num = self.ob1(*args)
        den = self.ob2(*args)
        return num - np.sign(num) * (abs(num) // abs(den)) * abs(den)


# Terminal objects
class Const(TAST):
    def __init__(self, value):
        if value.isnumeric():
            self.value = int(value)
        else:
            self.value = value

    def __call__(self, *args):
        return self.value

    def __repr__(self):
        if isinstance(self.value, str):
            return f'"{self.value}"'
        return str(self.value)


class Var(TAST):
    def __init__(self, varidx):
        self.varidx = varidx

    def __call__(self, *args):
        return args[self.varidx]

    def __repr__(self):
        return f"_arg_{self.varidx}"


def is_terminal(node):
    return isinstance(node, (Var, Const))


class F(TAST):
    def __init__(self, body):
        self.body = body

    def __call__(self, *args):
        return self.body(*args)

    def __repr__(self):
        return "def f:\n\t" + self.body.__repr__()


def get_type(obj):
    if isinstance(obj, int):
        return "Int"
    if isinstance(obj, str):
        return "String"
    if isinstance(obj, bool):
        return "Bool"
    raise ValueError("Unsuported type")
