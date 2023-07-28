import inspect
import pickle
import sys
from types import FrameType, FunctionType
from typing import Any, Dict, List, Set, Tuple
import ast

import z3

from .repairutils import BugInformation,prune_default_global_var,is_default_global
from .develoop import RedirectDeveloopRunner
from ..concolic import ConcolicTracer,get_zvalue,zint,symbolize,ControlDependenceGraph,Block,ConditionTree,ConditionNode

class RepairloopRunner(RedirectDeveloopRunner):
    def __init__(self, fn:FunctionType, args, kwargs, bug_info:BugInformation):
        """
        :param fn: function to run
        :param args: arguments to pass to the function
        :param kwargs: keyword arguments to pass to the function
        :param local_vars: local variables from buggy function
        :param global_vars: global variables from buggy function
        """
        super().__init__(fn, args, kwargs)
        self.bug_info=bug_info
        self.global_vars_without_default=prune_default_global_var(fn,bug_info.global_vars)
        self.tried_paths:Set[z3.ExprRef]=set()
        self.persistent_path:Set[z3.BoolRef]=set()
        print(f'Global vars: {self.global_vars_without_default}')
        self.cfg=ControlDependenceGraph(self.fn)
        self.cond_tree:ConditionTree=ConditionTree(self.cfg.cfg)

    def run_concolic(self,before_values:Dict[str,Any]) -> Tuple[List[z3.BoolRef],Dict[str,object],Dict[str,object]]:
        """
        Run concolic execution with given values.
        If some global or arguments are not in before_values, use the latest value.
        :param before_values: values to try in this concolic execution
        :return: z3 path constraints, local variables after execution, global variables after execution
        """
        with ConcolicTracer() as tracer:
            # Symbolize the arguments
            new_args=list(self.args)
            arg_names=list(inspect.signature(self.fn).parameters.keys())
            for name,obj in zip(arg_names,self.args):
                new_args[arg_names.index(name)]=symbolize(tracer.context,name,obj,before_values)

            # Symbolize the global variables
            new_globals=dict(self.fn.__globals__)
            pruned_globals=prune_default_global_var(self.fn,self.fn.__globals__)
            for name,obj in self.fn.__globals__.items():
                if name in pruned_globals:
                    new_globals[name]=symbolize(tracer.context,name,obj,before_values)
            for name,obj in new_globals.items():
                self.fn.__globals__[name]=obj

            print(f'original args: {self.args}')
            print(f'args: {new_args}')
            print(f'original globals: {prune_default_global_var(self.fn,self.fn.__globals__)}')
            print(f'globals: {prune_default_global_var(self.fn,new_globals)}')

            try:
                # result= tracer[self.fn](*new_args, **kwargs)
                # self.executed_lines=[6, 7, 10]
                self.executed_lines=[]
                sys.settrace(self.traceit)
                result=self.fn(*new_args, **self.kwargs)
                sys.settrace(None)
                print(f'Lines: {self.executed_lines}')
            except Exception as _exc:
                sys.settrace(None)
                print(f'Lines: {self.executed_lines}')
                print(f'Decls: {tracer.decls}')
                print(f'Path: {tracer.path}')
                # self.tried_paths.add(z3.simplify(z3.And(*tracer.path)))

                tb=_exc.__traceback__
                info=inspect.getinnerframes(tb)[1]
                return tracer.path,info.frame.f_locals,info.frame.f_globals
            
            print(f'Decls: {tracer.decls}')
            print(f'Path: {tracer.path}')
            # self.tried_paths.add(z3.simplify(z3.And(*tracer.path)))
            return tracer.path,dict(),dict()
            
    def get_z3_values(self,path):
        """
        Compute values from z3 path constraints.
        :param path: list of z3 path constraints
        :return: values of variables
        """
        solver=z3.Solver()
        solver.add(path)
        # for pers_path in self.persistent_path:
        #     solver.add(pers_path)
        
        if solver.check()==z3.unsat:
            print(f'Not solvable: {path}')
            return None
        
        model=solver.model()
        print(f'Model: {model}')
        values:Dict[str,object]=dict()

        for i in range(len(model)):
            if isinstance(model[i],z3.FuncDeclRef):
                cur_value=model[model[i]]
                # TODO: Add more types
                if isinstance(cur_value,z3.IntNumRef):
                    values[model[i].name()]=cur_value.as_long()
                elif isinstance(cur_value,z3.BoolRef):
                    values[model[i].name()]=cur_value.arg(0)
                elif isinstance(cur_value,z3.SeqRef):
                    values[model[i].name()]=cur_value.as_string()
                else:
                    values[model[i].name()]=cur_value

        print(f'Values: {values}')
        return values
            
    def get_buggy_values(self):
        """
        Get buggy values of arguments and global variables.
        Keep running concolic execution until the values are the same as buggy values.
        :return: buggy values of arguments and global variables
        """
        is_same=False
        paths=list()
        before_values:Dict[str,object]=dict()

        while not is_same:
            cur_paths,cur_locals,cur_globals=self.run_concolic(before_values)
            
            self.cond_tree.update_tree(cur_paths)

            if len(cur_locals)!=0 or len(cur_globals)!=0:
                is_same=self.is_vars_same(cur_locals,cur_globals)

            if not is_same:
                # If values are different, try to negate the path
                # Combine all paths into multiple Ands
                simple_path=z3.simplify(z3.And(*cur_paths))

                self.cond_tree.update_unreachable_conds(self.bug_info.buggy_line)
                print(f'Condition tree:\n{self.cond_tree}')

                before_values=None
                while before_values is None:
                    # Negate the path
                    new_path=self.cond_tree.get_path()
                    assert new_path is not None,f'Failed to negate {simple_path}'

                    # Solve the SMT and get the values
                    before_values=self.get_z3_values(new_path)
                    if before_values is None:
                        # If the path is not solvable, try another path
                        self.cond_tree.update_tree(new_path)
            else:
                # Otherwise, return the buggy values
                return before_values
    
    def find_unreachable_path(self,unreachable_path:Block,branch:Block,condition:z3.BoolRef):
        if isinstance(branch.statements[-1],ast.If) or isinstance(branch.statements[-1],ast.While):
            print(f'Unreachable: {z3.Not(condition)}')
            self.persistent_path.add(z3.Not(condition))
        elif isinstance(branch.statements[-1],ast.For):
            # TODO: Handle for loop
            pass

    def run(self,new_global_vars=None):
        """
        Run the function and return local and global variables if crashes
        """
        if new_global_vars is not None:
            for name in new_global_vars:
                self.fn.__globals__[name]=new_global_vars[name]
        try:
            self.fn(*self.args, **self.kwargs)
        except Exception as e:
            tb=e.__traceback__
            info=inspect.getinnerframes(tb)[1]
            return info.frame.f_locals, prune_default_global_var(self.fn,info.frame.f_globals)

        return (dict(),dict())
    
    def loop(self,from_error:Exception=None):
        """
        Run the function and compare variables with buggy
        """
        is_same=False
        trial=0
        MAX_TRIAL=10
        print(f'Function throws an exception: {from_error}, move to repair loop.')
        while not is_same:
            trial+=1
            print(f'Trial {trial}...')
            if trial>MAX_TRIAL:
                print("Max trial 100 reached. Stop.")
                break

            print('Get buggy inputs and states...')
            buggy_values=self.get_buggy_values()
            exit(0)
            
        if is_same:
            print(f'Same result after {trial} trials.')

        # TODO: Repair a crash, execute repaired function with original inputs and return the result
        exit(0)
        return 'Finished'
    
    def traceit(self,frame: FrameType, event: str, arg: Any):
        if event == 'line':
            function_name = frame.f_code.co_name
            lineno = frame.f_lineno
            if function_name==self.bug_info.buggy_func:
                self.executed_lines.append(lineno)

        return self.traceit

    def is_vars_same(self,local_vars,global_vars):
        is_same=True
        print('Compare local variables...')
        for name,obj in local_vars.items():
            try:
                # Ignore z3 objects
                if type(obj).__name__.startswith('z'):
                    continue
                if name not in self.bug_info.local_vars:
                    is_same=False
                    print(f'New local var {name}: {obj}')
                    break
                elif pickle.dumps(obj)!=pickle.dumps(self.bug_info.local_vars[name]):
                    is_same=False
                    print(f'Different local var {name}: {obj} vs {self.bug_info.local_vars[name]}')
                    break
            except ValueError:
                print(f'Cannot pickle {name}: {obj}')
                continue

        if is_same:
            print('Compare global variables...')
            for name,obj in global_vars.items():
                if is_default_global(self.fn,name,obj):
                    continue
                # Ignore z3 objects
                if type(obj).__name__.startswith('z'):
                    continue

                if name not in self.global_vars_without_default:
                    # is_same=False
                    print(f'New global var {name}: {obj}')
                    break

                try:
                    obj_dumped=pickle.dumps(obj)
                except Exception as e:
                    # TODO: Handle unpickable objects (C-level objects)
                    print(f'Cannot pickle {name}: {obj}')
                    continue
                
                if obj_dumped!=pickle.dumps(self.global_vars_without_default[name]):
                    is_same=False
                    print(f'Different global var {name}: {obj} vs {self.global_vars_without_default[name]}')
                    break

        if is_same:
            print(f'Same result!')
        else:
            print(f'Different result!')

        return is_same