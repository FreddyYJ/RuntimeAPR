#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# "Concolic Fuzzing" - a chapter of "The Fuzzing Book"
# Web site: https://www.fuzzingbook.org/html/ConcolicFuzzer.html
# Last change: 2022-05-18 12:45:52+02:00
#
# Copyright (c) 2021 CISPA Helmholtz Center for Information Security
# Copyright (c) 2018-2020 Saarland University, authors, and contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from typing import List, Callable, Dict, Tuple
import z3
import inspect
import string

class ConcolicTracer:
    """Trace function execution, tracking variables and path conditions"""

    def __init__(self, context=None):
        """Constructor."""
        self.context = context if context is not None else ({}, [])
        self.decls, self.path = self.context

    def __getitem__(self, fn):
        self.fn = fn
        self.fn_args = {i: None for i in inspect.signature(fn).parameters}
        return self

    def __call__(self, *args):
        self.result = self.fn(*self.concolic(args))
        return self.result
    
    def smt_expr(self, show_decl=False, simplify=False, path=[]):
        r = []
        if show_decl:
            for decl in self.decls:
                v = self.decls[decl]
                v = '(_ BitVec 8)' if v == 'BitVec' else v
                r.append("(declare-const %s %s)" % (decl, v))
        path = path if path else self.path
        if path:
            path = z3.And(path)
            if show_decl:
                if simplify:
                    return '\n'.join([
                        *r,
                        "(assert %s)" % z3.simplify(path).sexpr()
                    ])
                else:
                    return '\n'.join(
                        [*r, "(assert %s)" % path.sexpr()])
            else:
                return z3.simplify(path).sexpr()
        else:
            return ''

    def __enter__(self):
        reset_counter()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        return

    def concolic(self, args):
        my_args = []
        for name, arg in zip(self.fn_args, args):
            t = type(arg).__name__
            if t.startswith('z'):
                zwrap=t
            else:
                zwrap = globals()['z' + t]
            # vname = "%s_%s_%s_%s" % (self.fn.__name__, name, t, fresh_name())
            vname=name
            my_args.append(zwrap.create(self.context, vname, arg))
            self.fn_args[name] = vname
        return my_args

    def zeval(self, predicates=None, *,python=False, log=False):
        """Evaluate `predicates` in current context.
        - If `python` is set, use the z3 Python API; otherwise use z3 standalone.
        - If `log` is set, show input to z3.
        Return a pair (`result`, `solution`) where
        - `result` is either `'sat'` (satisfiable); then 
           solution` is a mapping of variables to (value, type) pairs; or
        - `result` is not `'sat'`, indicating an error; then `solution` is `None`
        """
        if predicates is None:
            path = self.path
        else:
            path = list(self.path)
            for i in sorted(predicates):
                if len(path) > i:
                    path[i] = predicates[i]
                else:
                    path.append(predicates[i])
        if log:
            print('Predicates in path:')
            for i, p in enumerate(path):
                print(i, p)
            print()

        r, sol = (zeval_py if python else zeval_smt)(path, self, log)
        if r == 'sat':
            return r, {k: sol.get(self.fn_args[k], None) for k in self.fn_args}
        else:
            return r, None

def zproxy_create(cls, z_type, z3var, context, z_name, v=None):
    z_value = cls(context, z3var(z_name), v)
    context[0][z_name] = z_type  # add to decls
    return z_value

class zbool:
    @classmethod
    def create(cls, context, z_name, v):
        if isinstance(v, zbool):
            v = bool(v)
        return zproxy_create(cls, 'Bool', z3.Bool, context, z_name, v)

    def __init__(self, context, z, v=None):
        self.context = context
        self.z = z
        self.v = v
        self.decl, self.path = self.context

    def __not__(self):
        return zbool(self.context, z3.Not(self.z), not self.v)

    def __bool__(self):
        r, pred = (True, self.z) if self.v else (False, z3.Not(self.z))
        frames=inspect.getouterframes(inspect.currentframe())
        current_frame=frames[1]
        cur_index=1
        while current_frame.filename.endswith('ConcolicTracer.py'):
            cur_index+=1
            current_frame=frames[cur_index]

        pred.cond_lineno=current_frame.lineno
        self.path.append(pred)
        return r
    
    def __hash__(self) -> int:
        return hash(self.v)

