import dataclasses
from types import FunctionType, MethodType, ModuleType
from typing import Any, Dict, List, Union
import inspect
import pickle

from ..concolic import zint,zbool,zstr,zfloat

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
    elif name=='_sc_e':
        return True
    elif inspect.isfunction(obj) or inspect.ismodule(obj) or inspect.ismethod(obj) or inspect.isclass(obj):
        return True
    elif '_lru_cache_wrapper' in str(type(obj)):
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

def is_default_local(fn:FunctionType,name,obj):
    if name=='_sc_e':
        return True
    elif inspect.isfunction(obj) or inspect.ismodule(obj) or inspect.ismethod(obj) or inspect.isclass(obj):
        return True
    elif '_lru_cache_wrapper' in str(type(obj)):
        return True
    
    if name==fn.__name__:
        return True
    return False

def prune_default_local_var(fn,local_vars:Dict[str,Any]):
    output=dict()
    for name,obj in local_vars.items():
        if not is_default_local(fn,name,obj):
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
            string=f'{self.name}:\n'
            for name,child in self.children.items():
                string+=f'\t{name}: {child}\n'
            return string

__stack=0

def pickle_object(fn:FunctionType,name:str,obj:object,is_global=False):
    global __stack
    if type(obj) in (zbool,zint,zstr,zfloat):
        return PickledObject(name,pickle.dumps(obj.v))
    elif type(obj) in (list,set,tuple):
        pickled_obj=PickledObject(name)
        cur_type=type(obj)
        if cur_type==set:
            # Convert set to list and sort it to make it deterministic
            obj=list(obj)
            obj.sort()
        elif cur_type==tuple:
            # Convert tuple to list
            obj=list(obj)

        for i,child in enumerate(obj):
            __stack+=1
            child_obj=pickle_object(fn,f'{name}[{i}]',child,is_global=is_global)
            __stack-=1
            pickled_obj.children[f'{name}[{i}]']=child_obj
        return pickled_obj
    else:
        try:
            data=pickle.dumps(obj)
            return PickledObject(name,data)
        except pickle.PicklingError:
            pickled_obj=PickledObject(name)
            for attr in dir(obj):
                if (is_global and is_default_global(fn,attr,getattr(obj,attr))) or \
                        (not is_global and is_default_local(fn,attr,getattr(obj,attr))):
                    continue
                else:
                    __stack+=1
                    attr_obj=pickle_object(fn,attr,getattr(obj,attr),is_global=is_global)
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