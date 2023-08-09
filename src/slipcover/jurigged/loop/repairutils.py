import dataclasses
from types import FunctionType, MethodType, ModuleType
from typing import Any, Dict, List, Union
import inspect
import pickle

from ..concolic import zint,zbool,zstr

class BugInformation:
    def __init__(self,buggy_line,buggy_func,buggy_args_values,buggy_global_values) -> None:
        self.local_vars:Dict[str,'PickledObject']=dict()
        self.global_vars:Dict[str,'PickledObject']=dict()
        self.buggy_line:int=buggy_line
        self.buggy_func:str=buggy_func
        self.buggy_args_values:Dict[str,Any]=buggy_args_values
        self.buggy_global_values:Dict[str,Any]=buggy_global_values

def is_default_global(fn:FunctionType,name,obj):
    """
    Check if a global variable is default or system variable
    :param name: name of the variable
    :return: True if it is default or system variable
    """
    if name.startswith("__") and name.endswith("__"):
        return True
    elif 'jurigged' in name or name=='_sc_e':
        return True
    elif inspect.isfunction(obj) or inspect.ismodule(obj) or inspect.ismethod(obj) or inspect.isclass(obj):
        return True
    
    if name==fn.__name__:
        return True
    return False

def prune_default_global_var(fn,global_vars:Dict[str,Any]):
    output=dict()
    for name,obj in global_vars.items():
        if not is_default_global(fn,name,obj):
            output[name]=obj
    
    return output

class PickledObject:
    def __init__(self,name,data=b'') -> None:
        self.name:str=name
        self.data:Union[bytes,object]=data
        self.children:Dict[str,'PickledObject']=dict()
    
    def __str__(self) -> str:
        if self.data!=b'':
            return f'{self.name}: {self.data}'
        else:
            return f'{self.name}: {self.children}'

__stack=0

def pickle_object(fn:FunctionType,name:str,obj:object):
    global __stack
    if type(obj) in (zbool,zint,zstr):
        return PickledObject(name,pickle.dumps(obj.v))
    else:
        try:
            data=pickle.dumps(obj)
            return PickledObject(name,data)
        except pickle.PicklingError:
            pickled_obj=PickledObject(name)
            for attr in dir(obj):
                if is_default_global(fn,attr,getattr(obj,attr)):
                    continue
                else:
                    __stack+=1
                    attr_obj=pickle_object(fn,attr,getattr(obj,attr))
                    __stack-=1
                    if attr_obj is not None:
                        pickled_obj.children[attr]=attr_obj
            return pickled_obj
        except Exception:
            # ctypes objects cannot be pickled, use object directly
            return PickledObject(name)
        
def compare_object(a:PickledObject,b:PickledObject):
    if a.data!=b.data:
        # Different pickled data
        return False
    else:
        if isinstance(a.data,bytes) and len(a.data)>0:
            # Both have pickled data and they are same
            return True
        else:
            # Both don't have pickled data
            if len(a.children)!=len(b.children):
                # Different number of children
                return False
            else:
                # Same number of children
                for name,child_a in a.children.items():
                    if name in b.children:
                        child_b=b.children[name]
                        if not compare_object(child_a,child_b):
                            return False
                    else:
                        return False
                return True