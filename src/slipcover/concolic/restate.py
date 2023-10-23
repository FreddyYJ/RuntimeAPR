from .defusegraph import DefUseGraph
from ..loop.repairutils import PickledObject, SetObject,compare_object, is_default_global, \
    is_default_local, pickle_object, prune_default_global_var, prune_default_local_var

from typing import Dict,List, Set,Tuple
from types import FunctionType
import inspect
from copy import deepcopy
import gast as ast

class StateReproducer:
    def __init__(self,fn:FunctionType,buggy_local_vars:Dict[str,object],buggy_global_vars:Dict[str,object],
                 args:List[object],kwargs:Dict[str,object],def_use_chain:List[DefUseGraph.Node]):
        self.fn=fn
        self.buggy_local_vars=buggy_local_vars
        self.buggy_global_vars=buggy_global_vars
        self.args=args
        self.orig_args=args
        self.kwargs=kwargs
        self.orig_kwargs=kwargs
        self.def_use_chains=def_use_chain

        self.reproduced_local_vars,self.reproduced_global_vars=self.run(args,kwargs,buggy_global_vars)

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

    def mutate(self,local_vars:Dict[str,object],global_vars:Dict[str,object]):
        local_diffs,global_diffs=self.is_vars_same(local_vars,global_vars)
        new_args=deepcopy(self.orig_args)
        new_kwargs=deepcopy(self.orig_kwargs)

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
                    for define in self.def_use_chains:
                        _cand=self._find_use(define,name)
                        if _cand is not None:
                            if _cand not in cand_args:
                                cand_args.add(_cand.node.id)
                            elif _cand not in cand_kwargs:
                                cand_kwargs.add(_cand.node.id)
                            else:
                                cand_globals.add(_cand.node.id)

        if len(cand_args)!=0:
            print(f'Candidate args: {cand_args}')
        if len(cand_kwargs)!=0:
            print(f'Candidate kwargs: {cand_kwargs}')
        if len(cand_globals)!=0:
            print(f'Candidate globals: {cand_globals}')

        # TODO mutate

        return new_args,new_kwargs,global_vars
                        
    def _find_use(self,node:DefUseGraph.Node,name:str):
        if isinstance(node.node,ast.gast.Name):
            if node.node.id ==name:
                # Found
                return node
            
        # Try children
        for child in node.children:
            result=self._find_use(child,name)
            if result is not None:
                return result
        return None
    
    def reproduce(self):
        for trial in range(1,101):
            new_args,new_kwargs,new_globals=self.mutate(self.reproduced_local_vars,self.reproduced_global_vars)

            # TODO run target function to check if the state is same
            exit(0)