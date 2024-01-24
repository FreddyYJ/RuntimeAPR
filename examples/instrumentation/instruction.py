import ast
import dis
from pathlib import Path
from types import CodeType
from typing import List, Tuple

import sys

filename=sys.argv[1]

with open(filename, 'r') as f:
    t = ast.parse(f.read())
    code = compile(t, str(Path(filename).resolve()), "exec")

instrs=list(dis.get_instructions(code))

from bytecode import Instr,Bytecode,Label,dump_bytecode,ControlFlowGraph

def get_bc(code:CodeType):
    bc=Bytecode.from_code(code)
    for instr in bc:
        if isinstance(instr,Instr) and instr.name=='LOAD_CONST' and isinstance(instr.arg,CodeType):
            get_bc(instr.arg)
    print('--------------')
    dump_bytecode(bc,lineno=True)
    print(f'File name: {code.co_filename}')
    print(f'Name: {code.co_name}')
    print(f'First line: {code.co_firstlineno}')
    print(f'Constants: {code.co_consts}')
    print(f'Var names: {code.co_varnames}')
    print(f'Free vars: {code.co_freevars}')
    print(f'Cell vars: {code.co_cellvars}')

get_bc(code)