import ast
import dis
from pathlib import Path
from typing import List, Tuple

import slipcover as sc

filename='instrumentation/simple.py'

with open(filename, 'r') as f:
    t = ast.parse(f.read())
    code = compile(t, str(Path(filename).resolve()), "exec")

instrs=list(dis.get_instructions(code))

from bytecode import Instr,Bytecode,Label,dump_bytecode,ControlFlowGraph

bc=Bytecode.from_code(code)
dump_bytecode(bc,lineno=True)
