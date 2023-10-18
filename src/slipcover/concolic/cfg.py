import inspect
from typing import Dict, List, Set
from .model import CFG,Block
from .builder import CFGBuilder
from types import CodeType, FunctionType, MethodType
import z3
import ast

def get_target_cfg(cfg:CFG,target_line:int,func_name:str) -> CFG:
    cur_cfg:CFG=None
    for c_name in cfg.classcfgs:
        c_cfg=cfg.classcfgs[c_name]
        if c_cfg.lineno <= target_line <= c_cfg.end_lineno:
            for f_name in c_cfg.functioncfgs:
                if f_name==func_name:
                    cur_cfg=c_cfg.functioncfgs[f_name]
                    break
    
    if cur_cfg is None:
        for f_name in cfg.functioncfgs:
            if f_name==func_name:
                cur_cfg=cfg.functioncfgs[f_name]
                break
    
    if cur_cfg is None:
        for c_name, c_cfg in cfg.classcfgs.items():
            cur_cfg=get_target_cfg(c_cfg,target_line,func_name)
            if cur_cfg is not None:
                break
    
    if cur_cfg is None:
        for f_name, f_cfg in cfg.functioncfgs.items():
            cur_cfg=get_target_cfg(f_cfg,target_line,func_name)
            if cur_cfg is not None:
                break
    
    return cur_cfg

class ControlDependenceGraph:
    def __init__(self,fn:FunctionType) -> None:
        self.entry_line=fn.__code__.co_firstlineno
        root_cfg=CFGBuilder().build_from_file('cfg',fn.__code__.co_filename)
        # Find the cfg of the function
        self.cfg:CFG=get_target_cfg(root_cfg,self.entry_line,fn.__name__)
        
        self.not_reachable_nodes=set()
        self.entry:Block=self.cfg.entryblock
        