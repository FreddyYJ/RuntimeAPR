from _ast import AsyncFunctionDef, FunctionDef
from types import FunctionType
from typing import Any, List, Set
import gast as ast
import beniget

class FunctionDefFinder(ast.NodeVisitor):
    def __init__(self,funcname:str,start_line:int) -> None:
        self.funcname=funcname
        self.start_line=start_line
        self.max_start_line=0
        self.definition:FunctionDef=None

    def visit_FunctionDef(self, node: FunctionDef) -> Any:
        if node.name==self.funcname and node.lineno>=self.start_line and self.max_start_line<node.lineno:
            self.definition=node
            self.max_start_line=node.lineno
    
    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef) -> Any:
        if node.name==self.funcname and node.lineno>=self.start_line and self.max_start_line<node.lineno:
            self.definition=node
            self.max_start_line=node.lineno
        
class DefUseGraph:
    class Node:
        def __init__(self,node:ast.AST):
            self.node=node
            self.children:Set[DefUseGraph.Node]=set()
            self.parents:Set[DefUseGraph.Node]=set()

        def __eq__(self, o: object) -> bool:
            if not isinstance(o,DefUseGraph.Node):
                return False
            return self.node==o.node
        
        def __hash__(self) -> int:
            return hash(self.node)
        
        def __str__(self,space:int=0) -> str:
            string=f'{" "*(space*4)}{self.node}\n'
            for child in self.children:
                string+=child.__str__(space+1)
            return string

    def __init__(self,fn:FunctionType) -> None:
        filename=fn.__code__.co_filename
        with open(filename,'r') as f:
            tree=ast.parse(f.read())
        func_finder=FunctionDefFinder(fn.__name__,fn.__code__.co_firstlineno)
        func_finder.visit(tree)
        self.func_def=func_finder.definition

        duc=beniget.DefUseChains(filename)
        duc.visit(tree)
        self.chains:dict=duc.chains

        self.bodies:List[DefUseGraph.Node]=[]
        for define in self.chains:
            use=self.chains[define]
            if not isinstance(use.node,ast.AST) or not hasattr(use.node,'lineno') or use.node.lineno is None:
                # AST node has None lineno, just skip it
                continue
            if use.node.lineno<self.func_def.lineno or \
                    use.node.end_lineno>self.func_def.end_lineno:
                continue
            self._gen_graph(use)

        self.entries:Set[DefUseGraph.Node]=set()
        self.leaves:Set[DefUseGraph.Node]=set()
        for node in self.bodies:
            if len(node.parents)==0:
                self.entries.add(node)
            if len(node.children)==0:
                self.leaves.add(node)

        # print('entries:')
        # for entry in self.entries:
        #     print(str(entry))
        # print('leaves:')
        # for leaf in self.leaves:
        #     print(str(leaf))

    def _gen_graph(self,use) -> "DefUseGraph.Node":
        cur_node=DefUseGraph.Node(use.node)
        if cur_node not in self.bodies:
            # Update children
            for child in use.users():
                if not isinstance(child.node,ast.AST) or not hasattr(child.node,'lineno') or child.node.lineno is None:
                    # AST node has None lineno, just skip it
                    continue
                if child.node.lineno<self.func_def.lineno or child.node.end_lineno>self.func_def.end_lineno:
                    continue
                child_node=self._gen_graph(child)
                cur_node.children.add(child_node)
                child_node.parents.add(cur_node)

            self.bodies.append(cur_node)

            return cur_node
        else:
            return self.bodies[self.bodies.index(cur_node)]
