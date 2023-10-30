import dataclasses
from types import FunctionType, MethodType, ModuleType
from typing import Any, Dict, List, Set, Union
import inspect
import pickle
from functools import partial

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
    elif 'method-wrapper' in str(type(obj)):
        return True
    elif 'builtin_function_or_method' in str(type(obj)):
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
    if name.startswith("__") and name.endswith("__"):
        return True
    elif name=='_sc_e':
        return True
    elif inspect.isfunction(obj) or inspect.ismodule(obj) or inspect.ismethod(obj) or inspect.isclass(obj):
        return True
    elif '_lru_cache_wrapper' in str(type(obj)):
        return True
    elif 'method-wrapper' in str(type(obj)):
        return True
    elif 'builtin_function_or_method' in str(type(obj)):
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
    def __init__(self,name,data=b'',orig_data=None,unpickled:str='') -> None:
        self.name:str=name
        self.data:Union[bytes,object]=data
        self.children:Dict[str,'PickledObject']=dict()
        self.unpickled:str=unpickled

        self.type=type(orig_data)
        self.orig_data=orig_data
        try:
            self.orig_data_str:str=str(orig_data)
        except:
            self.orig_data_str:str=''
    
    def __str__(self) -> str:
        if self.data!=b'':
            return f'{self.name} (pickled): {self.orig_data_str} :::: {self.data}'
        elif self.unpickled!='':
            return f'{self.name} (cannot pickled): {self.unpickled}'
        else:
            string=f'{self.name} (not pickled):\n'
            for name,child in self.children.items():
                string+=f'\t{name}: {child}\n'
            return string

class SetObject(PickledObject):
    def __init__(self, name,orig_data=None) -> None:
        super().__init__(name,orig_data=orig_data)
        self.type=set
        self.elements:Set[PickledObject]=set()

    def __str__(self) -> str:
        return f'{self.name} (set): {self.elements}'
    
pickle._Pickler.dispatch[zint]=pickle._Pickler.dispatch[int]
pickle._Pickler.dispatch[zbool]=pickle._Pickler.dispatch[bool]
pickle._Pickler.dispatch[zstr]=pickle._Pickler.dispatch[str]
pickle._Pickler.dispatch[zfloat]=pickle._Pickler.dispatch[float]
pickle.dumps=pickle._dumps

def pickle_object(fn:FunctionType,name:str,obj:object,is_global=False,pickled_ids:Dict[int,PickledObject]=dict()):
    if id(obj) in pickled_ids:
        return pickled_ids[id(obj)]
    if type(obj) in (zbool,zint,zstr,zfloat):
        res=PickledObject(name,pickle.dumps(obj.v),obj.v)
        pickled_ids[id(obj.v)]=res
        return res
    elif isinstance(obj,set):
        # Set object
        pickled_obj=SetObject(name,obj)
        new_set=set()
        for i,elem in enumerate(list(obj)):
            new_set.add(pickle_object(fn,str(i),elem,is_global=is_global,pickled_ids=pickled_ids))
        pickled_obj.elements=new_set
        pickled_ids[id(obj)]=pickled_obj
        return pickled_obj
    elif isinstance(obj,list) or isinstance(obj,tuple):
        pickled_obj=PickledObject(name,orig_data=obj)
        for i,elem in enumerate(obj):
            pickled_obj.children[str(i)]=pickle_object(fn,str(i),elem,is_global=is_global,pickled_ids=pickled_ids)
        pickled_ids[id(obj)]=pickled_obj
        return pickled_obj
    elif isinstance(obj,dict):
        pickled_obj=PickledObject(name,orig_data=obj)
        for key,value in obj.items():
            pickled_obj.children[str(key)]=pickle_object(fn,str(key),value,is_global=is_global,pickled_ids=pickled_ids)
        pickled_ids[id(obj)]=pickled_obj
        return pickled_obj
    elif hasattr(obj,'__dict__'):
        # Convert object recursively
        try:
            pickled_obj=PickledObject(name,orig_data=obj)
            for attr in dir(obj):
                try:
                    if (is_global and is_default_global(fn,attr,getattr(obj,attr))) or \
                            (not is_global and is_default_local(fn,attr,getattr(obj,attr))):
                        continue
                    else:
                        attr_obj=pickle_object(fn,attr,getattr(obj,attr),is_global=is_global,pickled_ids=pickled_ids)
                        pickled_ids[id(getattr(obj,attr))]=attr_obj
                        if attr_obj is not None:
                            pickled_obj.children[attr]=attr_obj
                except Exception as e:
                    print(f'Error when pickling {attr}: {e}, skip!')

            return pickled_obj
        except Exception as e:
            # ctypes objects cannot be pickled, use object directly
            return PickledObject(name,orig_data=obj,unpickled=f'{type(e)}: {e}')
    else:
        try:
            data=pickle.dumps(obj)
            res=PickledObject(name,data,obj)
            pickled_ids[id(obj)]=res
            return res
        except Exception as e:
            # ctypes objects cannot be pickled, use object directly
            return PickledObject(name,orig_data=obj,unpickled=f'{type(e)}: {e}')
        
FLOAT_THRESHOLD=0.01

def compare_object(a:PickledObject,b:PickledObject):
    if a.type==partial and b.type==partial:
        # functools.partial is same as function
        return True
    elif a.type==float and b.type==float:
        # Same if they are close enough
        return abs(pickle.loads(a.data)-pickle.loads(b.data))<FLOAT_THRESHOLD
    elif a.unpickled!='' or b.unpickled!='':
        # Just check type if one of them cannot pickled
        return a.type==b.type
    elif isinstance(a,SetObject) and isinstance(b,SetObject):
        if len(a.elements)!=len(b.elements):
            # Different number of elements
            return False
        else:
            # Same number of elements
            for elem_a in a.elements:
                found=False
                for elem_b in b.elements:
                    if compare_object(elem_a,elem_b):
                        found=True
                        break
                if not found:
                    return False
            return True
    elif a.data!=b.data:
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