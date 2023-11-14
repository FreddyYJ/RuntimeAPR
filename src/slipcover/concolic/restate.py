from .defusegraph import DefUseGraph
from ..loop.repairutils import PickledObject, SetObject,compare_object, is_default_global, \
    is_default_local, pickle_object, prune_default_global_var, prune_default_local_var

from typing import Dict,List, Set,Tuple
from types import FunctionType
import inspect
from copy import deepcopy
import gast as ast

class StateReproducer:
    def __init__(self,fn:FunctionType,args_names,buggy_local_vars:Dict[str,object],buggy_global_vars:Dict[str,object],
                #  args:List[object],kwargs:Dict[str,object],def_use_chain:List[DefUseGraph.Node]):
                args:List[object],kwargs:Dict[str,object],def_use_chain:Dict[str,List[str]]):
        self.fn=fn
        self.args_names=args_names
        self.buggy_local_vars=prune_default_local_var(self.fn,buggy_local_vars)
        self.buggy_global_vars=prune_default_global_var(self.fn,buggy_global_vars)
        self.args=args
        self.orig_args=args
        self.kwargs=kwargs
        self.orig_kwargs=kwargs
        self.def_use_chains=def_use_chain

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
        
        assert False, 'Should raise exception'
        return dict(),dict()


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
        new_args=deepcopy(self.orig_args)
        new_kwargs=deepcopy(self.orig_kwargs)

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

        # TODO mutate

        return new_args,new_kwargs,global_vars
    
    def reproduce(self):
        new_args=deepcopy(self.args)
        new_kwargs=deepcopy(self.kwargs)
        new_globals=deepcopy(self.buggy_global_vars)

        for trial in range(1,101):
            reproduced_local_vars,reproduced_global_vars=self.run(new_args,new_kwargs,new_globals)

            local_diffs,global_diffs=self.is_vars_same(prune_default_local_var(self.fn,reproduced_local_vars),prune_default_global_var(self.fn,reproduced_global_vars))
            if len(local_diffs)==0 and len(global_diffs)==0:
                print(f'States reproduced in trial {trial}')
                return
            
            new_args,new_kwargs,new_globals=self.find_candidate_inputs(reproduced_local_vars,reproduced_global_vars)

            # TODO run target function to check if the state is same
            exit(0)