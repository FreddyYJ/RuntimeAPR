import dataclasses
from typing import Any, Dict
import inspect

@dataclasses.dataclass
class BugInformation:
    local_vars=dict()
    global_vars=dict()
    buggy_line:int
    buggy_func:str
    buggy_args_values:Dict[str,Any]
    buggy_global_values:Dict[str,Any]

def is_default_global(fn,name,obj):
    """
    Check if a global variable is default or system variable
    :param name: name of the variable
    :return: True if it is default or system variable
    """
    if name.startswith("__") and name.endswith("__"):
        return True
    elif 'jurigged' in name:
        return True
    elif inspect.isfunction(obj) or inspect.ismodule(obj) or inspect.ismethod(obj) or inspect.isclass(obj):
        return True
    
    func:function=fn
    if name==func.__name__:
        return True
    return False

def prune_default_global_var(fn,global_vars:Dict[str,Any]):
    output=dict()
    for name,obj in global_vars.items():
        if not is_default_global(fn,name,obj):
            output[name]=obj
    
    return output