class zint(int):
    def __new__(cls, context, zn, v, *args, **kw):
        return int.__new__(cls, v, *args, **kw)

    @classmethod
    def create(cls, context, zn, v=None):
        if isinstance(v, zint):
            v=int(v)
        return zproxy_create(cls, 'Int', z3.Int, context, zn, v)

    def __init__(self, context, z, v=None):
        self.z, self.v = z, v
        self.context = context

    def __int__(self):
        return self.v

    def __pos__(self):
        return self.v

    def _zv(self, o):
        return (o.z, o.v) if isinstance(o, zint) else (z3.IntVal(o), o)

    def __ne__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z != z, self.v != v)

    def __eq__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z == z, self.v == v)

    def __req__(self, other):
        return self.__eq__(other)

    def __lt__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z < z, self.v < v)

    def __gt__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z > z, self.v > v)

    def __le__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, z3.Or(self.z < z, self.z == z),
                     self.v < v or self.v == v)

    def __ge__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, z3.Or(self.z > z, self.z == z),
                     self.v > v or self.v == v)
    
    def __bool__(self):
        # return zbool(self.context, self.z, self.v) <-- not allowed
        # force registering boolean condition
        if self != 0:
            return True
        return False
    
    def __hash__(self) -> int:
        return super().__hash__()
    
class zfloat(float):
    def __new__(cls, context, zn, v, *args, **kw):
        return float.__new__(cls, v, *args, **kw)

    @classmethod
    def create(cls, context, zn, v=None):
        if isinstance(v, zfloat):
            v=float(v)
        return zproxy_create(cls, 'Real', z3.Real, context, zn, v)

    def __init__(self, context, z, v=None):
        self.z, self.v = z, v
        self.context = context

    def __int__(self):
        return int(self.v)
    
    def __float__(self):
        return self.v

    def __pos__(self):
        return self.v

    def _zv(self, o):
        return (o.z, o.v) if isinstance(o, zfloat) else (z3.RealVal(o), o)

    def __ne__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z != z, self.v != v)

    def __eq__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z == z, self.v == v)

    def __req__(self, other):
        return self.__eq__(other)

    def __lt__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z < z, self.v < v)

    def __gt__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z > z, self.v > v)

    def __le__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, z3.Or(self.z < z, self.z == z),
                     self.v < v or self.v == v)

    def __ge__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, z3.Or(self.z > z, self.z == z),
                     self.v > v or self.v == v)
    
    def __bool__(self):
        # return zbool(self.context, self.z, self.v) <-- not allowed
        # force registering boolean condition
        if self != 0:
            return True
        return False
    
    def __hash__(self) -> int:
        return super().__hash__()


INT_BINARY_OPS = [
    '__add__',
    '__sub__',
    '__mul__',
    '__truediv__',
    # '__div__',
    '__mod__',
    # '__divmod__',
    '__pow__',
    # '__lshift__',
    # '__rshift__',
    # '__and__',
    # '__xor__',
    # '__or__',
    '__radd__',
    '__rsub__',
    '__rmul__',
    '__rtruediv__',
    # '__rdiv__',
    '__rmod__',
    # '__rdivmod__',
    '__rpow__',
    # '__rlshift__',
    # '__rrshift__',
    # '__rand__',
    # '__rxor__',
    # '__ror__',
]

def make_int_binary_wrapper(fname, fun, zfun):  # type: ignore
    def proxy(self, other):
        z, v = self._zv(other)
        z_ = zfun(self.z, z)
        v_ = fun(self.v, v)
        if isinstance(v_, float):
            return zfloat(self.context, z_, v_)
        return zint(self.context, z_, v_)

    return proxy

INITIALIZER_LIST: List[Callable] = []

def initialize():
    for fn in INITIALIZER_LIST:
        fn()

def init_concolic_1():
    for fname in INT_BINARY_OPS:
        fun = getattr(int, fname)
        zfun = getattr(z3.ArithRef, fname)
        setattr(zint, fname, make_int_binary_wrapper(fname, fun, zfun))
        func= getattr(float, fname)
        zfunc = getattr(z3.ArithRef, fname)
        setattr(zfloat, fname, make_int_binary_wrapper(fname, func, zfunc))

INITIALIZER_LIST.append(init_concolic_1)

