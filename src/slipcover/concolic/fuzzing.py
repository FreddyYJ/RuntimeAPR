from copy import copy, deepcopy
import inspect
import pickle
import traceback
from types import FunctionType
from typing import Any, Dict, List, Tuple
import random
import struct

import z3

from .defusegraph import DefUseGraph
from ..configure import Configure
from ..loop.repairutils import PickledObject, SetObject,compare_object, is_default_global, is_default_local, pickle_object, prune_default_global_var, prune_default_local_var
from .ConcolicTracer import ConcolicTracer, symbolize

class Fuzzer:
    def __init__(self,fn:FunctionType,args:List[object],kwargs:Dict[str,object],local_vars:Dict[str,PickledObject],
                 global_vars:Dict[str,PickledObject],exception,excep_line:int,*,skip_global=False) -> None:
        self.args=args
        self.kwargs=kwargs
        self.fn=fn
        self.skip_global=skip_global
        self.local_vars=local_vars
        self.global_vars=global_vars
        self.exception=exception
        self.excep_line=excep_line

        self.def_use_graph:DefUseGraph=DefUseGraph(self.fn)
        self.corpus:List[Tuple[List[object],Dict[str,object],Dict[str,object]]]=[]
        self.candidate_vars:List[str]=[]

    def mutate_object(self,obj:object,prev_name:str,continue_mutate=True):
        if continue_mutate:
            if isinstance(obj,bool):
                continue_mutate=False
                return not obj
            
            elif isinstance(obj,int):
                continue_mutate=False
                binary=format(obj,'b')
                for _ in range(64-len(binary)):
                    binary='0'+binary
                # Select a bit to flip randomly
                index=random.randint(0,63)
                # Flip the bit
                new_binary=binary[:index]+('0' if binary[index]=='1' else '1')+binary[index+1:]
                return int(new_binary,2)
            
            elif isinstance(obj,str):
                continue_mutate=False
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
                continue_mutate=False
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
                continue_mutate=False
                binary=struct.pack('d',obj)
                index=random.randint(0,63)
                bytewise=index//8
                bitwise=index%8

                new_binary=binary[:bytewise]+bytes([binary[bytewise]^(1<<bitwise)])+binary[bytewise+1:]
                return struct.unpack('d',new_binary)[0]
        
            if hasattr(obj,'__dict__'):
                # Custom classes
                names=list(getattr(obj,'__dict__').keys())
                for name in names.copy():
                    if is_default_global(self.fn,name,getattr(obj,'__dict__')[name]):
                        names.remove(name)
                index=random.randint(0,len(names)-1)
                
                new_field=self.mutate_object(getattr(obj,'__dict__')[name],prev_name+'.'+name,continue_mutate=False)
                setattr(obj,name,new_field)
                return obj

        return obj
    
    def _args_mutatible(self,args:List[object]):
        for arg in args:
            if hasattr(arg,'__dict__') and not isinstance(arg,str) and not isinstance(arg,bytes):
                return True
            
        return False

    def mutate(self,local_diff:dict()=None,global_diff:dict()=None):
        index=random.randint(0,len(self.corpus)-1)
        selected_args,selected_kwargs,selected_global_vars=self.corpus[index]
        copy_args,copy_kwargs,copy_global_vars=deepcopy([selected_args,selected_kwargs,selected_global_vars])

        change_args=False
        change_kwargs=False
        change_global=False
        if (local_diff is None and global_diff is None) or (len(local_diff)==0 and len(global_diff)==0):
            if not self._args_mutatible(selected_args) and not self._args_mutatible(list(selected_kwargs.values())):
                change_global=True
            elif not self._args_mutatible(selected_args):
                _rand=random.randint(0,1)
                if _rand==0:
                    change_global=True
                else:
                    change_kwargs=True
            elif not self._args_mutatible(list(selected_kwargs.values())):
                _rand=random.randint(0,1)
                if _rand==0:
                    change_global=True
                else:
                    change_args=True
            else:
                # Mutate random vars
                _rand=random.randint(0,2)
                if _rand==0:
                    change_args=True
                elif _rand==1:
                    change_kwargs=True
                else:
                    change_global=True

        elif len(global_diff)!=0 and len(local_diff)!=0:
            change_global=True
            if not self._args_mutatible(selected_args) and self._args_mutatible(list(selected_kwargs.values())):
                change_kwargs=True
            elif self._args_mutatible(selected_args) and not self._args_mutatible(list(selected_kwargs.values())):
                change_args=True
            elif self._args_mutatible(selected_args) and self._args_mutatible(list(selected_kwargs.values())):
                _rand=random.randint(0,1)
                if _rand==0:
                    change_args=True
                else:
                    change_kwargs=True

        elif len(local_diff)!=0:
            if not self._args_mutatible(selected_args) and self._args_mutatible(list(selected_kwargs.values())):
                change_kwargs=True
            elif self._args_mutatible(selected_args) and not self._args_mutatible(list(selected_kwargs.values())):
                change_args=True
            else:
                _rand=random.randint(0,1)
                if _rand==0:
                    change_args=True
                else:
                    change_kwargs=True

        elif len(global_diff)!=0:
            change_global=True
        
        # Mutate the arguments
        if change_args:
            arg_names=list(inspect.signature(self.fn).parameters.keys())
            for i,arg in enumerate(copy_args):
                if is_default_local(self.fn,f'arg{i}',arg):
                    # Do not mutate default arguments
                    continue
                
                if hasattr(arg,'__dict__'):
                    for name,field in getattr(arg,'__dict__').items():
                        if not is_default_local(self.fn,name,field):
                            new_field=self.mutate_object(field,arg_names[i]+'.'+name)
                            setattr(arg,name,new_field)

        if change_kwargs:
            # Mutate the keyword arguments
            for name,arg in copy_kwargs.items():
                if is_default_local(self.fn,name,arg):
                    # Do not mutate default arguments
                    continue

                if hasattr(arg,'__dict__'):
                    for name2,field in getattr(arg,'__dict__').items():
                        if not is_default_local(self.fn,name2,field):
                            new_field=self.mutate_object(field,name+'.'+name2)
                            setattr(arg,name2,new_field)

        if change_global:
            # Mutate the global variables
            if not self.skip_global:
                candidate_vars=[]
                for name,arg in copy_global_vars.items():
                    if is_default_global(self.fn,name,arg):
                        # Do not mutate default arguments
                        continue

                    candidate_vars.append(name)
                
                random.shuffle(candidate_vars)
                copy_global_vars[candidate_vars[0]]=self.mutate_object(copy_global_vars[candidate_vars[0]],candidate_vars[0])

        return copy_args,copy_kwargs,copy_global_vars

    def fuzz(self):
        new_args=self.args
        new_kwargs=self.kwargs
        new_global_vars=self.global_vars
        self.corpus.append((new_args,new_kwargs,new_global_vars,))

        trial=1
        while True:
            print(f'Trial: {trial}')
            trial+=1

            path,local_vars,global_vars,exc,line=self.run(new_args,new_kwargs,new_global_vars)

            if isinstance(exc,type(self.exception)) and self.excep_line==line:
                print('Exception raised, stop fuzzing.')
                return new_args,new_kwargs,new_global_vars

            if len(local_vars)!=0 or len(global_vars)!=0:
                is_same,local_diffs,global_diffs=self.is_vars_same(local_vars,global_vars)            
                if is_same:
                    print('All states same, but exception not raised.')
            else:
                print('No exception thrown, add this args to corpus.')
                new_args,new_kwargs,new_global_vars=self.mutate()
                continue
                
            # TODO: def-use chain
            for name,value in local_diffs.items():
                if name not in self.candidate_vars:
                    self.candidate_vars.append(name)
                    print(f'Add candidate variable {name}')
            for name,value in global_diffs.items():
                if name not in self.candidate_vars:
                    self.candidate_vars.append(name)
                    print(f'Add candidate variable {name}')

            if exc is not None:
                # TODO: loss function
                self.corpus.append((new_args,new_kwargs,new_global_vars,))
            new_args,new_kwargs,new_global_vars=self.mutate(local_diffs,global_diffs)

    def is_vars_same(self,local_vars,global_vars):
        is_same=True
        local_diffs:Dict[str,Tuple[object]]=dict()
        global_diffs:Dict[str,Tuple[object]]=dict()

        print('Compare local variables...')
        for name,obj in local_vars.items():
            if is_default_local(self.fn,name,obj):
                continue

            if name not in self.local_vars:
                is_same=False
                print(f'New local var {name}: {obj}')
                local_diffs[name]=(obj,None)
                continue
            
            _obj=pickle_object(self.fn,name,obj)
            if _obj is not None:
                _is_same=compare_object(_obj,self.local_vars[name])
                if not _is_same:
                    local_diffs[name]=(_obj,self.local_vars[name])
                if is_same:
                    is_same=_is_same
            else:
                is_same=False
            # if not is_same:
            #     break

        # if is_same and not self.skip_global:
        if not self.skip_global:
            print('Compare global variables...')
            for name,obj in global_vars.items():
                if is_default_global(self.fn,name,obj):
                    continue

                if name not in self.global_vars:
                    # is_same=False
                    print(f'New global var {name}: {obj}')
                    global_diffs[name]=(obj,None)
                    continue

                _obj=pickle_object(self.fn,name,obj,is_global=True)
                if _obj is not None:
                    _is_same=compare_object(_obj,self.global_vars[name])
                    if not _is_same:
                        global_diffs[name]=(_obj,self.global_vars[name])
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

        return is_same,local_diffs,global_diffs

    def run(self,new_args:List[object],new_kwargs:Dict[str,object],new_globals:Dict[str,object]) \
                 -> Tuple[List[z3.BoolRef],Dict[str,object],Dict[str,object]]:
        """
        Run concolic execution with given values.
        If some global or arguments are not in before_values, use the latest value.
        :param before_values: values to try in this concolic execution
        :return: z3 path constraints, local variables after execution, global variables after execution
        """
        with ConcolicTracer() as tracer:
            """
                Note: We do not symbolize arguments.
                Now, we assume that the heap of the arguments are changed, but arguments itself are not changed.
                e.g. Possible cases: arg.field changed
                     Impossible cases: arg = 0 to arg = 1
            """
            args,kwargs,globals=deepcopy([new_args,new_kwargs,new_globals])
            for name,obj in globals.items():
                self.fn.__globals__[name]=obj

            try:
                global is_concolic_execution
                is_concolic_execution=True
                result=self.fn(*args, **kwargs)
            except Exception as _exc:
                print(f'Exception raised: {type(_exc)}: {_exc}')
                traceback.print_exception(type(_exc),_exc,_exc.__traceback__)
                if Configure.debug:
                    print(f'Decls: {tracer.decls}')
                print(f'Path: {tracer.path}')

                tb=_exc.__traceback__
                info=inspect.getinnerframes(tb)[1]
                return tracer.path,info.frame.f_locals,info.frame.f_globals,_exc,_exc.__traceback__.tb_lineno
            
            if Configure.debug:
                print(f'Decls: {tracer.decls}')
            print(f'Path: {tracer.path}')
            # self.tried_paths.add(z3.simplify(z3.And(*tracer.path)))
            return tracer.path,dict(),dict(),None,-1
