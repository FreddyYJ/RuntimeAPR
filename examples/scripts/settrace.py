import inspect
from types import FrameType
from typing import Any
from fuzzingbook.ConcolicFuzzer import ConcolicTracer
import z3

buggy_func=''
buggy_line=0

buggy_local=None
buggy_global=None

counter=0

def traceit(frame: FrameType, event: str, arg: Any):
    if event == 'line':
        global buggy_func,buggy_line,buggy_local,buggy_global
        function_name = frame.f_code.co_name
        lineno = frame.f_lineno
        if function_name==buggy_func and lineno==buggy_line:
            print(f'function: {function_name}, line: {lineno}')
            buggy_local=frame.f_locals
            buggy_global=frame.f_globals
            # print(frame.f_code.co_code)
    # elif event=='exception':
    #     print('Still crashed!')

    return traceit


import sys

def foo(a,b=None):
    global counter
    counter+=1
    print(f'counter: {counter}')

    if a==0 and counter>0:
        raise ValueError('A should not be a 0')
    elif a>0:
        print('a>0')
    elif a<0:
        print('a<0')
        
try:
    foo(2)
    sys.settrace(traceit)
    foo(0,1)
    sys.settrace(None)
except ValueError as e:
    sys.settrace(None)
    tb=e.__traceback__
    info=inspect.getinnerframes(tb)[1]
    buggy_func=info.function
    buggy_line=info.lineno

    # sys.settrace(traceit)
    a=z3.Int('foo_a_int_1')
    count=z3.Int('foo_counter_int_2')
    with ConcolicTracer(({'foo_a_int_1':'Int','foo_counter_int_2':'Int'},[a==0,count>0])) as _:
        try:
            _[foo](0,1)
        except:
            pass
        print(_.decls)
        print(_.path)

        solver=z3.Solver()
        for p in _.path:
            solver.add(p)
        
        print(solver.check())
        print(solver.model())
    # sys.settrace(None)

    sources=inspect.getsourcelines(foo)
    print(sources)