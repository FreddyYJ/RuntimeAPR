import inspect
from typing import Dict, List, Set
from .model import CFG,Block
from .builder import CFGBuilder
from types import CodeType, FunctionType, MethodType
import z3
import ast

class ControlDependenceGraph:
    def __init__(self,fn:FunctionType) -> None:
        self.entry_line=fn.__code__.co_firstlineno
        root_cfg=CFGBuilder().build_from_file('cfg',fn.__code__.co_filename)
        # Find the cfg of the function
        self.cfg:CFG=None
        for c_name in root_cfg.classcfgs:
            c_cfg=root_cfg.classcfgs[c_name]
            if c_cfg.lineno <= self.entry_line <= c_cfg.end_lineno:
                for f_name in c_cfg.functioncfgs:
                    if f_name==fn.__name__:
                        self.cfg=c_cfg.functioncfgs[f_name]
                        break
        
        if self.cfg is None:
            for f_name in root_cfg.functioncfgs:
                if f_name==fn.__name__:
                    self.cfg=root_cfg.functioncfgs[f_name]
                    break
                
        self.not_reachable_nodes=set()
        self.entry:Block=self.cfg.entryblock
        