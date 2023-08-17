import inspect
import os
import sys
from types import FrameType, FunctionType, MethodType
from typing import Any, Dict, List, Set, Tuple, Union
import ast

import z3
from bytecode import Bytecode
import gc

from .funcast import FunctionFinderVisitor
from .repairutils import BugInformation,prune_default_global_var,is_default_global,compare_object,pickle_object
from ..concolic import ConcolicTracer,get_zvalue,zint,symbolize,ControlDependenceGraph,Block,ConditionTree,ConditionNode

import pickle

class RepairloopRunner:
    def __init__(self, fn:FunctionType, args, kwargs, bug_info:BugInformation):
        """
        :param fn: function to run
        :param args: arguments to pass to the function
        :param kwargs: keyword arguments to pass to the function
        :param local_vars: local variables from buggy function
        :param global_vars: global variables from buggy function
        """
        self.fn=fn
        self.args=args
        self.kwargs=kwargs
        self.bug_info=bug_info
        self.global_vars_without_default=prune_default_global_var(fn,bug_info.global_vars)
        self.tried_paths:Set[z3.ExprRef]=set()
        self.persistent_path:Set[z3.BoolRef]=set()
        print(f'Global vars: {self.global_vars_without_default}')
        self.cfg=ControlDependenceGraph(self.fn)
        self.cond_tree:ConditionTree=ConditionTree(self.cfg.cfg)
        self.skip_global:bool=False # Skip global variables

        # To record local and global variables at target function return
        self.target_locals:Dict[str,object]=dict()
        self.target_globals:Dict[str,object]=dict()

        # Save object states in the file, for the debug
        self.save_states_file:str=os.environ.get('APR_SAVE_FILE','/dev/null')
        self.is_append=False

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
            if not self.skip_global:
                pruned_globals=prune_default_global_var(self.fn,self.fn.__globals__)
                for name,obj in self.fn.__globals__.items():
                    if name in pruned_globals:
                        new_globals[name]=symbolize(tracer.context,name,obj,before_values)
                for name,obj in new_globals.items():
                    self.fn.__globals__[name]=obj

            print(f'original args: {self.args}')
            print(f'args: {new_args}')
            if not self.skip_global:
                print(f'original globals: {prune_default_global_var(self.fn,self.fn.__globals__)}')
                print(f'globals: {prune_default_global_var(self.fn,new_globals)}')

            try:
                sys.settrace(self.traceit)
                result=self.fn(*new_args, **self.kwargs)
                sys.settrace(None)
            except Exception as _exc:
                sys.settrace(None)
                print(f'Decls: {tracer.decls}')
                print(f'Path: {tracer.path}')

                tb=_exc.__traceback__
                info=inspect.getinnerframes(tb)[1]
                return tracer.path,info.frame.f_locals,info.frame.f_globals
            
            print(f'Decls: {tracer.decls}')
            print(f'Path: {tracer.path}')
            # self.tried_paths.add(z3.simplify(z3.And(*tracer.path)))
            return tracer.path,self.target_locals,self.target_globals
            
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
                elif isinstance(cur_value,z3.RatNumRef):
                    values[model[i].name()]=float(cur_value.as_decimal(10))
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
            self.trial+=1
            print(f'Trial {self.trial}...')
            cur_paths,cur_locals,cur_globals=self.run_concolic(before_values)
            
            if len(cur_paths)==0:
                # Only one path (current path)
                print('No more paths to try, return current values.')
                is_same=True
            else:
                self.cond_tree.update_tree(cur_paths)

            if not is_same:
                if len(cur_locals)!=0 or len(cur_globals)!=0:
                    is_same=self.is_vars_same(cur_locals,cur_globals)
            else:
                if len(cur_locals)!=0 or len(cur_globals)!=0:
                    self.is_vars_same(cur_locals,cur_globals)
                    
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
        self.trial=0
        MAX_TRIAL=10
        print(f'Function throws an exception: {from_error}, move to repair loop.')
        while not is_same:
            if self.trial>MAX_TRIAL:
                print("Max trial 100 reached. Stop.")
                break

            print('Get buggy inputs and states...')
            buggy_values=self.get_buggy_values()
            exit(0)
            
        if is_same:
            print(f'Same result after {self.trial} trials.')

        # TODO: Repair a crash, execute repaired function with original inputs and return the result
        exit(0)
        return 'Finished'
    
    def traceit(self,frame: FrameType, event: str, arg: Any):
        if event=='return':
            self.target_locals=frame.f_locals.copy()
            self.target_globals=frame.f_globals.copy()

        return self.traceit

    def is_vars_same(self,local_vars,global_vars):
        is_same=True
        if self.is_append:
            save_file=open(self.save_states_file,'a')
        else:
            save_file=open(self.save_states_file,'w')
            self.is_append=True
        save_file.write(f'Trial {self.trial}:\n')

        save_file.write(f'Local vars:\n')
        print('Compare local variables...')
        for name,obj in local_vars.items():
            try:
                if name not in self.bug_info.local_vars:
                    is_same=False
                    print(f'New local var {name}: {obj}')
                    save_file.write(f'New local var {name}: {type(obj)}: {pickle_object(self.fn,name,obj)}\n')
                    break
                
                _obj=pickle_object(self.fn,name,obj)
                if _obj is not None:
                    _is_same=compare_object(_obj,self.bug_info.local_vars[name])
                    if is_same:
                        is_same=_is_same
                    if _is_same:
                        save_file.write(f'Same local vars {name}: {type(obj)}: {_obj}\n')
                    else:
                        save_file.write(f'Different local vars {name}\n{type(obj)}: {_obj} and\n'
                                        f'{type(self.bug_info.local_vars[name])}: {self.bug_info.local_vars[name]}\n')
                else:
                    is_same=False
                # if not is_same:
                #     break
            except ValueError:
                print(f'Cannot pickle {name}: {obj}')
                continue

        # if is_same and not self.skip_global:
        if not self.skip_global:
            save_file.write(f'-----------------------\nGlobal vars:\n')
            print('Compare global variables...')
            for name,obj in global_vars.items():
                if is_default_global(self.fn,name,obj):
                    continue

                if name not in self.global_vars_without_default:
                    # is_same=False
                    print(f'New global var {name}: {obj}')
                    save_file.write(f'New global var {name}: {type(obj)}: {pickle_object(self.fn,name,obj)}\n')
                    break
                _obj=pickle_object(self.fn,name,obj)
                if _obj is not None:
                    _is_same=compare_object(_obj,self.global_vars_without_default[name])
                    if is_same:
                        is_same=_is_same
                    if _is_same:
                        save_file.write(f'Same global vars {name}: {type(obj)}: {_obj}\n')
                    else:
                        save_file.write(f'Different global vars {name}\n{type(obj)}: {_obj} and\n'
                                        f'{type(self.global_vars_without_default[name])}: {self.global_vars_without_default[name]}\n')
                else:
                    is_same=False
                # if not is_same:
                #     break

        save_file.write('\n')
        save_file.close()
        if is_same:
            print(f'Same result!')
        else:
            print(f'Different result!')

        return is_same
    