INT_UNARY_OPS = [
    '__neg__',
    '__pos__',
    # '__abs__',
    # '__invert__',
    # '__round__',
    # '__ceil__',
    # '__floor__',
    # '__trunc__',
]

def make_int_unary_wrapper(fname, fun, zfun):
    def proxy(self):
        return zint(self.context, zfun(self.z), fun(self.v))

    return proxy

def make_float_unary_wrapper(fname, fun, zfun):
    def proxy(self):
        return zfloat(self.context, zfun(self.z), fun(self.v))

    return proxy

def init_concolic_2():
    for fname in INT_UNARY_OPS:
        fun = getattr(int, fname)
        zfun = getattr(z3.ArithRef, fname)
        setattr(zint, fname, make_int_unary_wrapper(fname, fun, zfun))
        fun= getattr(float, fname)
        zfun = getattr(z3.ArithRef, fname)
        setattr(zfloat, fname, make_float_unary_wrapper(fname, fun, zfun))

INITIALIZER_LIST.append(init_concolic_2)

COUNTER = 0

def fresh_name():
    global COUNTER
    COUNTER += 1
    return COUNTER

def reset_counter():
    global COUNTER
    COUNTER = 0


def zeval_py(path, cc, log):
    for decl in cc.decls:
        if cc.decls[decl] == 'BitVec':
            v = "z3.%s('%s', 8)" % (cc.decls[decl], decl)
        else:
            v = "z3.%s('%s')" % (cc.decls[decl], decl)
        exec(v)
    s = z3.Solver()
    s.add(z3.And(path))
    if s.check() == z3.unsat:
        return 'No Solutions', {}
    elif s.check() == z3.unknown:
        return 'Gave up', None
    assert s.check() == z3.sat
    m = s.model()
    return 'sat', {d.name(): m[d] for d in m.decls()}

import re

import subprocess

SEXPR_TOKEN = r'''(?mx)
    \s*(?:
        (?P<bra>\()|
        (?P<ket>\))|
        (?P<token>[^"()\s]+)|
        (?P<string>"[^"]*")
       )'''

def parse_sexp(sexp):
    stack, res = [], []
    for elements in re.finditer(SEXPR_TOKEN, sexp):
        kind, value = [(t, v) for t, v in elements.groupdict().items() if v][0]
        if kind == 'bra':
            stack.append(res)
            res = []
        elif kind == 'ket':
            last, res = res, stack.pop(-1)
            res.append(last)
        elif kind == 'token':
            res.append(value)
        elif kind == 'string':
            res.append(value[1:-1])
        else:
            assert False
    return res

import tempfile
import os

Z3_BINARY = 'z3'  # Z3 binary to invoke

Z3_OPTIONS = '-t:6000'  # Z3 options - a soft timeout of 6000 milliseconds

def zeval_smt(path, cc, log):
    s = cc.smt_expr(True, True, path)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.smt',
                                     delete=False) as f:
        f.write(s + "\n")
        f.write("(check-sat)\n")
        f.write("(get-model)\n")

    if log:
        print(open(f.name).read())

    cmd = f"{Z3_BINARY} {Z3_OPTIONS} {f.name}"
    if log:
        print(cmd)

    output = subprocess.getoutput(cmd)

    os.remove(f.name)

    if log:
        print(output)

    o = parse_sexp(output)
    if not o:
        return 'Gave up', None

    kind = o[0]
    if kind == 'unknown':
        return 'Gave up', None
    elif kind == 'timeout':
        return 'Timeout', None
    elif kind == 'unsat':
        return 'No Solutions', {}

    assert kind == 'sat', kind
    if o[1][0] == 'model': # up to 4.8.8.0
        return 'sat', {i[1]: (i[-1], i[-2]) for i in o[1][1:]}
    else:
        return 'sat', {i[1]: (i[-1], i[-2]) for i in o[1][0:]}

