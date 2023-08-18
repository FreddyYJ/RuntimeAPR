import ast
from typing import List, Set
from .model import CFG,Block
import z3
import random

__node_print_count__=0

class ConditionNode:
    def __init__(self,lineno:int,condition:z3.BoolRef,parent_node:Block=None,child_node:Block=None) -> None:
        self.lineno=lineno
        self.condition=condition
        self.true_child:ConditionNode=None
        self.false_child:ConditionNode=None
        self.parent_node:Block=parent_node
        self.child_node:Block=child_node
        self.reachable:bool=True
    
    def __eq__(self, __value: object) -> bool:
        return self.lineno==__value.lineno and self.condition==__value.condition
    
    def __str__(self) -> str:
        global __node_print_count__
        s=f'Node: line: {self.lineno}, condition: {self.condition}, reachable: {self.reachable}\n'
        __node_print_count__+=1
        if self.true_child is not None:
            for _ in range(__node_print_count__):
                s+='   '
            s+=f'True: {self.true_child.__str__()}\n'
        else:
            for _ in range(__node_print_count__):
                s+='   '
            s+='True: None\n'
        
        if self.false_child is not None:
            for _ in range(__node_print_count__):
                s+='   '
            s+=f'False: {self.false_child.__str__()}'
        else:
            for _ in range(__node_print_count__):
                s+='   '
            s+='False: None'
        
        __node_print_count__-=1
        return s