def except_handler(e:Exception):
    innerframes=inspect.getinnerframes(e.__traceback__)
    info:inspect.FrameInfo=innerframes[0]
    inner_info:inspect.FrameInfo=innerframes[1]
    
    objects=gc.get_referrers(inner_info.frame.f_code)
    for obj in objects:
        if isinstance(obj,FunctionType) and obj.__name__==inner_info.function:
            func=obj
            break
    
    assert func is not None,f'Cannot find function {inner_info.function} at line {inner_info.lineno}'

    with open(inner_info.filename,'r') as file:
        func_ast=ast.parse(file.read(),inner_info.filename,'exec')
    visitor=FunctionFinderVisitor(inner_info.lineno)
    visitor.visit(func_ast)
    target_func=visitor.get_funcs()
    args=target_func.args
    # print(args.args[0].arg)
    # print(args.posonlyargs)
    # print(args.kwonlyargs[0].arg)
    # print(args.vararg.arg)

    pos_args=[]
    for arg in args.posonlyargs:
        pos_args.append(arg.arg)
    norm_args=[]
    for arg in args.args:
        norm_args.append(arg.arg)
    var_arg=args.vararg.arg if args.vararg else None
    kwonly_args=[]
    for arg in args.kwonlyargs:
        kwonly_args.append(arg.arg)
    kw_arg=args.kwarg.arg if args.kwarg else None
    # func(pos_args, /, norm_args, *var_arg | *, kwonly_args, **kw_arg)
    
    bc=Bytecode.from_code(inner_info.frame.f_code)
    arg_names=bc.argnames
    # print(arg_names)
    # print(inner_info.frame.f_locals)
    pos_only=[]
    for arg in pos_args:
        if arg in inner_info.frame.f_locals:
            pos_only.append(inner_info.frame.f_locals[arg])
    norms=[]
    for arg in norm_args:
        if arg in inner_info.frame.f_locals:
            norms.append(inner_info.frame.f_locals[arg])
    vargs=[]
    if var_arg and var_arg in inner_info.frame.f_locals:
        assert isinstance(inner_info.frame.f_locals[var_arg],tuple)
        for element in inner_info.frame.f_locals[var_arg]:
            vargs.append(element)
    kwonlys={}
    for arg in kwonly_args:
        if arg in inner_info.frame.f_locals:
            kwonlys[arg]=inner_info.frame.f_locals[arg]
    kws={}
    if kw_arg and kw_arg in inner_info.frame.f_locals:
        assert isinstance(inner_info.frame.f_locals[kw_arg],dict)
        for k,v in inner_info.frame.f_locals[kw_arg].items():
            kws[k]=v
    kwonlys.update(kws)

    print(f'Args: {pos_only+norms+vargs}')
    print(f'Kwargs: {kwonlys}')
    bug_info=BugInformation(inner_info.lineno,inner_info.function,
                            inner_info.frame.f_locals.copy(),inner_info.frame.f_globals.copy())
    for name,obj in inner_info.frame.f_locals.copy().items():
        _obj=pickle_object(func,name,obj)
        if _obj is not None:
            bug_info.local_vars[name]=_obj
    for name,obj in prune_default_global_var(func,inner_info.frame.f_globals.copy()).items():
        _obj=pickle_object(func,name,obj)
        if _obj is not None:
            bug_info.global_vars[name]=_obj
    runner=RepairloopRunner(func,(pos_only+norms+vargs),kwonlys,bug_info)
    return runner.loop(e)