class zstr(str):
    def __new__(cls, context, zn, v):
        return str.__new__(cls, v)

    @classmethod
    def create(cls, context, zn, v=None):
        if isinstance(v, zstr):
            v = str(v)
        return zproxy_create(cls, 'String', z3.String, context, zn, v)

    def __init__(self, context, z, v=None):
        self.context, self.z, self.v = context, z, v
        self._len = zint(context, z3.Length(z), len(v))
        #self.context[1].append(z3.Length(z) == z3.IntVal(len(v)))

    def _zv(self, o):
        return (o.z, o.v) if isinstance(o, zstr) else (z3.StringVal(o), o)
    
    def __eq__(self, other):
        z, v = self._zv(other)
        return zbool(self.context, self.z == z, self.v == v)

    def __req__(self, other):
        return self.__eq__(other)
    
    def __len__(self):
        return len(self.v)

    def length(self):
        return self._len
    
    def __add__(self, other):
        z, v = self._zv(other)
        return zstr(self.context, self.z + z, self.v + v)

    def __radd__(self, other):
        return self.__add__(other)

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            start, stop, step = idx.indices(len(self.v))
            assert step == 1  # for now
            assert stop >= start  # for now
            rz = z3.SubString(self.z, start, stop - start)
            rv = self.v[idx]
        elif isinstance(idx, int):
            rz = z3.SubString(self.z, idx, 1)
            rv = self.v[idx]
        else:
            assert False  # for now
        return zstr(self.context, rz, rv)

    def __iter__(self):
        return zstr_iterator(self.context, self)

    def __hash__(self):
        return hash(self.v)
    
    def __getstate__(self):
        return None
    
    def encode(self, encoding='utf-8', errors='strict'):
        return self.v.encode(encoding, errors)
    
    def upper(self):
        empty = ''
        ne = 'empty_%d' % fresh_name()
        result = zstr.create(self.context, ne, empty)
        self.context[1].append(z3.StringVal(empty) == result.z)
        cdiff = (ord('a') - ord('A'))
        for i in self:
            oz = zord(self.context, i.z)
            uz = zchr(self.context, oz - cdiff)
            rz = z3.And([oz >= ord('a'), oz <= ord('z')])
            ov = ord(i.v)
            uv = chr(ov - cdiff)
            rv = ov >= ord('a') and ov <= ord('z')
            if zbool(self.context, rz, rv):
                i = zstr(self.context, uz, uv)
            else:
                i = zstr(self.context, i.z, i.v)
            result += i
        return result

    def lower(self):
        empty = ''
        ne = 'empty_%d' % fresh_name()
        result = zstr.create(self.context, ne, empty)
        self.context[1].append(z3.StringVal(empty) == result.z)
        cdiff = (ord('a') - ord('A'))
        for i in self:
            oz = zord(self.context, i.z)
            uz = zchr(self.context, oz + cdiff)
            rz = z3.And([oz >= ord('A'), oz <= ord('Z')])
            ov = ord(i.v)
            uv = chr(ov + cdiff)
            rv = ov >= ord('A') and ov <= ord('Z')
            if zbool(self.context, rz, rv):
                i = zstr(self.context, uz, uv)
            else:
                i = zstr(self.context, i.z, i.v)
            result += i
        return result

    def startswith(self, other, beg=0, end=None):
        assert end is None  # for now
        assert isinstance(beg, int)  # for now
        zb = z3.IntVal(beg)

        others = other if isinstance(other, tuple) else (other, )

        last = False
        for o in others:
            z, v = self._zv(o)
            r = z3.IndexOf(self.z, z, zb)
            last = zbool(self.context, r == zb, self.v.startswith(v))
            if last:
                return last
        return last

    def find(self, other, beg=0, end=None):
        assert end is None  # for now
        assert isinstance(beg, int)  # for now
        zb = z3.IntVal(beg)
        z, v = self._zv(other)
        zi = z3.IndexOf(self.z, z, zb)
        vi = self.v.find(v, beg, end)
        return zint(self.context, zi, vi)

    def rstrip(self, chars=None):
        if chars is None:
            chars = string.whitespace
        if self._len == 0:
            return self
        else:
            last_idx = self._len - 1
            cz = z3.SubString(self.z, last_idx.z, 1)
            cv = self.v[-1]
            zcheck_space = z3.Or([cz == z3.StringVal(char) for char in chars])
            vcheck_space = any(cv == char for char in chars)
            if zbool(self.context, zcheck_space, vcheck_space):
                return zstr(self.context, z3.SubString(self.z, 0, last_idx.z),
                            self.v[0:-1]).rstrip(chars)
            else:
                return self

    def lstrip(self, chars=None):
        if chars is None:
            chars = string.whitespace
        if self._len == 0:
            return self
        else:
            first_idx = 0
            cz = z3.SubString(self.z, 0, 1)
            cv = self.v[0]
            zcheck_space = z3.Or([cz == z3.StringVal(char) for char in chars])
            vcheck_space = any(cv == char for char in chars)
            if zbool(self.context, zcheck_space, vcheck_space):
                return zstr(self.context, z3.SubString(
                    self.z, 1, self._len.z), self.v[1:]).lstrip(chars)
            else:
                return self

    def strip(self, chars=None):
        return self.lstrip(chars).rstrip(chars)

    def split(self, sep=None, maxsplit=-1):
        assert sep is not None  # default space based split is complicated
        assert maxsplit == -1  # for now.
        zsep = z3.StringVal(sep)
        zl = z3.Length(zsep)
        # zi would be the length of prefix
        zi = z3.IndexOf(self.z, zsep, z3.IntVal(0))
        # Z3Bug: There is a bug in the `z3.IndexOf` method which returns
        # `z3.SeqRef` instead of `z3.ArithRef`. So we need to fix it.
        zi = z3.ArithRef(zi.ast, zi.ctx)

        vi = self.v.find(sep)
        if zbool(self.context, zi >= z3.IntVal(0), vi >= 0):
            zprefix = z3.SubString(self.z, z3.IntVal(0), zi)
            zmid = z3.SubString(self.z, zi, zl)
            zsuffix = z3.SubString(self.z, zi + zl,
                                   z3.Length(self.z))
            return [zstr(self.context, zprefix, self.v[0:vi])] + zstr(
                self.context, zsuffix, self.v[vi + len(sep):]).split(
                    sep, maxsplit)
        else:
            return [self]
        