class ConditionTree:
    def __init__(self,cfg:CFG) -> None:
        self.cfg=cfg
        self.true_entry:ConditionNode=None
        self.false_entry:ConditionNode=None

    def __visit_to_update(self,node:ConditionNode,cfg_node:Block,conditions:List[z3.BoolRef],cond_index:int):
        # Last statement of the block should be branch statement
        if isinstance(cfg_node.statements[-1],ast.If) or isinstance(cfg_node.statements[-1],ast.While) or \
                isinstance(cfg_node.statements[-1],ast.IfExp):
            next_cond=conditions[cond_index]

            if not str(next_cond).startswith('Not'):
                # True branch
                if node.true_child is None:
                    node.true_child=ConditionNode(cfg_node.exits[0].target.at(),next_cond,cfg_node,cfg_node.exits[0].target)
                self.__visit_to_update(node.true_child,cfg_node.exits[0].target,conditions,cond_index+1)
            else:
                # False branch
                if node.false_child is None:
                    # Only one branch exist if false branch is function end
                    if len(cfg_node.exits)>=2:
                        node.false_child=ConditionNode(cfg_node.exits[1].target.at(),next_cond,cfg_node,cfg_node.exits[1].target)
                    else:
                        node.false_child=ConditionNode(-1,next_cond,cfg_node)
                if len(cfg_node.exits)>=2:
                    self.__visit_to_update(node.false_child,cfg_node.exits[1].target,conditions,cond_index+1)
        elif isinstance(cfg_node.statements[-1],ast.For):
            next_cond=conditions[cond_index]
            cond_lineno=next_cond.cond_lineno
            if cfg_node.statements[-1].lineno<=cond_lineno<=cfg_node.statements[-1].end_lineno:
                # Go to body
                if node.true_child is None:
                    # Create dummy node with None condition
                    node.true_child=ConditionNode(cfg_node.exits[0].target.at(),None,cfg_node,cfg_node.exits[0].target)
                self.__visit_to_update(node.true_child,cfg_node.exits[0].target,conditions,cond_index)
            else:
                # Exit for statement
                if node.false_child is None:
                    if len(cfg_node.exits)>=2:
                        node.false_child=ConditionNode(cfg_node.exits[1].target.at(),None,cfg_node,cfg_node.exits[1].target)
                    else:
                        node.false_child=ConditionNode(-1,None,cfg_node)
                if len(cfg_node.exits)>=2:
                    self.__visit_to_update(node.false_child,cfg_node.exits[1].target,conditions,cond_index)
        elif len(cfg_node.exits)>0:
            self.__visit_to_update(node,cfg_node.exits[0].target,conditions,cond_index)

    def update_tree(self,conditions:List[z3.BoolRef]):
        current_cfg_node:Block=self.cfg.entryblock
        current_cond:z3.BoolRef=conditions[0]
        while True:
            # Last statement of the block should be branch statement
            if isinstance(current_cfg_node.statements[-1],ast.If) or isinstance(current_cfg_node.statements[-1],ast.While) or \
                    isinstance(current_cfg_node.statements[-1],ast.IfExp):
                if not str(current_cond).startswith('Not'):
                    # True branch
                    if self.true_entry is None:
                        self.true_entry=ConditionNode(current_cfg_node.exits[0].target.at(),current_cond,current_cfg_node,current_cfg_node.exits[0].target)
                    self.__visit_to_update(self.true_entry,current_cfg_node.exits[0].target,conditions,1)
                    break
                else:
                    # False branch
                    if self.false_entry is None:
                        if len(current_cfg_node.exits)>=2:
                            self.false_entry=ConditionNode(current_cfg_node.exits[1].target.at(),current_cond,current_cfg_node,current_cfg_node.exits[1].target)
                        else:
                            self.false_entry=ConditionNode(-1,current_cond,current_cfg_node)
                    if len(current_cfg_node.exits)>=2:
                        self.__visit_to_update(self.false_entry,current_cfg_node.exits[1].target,conditions,1)
                    break
            elif isinstance(current_cfg_node.statements[-1],ast.For):
                cond_lineno=current_cond.cond_lineno
                if current_cfg_node.statements[-1].lineno<=cond_lineno<=current_cfg_node.statements[-1].end_lineno:
                    # Go to body
                    if self.true_entry is None:
                        # Create dummy node with None condition
                        self.true_entry=ConditionNode(current_cfg_node.exits[0].target.at(),None,current_cfg_node,current_cfg_node.exits[0].target)
                    self.__visit_to_update(self.true_entry,current_cfg_node.exits[0].target,conditions,0)
                    break
                else:
                    # Exit for statement
                    if self.false_entry is None:
                        if len(current_cfg_node.exits)>=2:
                            self.false_entry=ConditionNode(current_cfg_node.exits[1].target.at(),None,current_cfg_node,current_cfg_node.exits[1].target)
                        else:
                            self.false_entry=ConditionNode(-1,None,current_cfg_node)
                    if len(current_cfg_node.exits)>=2:
                        self.__visit_to_update(self.false_entry,current_cfg_node.exits[1].target,conditions,0)
                    break
            else:
                current_cfg_node=current_cfg_node.exits[0].target

    def __visit_path_dfs(self,node:ConditionNode,paths:List[z3.BoolRef]):
        if (node.true_child is None and node.false_child is None) or \
            (node.true_child is not None and node.false_child is not None and not node.true_child.reachable and not node.false_child.reachable):
            # We already tried this path, select another path
            return False
        
        if node.true_child is not None:
            if node.true_child.reachable:
                # Try to visit true branch
                if node.true_child.condition is not None:
                    paths.append(node.true_child.condition)
                is_return=self.__visit_path_dfs(node.true_child,paths)
                if is_return:
                    # We found the path, stop searching
                    return True
                else:
                    # We didn't find the path, remove the path
                    if node.true_child.condition is not None:
                        paths.pop()
        else:
            # Only false branch exist, select true branch
            if node.false_child.condition is not None:
                paths.append(node.false_child.condition.arg(0))
            return True
        
        if node.false_child is None:
            # Only true branch exist, select false branch
            if node.true_child.condition is not None:
                paths.append(z3.Not(node.true_child.condition))
            return True
        else:
            if node.false_child.reachable:
                # Try to visit false branch, if true branch is not the path or not exist
                if node.false_child.condition is not None:
                    paths.append(node.false_child.condition)
                is_return=self.__visit_path_dfs(node.false_child,paths)
                if is_return:
                    # We found the path, stop searching
                    return True
                else:
                    # We didn't find the path, remove the path
                    if node.false_child.condition is not None:
                        paths.pop()

        # We failed to find the path in this node :(
        return False

    def get_path(self) -> List[z3.BoolRef]:
        paths:List[z3.BoolRef]=[]
        res=False
        if self.true_entry is not None and self.true_entry.reachable:
            # Try True branch first
            if self.true_entry.condition is not None:
                paths.append(self.true_entry.condition)
            if self.__visit_path_dfs(self.true_entry,paths):
                return paths
        if self.true_entry is not None and self.false_entry is None:
            # Only True branch exist, but unreachable
            if self.true_entry.condition is not None:
                return [z3.Not(self.true_entry.condition)]
            else:
                return []

        if self.false_entry is not None and self.false_entry.reachable:
            # Try False branch if True branch is none or failed to find path
            if self.false_entry.condition is not None:
                paths.append(self.false_entry.condition)
            if self.__visit_path_dfs(self.false_entry,paths):
                return paths
        else:
            # Only False branch exist, but unreachable
            if self.false_entry.condition is not None:
                return [self.false_entry.condition.arg(0)]
            else:
                return []
                    
        # True is none and failed to find path in false
        assert self.true_entry is None,f'Both branches are None'
        if self.false_entry.condition is not None:
            return [self.false_entry.condition.arg(0)]
        else:
            return []
    
    def __visit_path_random(self,node:ConditionNode,paths:List[z3.BoolRef]):
        # TODO: Prevent duplicate path
        if (node.true_child is None and node.false_child is None) or \
            (node.true_child is not None and node.false_child is not None and not node.true_child.reachable and not node.false_child.reachable):
            # We already tried this path, select another path
            return False
        
        if node.true_child is not None and node.true_child.reachable:
            if node.false_child is not None and node.false_child.reachable:
                # Both are exist and reachable
                if random.randint(0,1)==0:
                    # Try to visit true branch
                    if node.true_child.condition is not None:
                        paths.append(node.true_child.condition)
                    is_return=self.__visit_path_random(node.true_child,paths)
                    if is_return:
                        # We found the path, stop searching
                        return True
                    else:
                        # We didn't find the path, remove the path
                        if node.true_child.condition is not None:
                            paths.pop()
                else:
                    # Try to visit false branch
                    if node.false_child.condition is not None:
                        paths.append(node.false_child.condition)
                    is_return=self.__visit_path_random(node.false_child,paths)
                    if is_return:
                        # We found the path, stop searching
                        return True
                    else:
                        # We didn't find the path, remove the path
                        if node.false_child.condition is not None:
                            paths.pop()
            else:
                # Only true branch exist, select true branch
                if node.true_child.condition is not None:
                    paths.append(node.true_child.condition)
                is_return=self.__visit_path_random(node.true_child,paths)
                if is_return:
                    return True
                else:
                    if node.true_child.condition is not None:
                        paths.pop()
        else:
            # Only false branch exist, select false branch
            if node.false_child is not None and node.false_child.reachable:
                if node.false_child.condition is not None:
                    paths.append(node.false_child.condition)
                is_return=self.__visit_path_random(node.false_child,paths)
                if is_return:
                    return True
                else:
                    if node.false_child.condition is not None:
                        paths.pop()
            else:
                # Both are not exist or not reachable
                return False
    
    def __visit_to_check_reachable(self,node:Block,target_line:int,tried_nodes:Set[Block]=set()):
        tried_nodes.add(node)
        if node is None:
            return False
        
        if node.at()<=target_line<=node.end():
            # Reached
            return True
        elif len(node.exits)==0:
            # Not reachable until function exit
            return False
        else:
            for child in node.exits:
                if child.target not in tried_nodes:
                    res=self.__visit_to_check_reachable(child.target,target_line,tried_nodes)
                    if res:
                        return True
                    
    def __visit_check_reachable(self,node:ConditionNode,target_line:int):
        res=self.__visit_to_check_reachable(node.child_node,target_line)
        if res:
            # This node is reachable
            if node.true_child is not None and node.true_child.reachable:
                res=self.__visit_check_reachable(node.true_child,target_line)
                if not res:
                    # True branch is not reachable
                    node.true_child.reachable=False
            if node.false_child is not None and node.false_child.reachable:
                res=self.__visit_check_reachable(node.false_child,target_line)
                if not res:
                    # False branch is not reachable
                    node.false_child.reachable=False
        else:
            # This node is not reachable
            node.reachable=False

    def update_unreachable_conds(self,target_line:int) -> List[z3.BoolRef]:
        if self.true_entry is not None:
            self.__visit_check_reachable(self.true_entry,target_line)
        if self.false_entry is not None:
            self.__visit_check_reachable(self.false_entry,target_line)
    
    def __str__(self) -> str:
        s=''
        if self.true_entry is not None:
            s+=f'True: {self.true_entry.__str__()}\n'
        else:
            s+='True: None\n'
        if self.false_entry is not None:
            s+=f'False: {self.false_entry.__str__()}'
        else:
            s+='False: None'
        return s