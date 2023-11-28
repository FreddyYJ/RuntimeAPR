from enum import Enum
from functools import partial
import random
import struct

from .defusegraph import DefUseGraph
from ..loop.repairutils import PickledObject, SetObject,compare_object, is_default_global, \
    is_default_local, pickle_object, prune_default_global_var, prune_default_local_var

from typing import Dict,List, Set,Tuple
from types import FunctionType, ModuleType
import inspect
from copy import deepcopy
import gast as ast

class StateReproducer:
    def __init__(self,fn:FunctionType,args_names,buggy_local_vars:Dict[str,object],buggy_global_vars:Dict[str,object],
                #  args:List[object],kwargs:Dict[str,object],def_use_chain:List[DefUseGraph.Node]):
                args:List[object],kwargs:Dict[str,object],global_vars:Dict[str,object],def_use_chain:Dict[str,List[str]]):
        self.fn=fn
        self.args_names=args_names
        self.buggy_local_vars=prune_default_local_var(self.fn,buggy_local_vars)
        self.buggy_global_vars=prune_default_global_var(self.fn,buggy_global_vars)
        self.args=args
        self.orig_args=args
        self.kwargs=kwargs
        self.orig_kwargs=kwargs
        self.global_vars=prune_default_global_var(self.fn,global_vars)
        self.def_use_chains=def_use_chain

        """
            [
                (args, kwargs, globals, local_diffs, global_diffs),
                ...
            ]
        """
        self.diffs:List[tuple]=[]

    def run(self,new_args:List[object],new_kwargs:Dict[str,object],new_globals:Dict[str,object]):
        # Prune default variables
        next_globals=prune_default_global_var(self.fn,new_globals)
        args,kwargs,globals=deepcopy([new_args,new_kwargs,next_globals])
        for name,obj in globals.items():
            self.fn.__globals__[name]=obj

        try:
            global is_concolic_execution
            is_concolic_execution=True
            result=self.fn(*args, **kwargs)
        except Exception as _exc:
            print(f'Exception raised: {type(_exc)}: {_exc}')
            innerframes=inspect.getinnerframes(_exc.__traceback__)
            innerframes.reverse()
            inner_info:inspect.FrameInfo=innerframes[0]
            cur_index=0

            while not inner_info.filename.endswith('.py') or (inner_info.function.startswith('<') and inner_info.function.endswith('>')):
                cur_index+=1
                inner_info=innerframes[cur_index]


            return inner_info.frame.f_locals,inner_info.frame.f_globals
        
        return None,None

    def is_vars_same(self,local_vars:Dict[str,object],global_vars:Dict[str,object]):
        is_same=True
        local_diffs:Dict[str,Tuple[object]]=dict()
        global_diffs:Dict[str,Tuple[object]]=dict()

        print('Compare local variables...')
        for name,obj in local_vars.items():
            if is_default_local(self.fn,name,obj):
                continue

            if name not in self.buggy_local_vars:
                is_same=False
                print(f'New local var {name}: {obj}')
                local_diffs[name]=(obj,None)
                continue
            
            _obj=pickle_object(self.fn,name,obj)
            base_obj=pickle_object(self.fn,name,self.buggy_local_vars[name])
            if _obj is not None:
                _is_same=compare_object(_obj,base_obj)
                if not _is_same:
                    local_diffs[name]=(obj,self.buggy_local_vars[name])
                if is_same:
                    is_same=_is_same
            else:
                is_same=False
            # if not is_same:
            #     break

        print('Compare global variables...')
        for name,obj in global_vars.items():
            if is_default_global(self.fn,name,obj):
                continue

            if name not in self.buggy_global_vars:
                # is_same=False
                print(f'New global var {name}: {obj}')
                global_diffs[name]=(obj,None)
                continue

            _obj=pickle_object(self.fn,name,obj,is_global=True)
            base_obj=pickle_object(self.fn,name,self.buggy_global_vars[name],is_global=True)
            if _obj is not None:
                _is_same=compare_object(_obj,base_obj)
                if not _is_same:
                    global_diffs[name]=(obj,self.buggy_global_vars[name])
                if is_same:
                    is_same=_is_same
            else:
                is_same=False
            # if not is_same:
            #     break

        if is_same:
            print(f'Same result!')
        else:
            print(f'Different result!')

        return local_diffs,global_diffs

    def find_candidate_inputs(self,local_vars:Dict[str,object],global_vars:Dict[str,object]):
        local_diffs,global_diffs=self.is_vars_same(local_vars,global_vars)

        pos_args=[]
        for arg in self.args_names.posonlyargs:
            pos_args.append(arg.arg)
        for arg in self.args_names.args:
            pos_args.append(arg.arg)
        var_arg=self.args_names.vararg.arg if self.args_names.vararg else None
        kwonly_args=[]
        for arg in self.args_names.kwonlyargs:
            kwonly_args.append(arg.arg)
        kw_arg=self.args_names.kwarg.arg if self.args_names.kwarg else None

        cand_args:Set[str]=set()
        cand_kwargs:Set[str]=set()
        cand_globals:Set[str]=set()
        if len(local_diffs)!=0:
            print('Mutate local variables...')
            for name,(obj,base_obj) in local_diffs.items():
                if base_obj is None:
                    print(f'New local var {name}: {obj}')
                    # TODO new local var found
                else:
                    print(f'Mutate local var {name}: {base_obj} -> {obj}')
                    # Find the corresponding argument, kwargs, globals
                    for use in self.def_use_chains[name]:
                        if use.split('.')[0] in pos_args:
                            cand_args.add(use)
                        elif use.split('.')[0] in kwonly_args:
                            cand_kwargs.add(use)
                        else:
                            cand_globals.add(use)

        if len(global_diffs)!=0:
            print('Mutate global variables...')
            for name,(obj,base_obj) in global_diffs.items():
                if base_obj is None:
                    print(f'New global var {name}: {obj}')
                    # TODO new global var found
                else:
                    print(f'Mutate global var {name}: {base_obj} -> {obj}')
                    # Find the corresponding argument, kwargs, globals
                    for use in self.def_use_chains[name]:
                        if use.split('.')[0] in pos_args:
                            cand_args.add(use)
                        elif use.split('.')[0] in kwonly_args:
                            cand_kwargs.add(use)
                        else:
                            cand_globals.add(use)

        if len(cand_args)!=0:
            print(f'Candidate args: {cand_args}')
        if len(cand_kwargs)!=0:
            print(f'Candidate kwargs: {cand_kwargs}')
        if len(cand_globals)!=0:
            print(f'Candidate globals: {cand_globals}')

        return cand_args,cand_kwargs,cand_globals
    
    def mutate_object(self,obj:object,name:str,candidate_name:List[str]):
        if name in candidate_name:
            if isinstance(obj,FunctionType) or isinstance(obj,ModuleType) or inspect.isclass(obj) or \
                                                isinstance(obj,partial):
                return obj
            
            print(f'Mutate {name}')
            if isinstance(obj,Enum):
                # For Enum object, select a random value
                candidates=[]
                for elem in obj.__class__:
                    candidates.append(elem)
                index=random.randint(0,len(candidates)-1)
                return candidates[index]
            
            elif isinstance(obj,bool):
                # For boolean object, negatiate the value
                return not obj
            
            elif isinstance(obj,int):
                # For integer object, flip a random bit
                MAX_INT_BIT=64
                bit=random.randint(0,MAX_INT_BIT-1)
                return obj^(1<<bit)
            
            elif isinstance(obj,str):
                # For str object, erase/insert/mutate a random character
                new_str=obj
                MAX_STR_LEN=len(new_str)

                # Erase random characters
                while len(new_str)!=0 and random.randint(0,1)==1:
                    index=random.randint(0,len(new_str)-1)
                    new_str=new_str[:index]+new_str[index+1:]
                
                # Insert random characters
                while len(new_str)<=MAX_STR_LEN and random.randint(0,1)==1:
                    index=random.randint(0,len(new_str))
                    new_str=new_str[:index]+chr(random.randint(0,255))+new_str[index:]

                if new_str!=obj: return new_str

                if len(new_str)==0: return chr(random.randint(0,255))
                else:
                    # Still the same string, mutate a random character
                    index=random.randint(0,len(new_str)-1)
                    return new_str[:index]+chr(random.randint(0,255))+new_str[index+1:]
            
            elif isinstance(obj,bytes):
                # For bytes object, erase/insert/mutate a random character
                new_str=obj
                MAX_STR_LEN=len(new_str)

                # Erase random characters
                while len(new_str)!=0 and random.randint(0,1)==1:
                    index=random.randint(0,len(new_str)-1)
                    new_str=new_str[:index]+new_str[index+1:]
                
                # Insert random characters
                while len(new_str)<=MAX_STR_LEN and random.randint(0,1)==1:
                    index=random.randint(0,len(new_str))
                    new_str=new_str[:index]+bytes(random.randint(0,255))+new_str[index:]

                if new_str!=obj: return new_str

                if len(new_str)==0: return bytes(random.randint(0,255))
                else:
                    # Still the same string, mutate a random character
                    index=random.randint(0,len(new_str)-1)
                    return new_str[:index]+bytes(random.randint(0,255))+new_str[index+1:]
                
            elif isinstance(obj,float):
                # For float object, flip a random bitwise and bytewise
                binary=struct.pack('d',obj)
                index=random.randint(0,63)
                bytewise=index//8
                bitwise=index%8

                new_binary=binary[:bytewise]+bytes([binary[bytewise]^(1<<bitwise)])+binary[bytewise+1:]
                return struct.unpack('d',new_binary)[0]
    
        else:
            continue_mutate=False
            for cand in candidate_name:
                if cand.startswith(name+'.'):
                    continue_mutate=True
                    break

            if continue_mutate and hasattr(obj,'__dict__'):
                # Custom classes
                names=list(getattr(obj,'__dict__').keys())
                for name in names.copy():
                    if is_default_global(self.fn,name,getattr(obj,'__dict__')[name]):
                        names.remove(name)
                
                if len(names)==0:
                    return obj
                index=random.randint(0,len(names)-1)
                key_name=names[index]
                
                if name+'.'+key_name in candidate_name:
                    do_remove=random.randint(0,2)
                else:
                    do_remove=0

                if do_remove==1:
                    delattr(obj,name)
                elif do_remove==2:
                    setattr(obj,name,None)
                else:
                    new_field=self.mutate_object(getattr(obj,'__dict__')[key_name],name+'.'+key_name,candidate_name)
                    setattr(obj,name,new_field)
                return obj

        return obj

    def reproduce(self):
        new_args,new_kwargs,new_globals=deepcopy([self.args,self.kwargs,self.global_vars])

        with open('states.log','w') as f:
            trial=1
            while trial <= 30:
                print(f'Trial {trial}')

                reproduced_local_vars,reproduced_global_vars=self.run(new_args,new_kwargs,new_globals)
                if reproduced_local_vars is None:
                    print(f'Exception not raised, skip!')
                    # Mutate arguments
                    arg_names=list(inspect.signature(self.fn).parameters.keys())
                    for cand_arg in cand_args:
                        arg_name=cand_arg.split('.')[0]
                        if arg_name in arg_names:
                            index=arg_names.index(arg_name)
                            new_args[index]=self.mutate_object(prev_args[index],arg_name,cand_args)
                    # Mutate kwargs
                    for cand_kwarg in cand_kwargs:
                        kwarg_name=cand_kwarg.split('.')[0]
                        if kwarg_name in new_kwargs:
                            new_kwargs[kwarg_name]=self.mutate_object(prev_kwargs[kwarg_name],kwarg_name,cand_kwargs)
                    # Mutate globals
                    for cand_global in cand_globals:
                        global_name=cand_global.split('.')[0]
                        if global_name in new_globals:
                            new_globals[global_name]=self.mutate_object(prev_globals[global_name],global_name,cand_globals)

                    continue

                local_diffs,global_diffs=self.is_vars_same(prune_default_local_var(self.fn,reproduced_local_vars),
                                                        prune_default_global_var(self.fn,reproduced_global_vars))
                if len(local_diffs)==0 and len(global_diffs)==0:
                    print(f'States reproduced in trial {trial}')
                    return
                
                prev_args,prev_kwargs,prev_globals=deepcopy([new_args,new_kwargs,new_globals])
                cur_local_values=dict()
                for name,local in local_diffs.items():
                    cur_local_values[name]=local[0]
                cur_global_values=dict()
                for name,local in global_diffs.items():
                    cur_global_values[name]=local[0]
                self.diffs.append((prev_args,prev_kwargs,prev_globals,cur_local_values,cur_global_values))
                print(f'Trial: {trial}',file=f)
                print(f'Args: {prev_args}',file=f)
                print(f'Kwargs: {prev_kwargs}',file=f)
                print(f'Globals: {prev_globals}',file=f)
                print(f'Local diffs: {cur_local_values}',file=f)
                print(f'Global diffs: {cur_global_values}',file=f)
                
                
                cand_args,cand_kwargs,cand_globals=self.find_candidate_inputs(reproduced_local_vars,reproduced_global_vars)

                # Mutate arguments
                arg_names=list(inspect.signature(self.fn).parameters.keys())
                for cand_arg in cand_args:
                    arg_name=cand_arg.split('.')[0]
                    if arg_name in arg_names:
                        index=arg_names.index(arg_name)
                        new_args[index]=self.mutate_object(new_args[index],arg_name,cand_args)
                # Mutate kwargs
                for cand_kwarg in cand_kwargs:
                    kwarg_name=cand_kwarg.split('.')[0]
                    if kwarg_name in new_kwargs:
                        new_kwargs[kwarg_name]=self.mutate_object(new_kwargs[kwarg_name],kwarg_name,cand_kwargs)
                # Mutate globals
                for cand_global in cand_globals:
                    global_name=cand_global.split('.')[0]
                    if global_name in new_globals:
                        new_globals[global_name]=self.mutate_object(new_globals[global_name],global_name,cand_globals)
                
                print(f'Candidate args: {cand_args}',file=f)
                print(f'Candidate kwargs: {cand_kwargs}',file=f)
                print(f'Candidate globals: {cand_globals}',file=f)
                print('-----------------------------',file=f)
                
                trial+=1

        print(f'Cannot reproduce states!')
        exit(0)