class zstr_iterator():
    def __init__(self, context, zstr):
        self.context = context
        self._zstr = zstr
        self._str_idx = 0
        self._str_max = zstr._len  # intz is not an _int_

    def __next__(self):
        if self._str_idx == self._str_max:  # intz#eq
            raise StopIteration
        c = self._zstr[self._str_idx]
        self._str_idx += 1
        return c

    def __len__(self):
        return self._len

from typing import Union, Optional, Dict, Generator, Set

def visit_z3_expr(
        e: Union[z3.ExprRef, z3.QuantifierRef],
        seen: Optional[Dict[Union[z3.ExprRef, z3.QuantifierRef], bool]] = None) -> \
        Generator[Union[z3.ExprRef, z3.QuantifierRef], None, None]:
    if seen is None:
        seen = {}
    elif e in seen:
        return

    seen[e] = True
    yield e

    if z3.is_app(e):
        for ch in e.children():
            for e in visit_z3_expr(ch, seen):
                yield e
        return

    if z3.is_quantifier(e):
        for e in visit_z3_expr(e.body(), seen):
            yield e
        return


def is_z3_var(e: z3.ExprRef) -> bool:
    return z3.is_const(e) and e.decl().kind() == z3.Z3_OP_UNINTERPRETED


def get_all_vars(e: z3.ExprRef) -> Set[z3.ExprRef]:
    return {sub for sub in visit_z3_expr(e) if is_z3_var(sub)}


def z3_ord(str_expr: z3.SeqRef) -> z3.ArithRef:
    return z3.parse_smt2_string(
        f"(assert (= 42 (str.to_code {str_expr.sexpr()})))",
        decls={str(c): c for c in get_all_vars(str_expr)}
    )[0].children()[1]


def z3_chr(int_expr: z3.ArithRef) -> z3.SeqRef:
    return z3.parse_smt2_string(
        f"(assert (= \"4\" (str.from_code {int_expr.sexpr()})))",
        decls={str(c): c for c in get_all_vars(int_expr)}
    )[0].children()[1]

def zord(context, c):
    return z3_ord(c)

def zchr(context, i):
    return z3_chr(i)
    
def make_str_abort_wrapper(fun):
    def proxy(*args, **kwargs):
        raise Exception('%s Not implemented in `zstr`' % fun.__name__)
    return proxy

def init_concolic_3():
    strmembers = inspect.getmembers(zstr, callable)
    zstrmembers = {m[0] for m in strmembers if len(
        m) == 2 and 'zstr' in m[1].__qualname__}
    for name, fn in inspect.getmembers(str, callable):
        # Omitted 'splitlines' as this is needed for formatting output in
        # IPython/Jupyter
        if name not in zstrmembers and name not in [
            'splitlines',
            '__class__',
            '__contains__',
            '__delattr__',
            '__dir__',
            '__format__',
            '__ge__',
            '__getattribute__',
            '__getnewargs__',
            '__gt__',
            '__hash__',
            '__le__',
            '__len__',
            '__lt__',
            '__mod__',
            '__mul__',
            '__ne__',
            '__reduce__',
            '__reduce_ex__',
            '__repr__',
            '__rmod__',
            '__rmul__',
            '__setattr__',
            '__sizeof__',
                '__str__']:
            setattr(zstr, name, make_str_abort_wrapper(fn))

INITIALIZER_LIST.append(init_concolic_3)

BIT_OPS = [
    '__lshift__',
    '__rshift__',
    '__and__',
    '__xor__',
    '__or__',
    '__rlshift__',
    '__rrshift__',
    '__rand__',
    '__rxor__',
    '__ror__',
]

def make_int_bit_wrapper(fname, fun, zfun):
    def proxy(self, other):
        z, v = self._zv(other)
        z_ = z3.BV2Int(
            zfun(
                z3.Int2BV(
                    self.z, num_bits=64), z3.Int2BV(
                    z, num_bits=64)))
        v_ = fun(self.v, v)
        return zint(self.context, z_, v_)

    return proxy

def init_concolic_4():
    for fname in BIT_OPS:
        fun = getattr(int, fname)
        zfun = getattr(z3.BitVecRef, fname)
        setattr(zint, fname, make_int_bit_wrapper(fname, fun, zfun))

INITIALIZER_LIST.append(init_concolic_4)

def get_zvalue(ctxt,name:str,obj:object):
    if type(obj)==zint:
        return zint.create(ctxt,name,obj.v)
    elif type(obj)==zstr:
        return zstr.create(ctxt,name,obj.v)
    elif type(obj)==zbool:
        return zbool.create(ctxt,name,obj.v)
    elif type(obj)==zfloat:
        return zfloat.create(ctxt,name,obj.v)
    elif type(obj)==int:
        return zint.create(ctxt,name,obj)
    elif type(obj)==str:
        return zstr.create(ctxt,name,obj)
    elif type(obj)==bool:
        return zbool.create(ctxt,name,obj)
    elif type(obj)==float:
        return zfloat.create(ctxt,name,obj)
    else:
        return obj

# Added by me
initialize()

def symbolize(ctxt,name:str,obj:object,before_objs:Dict[str,object]):
    if type(obj) in (int,str,bool,float,zint,zstr,zbool,zfloat):
        if name in before_objs:
            return get_zvalue(ctxt,name,before_objs[name])
        else:
            return get_zvalue(ctxt,name,obj)
    elif type(obj) in (list,set,tuple):
        # Symbolize elements if object is a list, set or tuple
        cur_type=type(obj)
        if cur_type==set:
            # Convert set to list and sort it to make it deterministic
            obj=list(obj)
            # obj.sort()
        elif cur_type==tuple:
            # Convert tuple to list
            obj=list(obj)

        # Symbolize elements
        for i,e in enumerate(obj):
            cur_name=f'{name}[{i}]'
            symbol=symbolize(ctxt,cur_name,e,before_objs)
            obj[i]=symbol
        
        if cur_type==set:
            # Convert list back to tuple
            obj=set(obj)
        elif cur_type==tuple:
            # Convert list back to tuple
            obj=tuple(obj)

        return obj
    elif type(obj)==dict:
        # Symbolize values if object is a dict
        for k,v in obj.items():
            cur_name=f'{name}[{k}]'
            symbol=symbolize(ctxt,cur_name,v,before_objs)
            obj[k]=symbol
        
        return obj
    
    if hasattr(obj,'__dict__'):
        # Symbolize attributes if available
        for attr_name,value in obj.__dict__.items():
            try:
                value_name=name+'.'+attr_name
                if type(value) in (int,str,bool,float,zint,zstr,zbool,zfloat):
                    if value_name in before_objs:
                        symbol=get_zvalue(ctxt,value_name,before_objs[value_name])
                    else:
                        symbol=get_zvalue(ctxt,value_name,value)
                else:
                    symbol=symbolize(ctxt,value_name,value)
            
                obj.__dict__[attr_name]=symbol
            except:
                pass
    
    return obj
