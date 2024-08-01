from _ast import AsyncFunctionDef, FunctionDef
from types import FunctionType
from typing import Any, List, Set, Union
import gast as ast
import beniget

from ..configure import Configure


class FunctionDefFinder(ast.NodeVisitor):
    def __init__(self, funcname: str, start_line: int) -> None:
        self.funcname = funcname
        self.start_line = start_line
        self.max_start_line = 0
        self.definition: FunctionDef = None

    def visit_FunctionDef(self, node: FunctionDef) -> Any:
        if node.name == self.funcname and node.lineno >= self.start_line and self.max_start_line < node.lineno:
            self.definition = node
            self.max_start_line = node.lineno

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef) -> Any:
        if node.name == self.funcname and node.lineno >= self.start_line and self.max_start_line < node.lineno:
            self.definition = node
            self.max_start_line = node.lineno


class DependencyGraph:
    def __init__(self, fn: FunctionType) -> None:
        filename = fn.__code__.co_filename
        with open(filename, 'r') as f:
            tree = ast.parse(f.read())
        func_finder = FunctionDefFinder(fn.__name__, fn.__code__.co_firstlineno)
        func_finder.visit(tree)
        self.func_def = func_finder.definition

    def _get_full_attribute_name(self, node: Union[ast.Attribute, ast.Subscript, ast.Name]):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node.value, ast.Attribute):
            if isinstance(node, ast.Attribute):
                return self._get_full_attribute_name(node.value) + '.' + node.attr
            elif isinstance(node, ast.Subscript):
                return self._get_full_attribute_name(node.value) + '[' + self._get_full_attribute_name(node.slice) + ']'
        elif isinstance(node.value, ast.Name):
            if isinstance(node, ast.Attribute):
                return node.value.id + '.' + node.attr
            elif isinstance(node, ast.Subscript):
                return node.value.id + '[' + self._get_full_attribute_name(node.slice) + ']'
        elif isinstance(node.value, ast.Constant):
            if isinstance(node, ast.Attribute):
                return str(node.value.value) + '.' + node.attr
            elif isinstance(node, ast.Subscript):
                return str(node.value.value) + '[' + self._get_full_attribute_name(node.slice) + ']'
        else:
            raise ValueError(f'Unknown attribute parent value type: {type(node.value)}')

    def get_deps(self):
        """
        Original code by https://stackoverflow.com/questions/55712076/compute-the-data-dependency-graph-of-a-python-program
        """
        full_graph = dict()
        for assign in ast.walk(self.func_def):
            if isinstance(assign, ast.Assign):
                if isinstance(assign.targets[0], ast.Name):
                    defs = []

                    for d in ast.walk(assign):
                        if isinstance(d, ast.Name):
                            defs.append(d.id)
                        elif isinstance(d, ast.Attribute):
                            defs.append(self._get_full_attribute_name(d))

                    full_graph[assign.targets[0].id] = defs[1:]

                elif isinstance(assign.targets[0], ast.Subscript):
                    defs = []

                    for d in ast.walk(assign.targets[0]):
                        if isinstance(d, ast.Name):
                            defs.append(d.id)
                        elif isinstance(d, ast.Attribute):
                            defs.append(self._get_full_attribute_name(d))

                    full_graph[self._get_full_attribute_name(assign.targets[0])] = defs

                elif isinstance(assign.targets[0], ast.Tuple):
                    for elts in assign.targets[0].elts:
                        if isinstance(elts, ast.Name):
                            defs = []

                            for d in ast.walk(elts):
                                if isinstance(d, ast.Name):
                                    defs.append(d.id)
                                elif isinstance(d, ast.Attribute):
                                    defs.append(self._get_full_attribute_name(d))

                            full_graph[elts.id] = defs[1:]

                elif isinstance(assign.targets[0], ast.Attribute):
                    defs = []

                    for d in ast.walk(assign.targets[0]):
                        if isinstance(d, ast.Name):
                            defs.append(d.id)
                        elif isinstance(d, ast.Attribute):
                            defs.append(self._get_full_attribute_name(d))

                    full_graph[self._get_full_attribute_name(assign.targets[0])] = defs[1:]

                else:
                    raise ValueError(f'Unknown assign target type: {type(assign.targets[0])}')

        # Remove duplicate dependencies
        for var in full_graph:
            for dep in full_graph[var].copy():
                for dep2 in full_graph[var].copy():
                    if dep != dep2 and dep.startswith(dep2):
                        if dep2 in full_graph[var]:
                            full_graph[var].remove(dep2)

        return full_graph


class DefUseGraph:
    class Node:
        def __init__(self, node: ast.AST):
            self.node = node
            self.children: Set[DefUseGraph.Node] = set()
            self.parents: Set[DefUseGraph.Node] = set()

        def __eq__(self, o: object) -> bool:
            if not isinstance(o, DefUseGraph.Node):
                return False
            return self.node == o.node

        def __hash__(self) -> int:
            return hash(self.node)

        def __str__(self, space: int = 0) -> str:
            string = f'{" "*(space*4)}{self.node}\n'
            for child in self.children:
                string += child.__str__(space + 1)
            return string

    def __init__(self, fn: FunctionType) -> None:
        filename = fn.__code__.co_filename
        with open(filename, 'r') as f:
            tree = ast.parse(f.read())
        func_finder = FunctionDefFinder(fn.__name__, fn.__code__.co_firstlineno)
        func_finder.visit(tree)
        self.func_def = func_finder.definition

        duc = beniget.DefUseChains(filename)
        duc.visit(tree)
        self.chains: dict = duc.chains

        self.bodies: List[DefUseGraph.Node] = []
        for define in self.chains:
            use = self.chains[define]
            if not isinstance(use.node, ast.AST) or not hasattr(use.node, 'lineno') or use.node.lineno is None:
                # AST node has None lineno, just skip it
                continue
            if use.node.lineno < self.func_def.lineno or use.node.end_lineno > self.func_def.end_lineno:
                continue
            self._gen_graph(use)

        self.entries: Set[DefUseGraph.Node] = set()
        self.leaves: Set[DefUseGraph.Node] = set()
        for node in self.bodies:
            if len(node.parents) == 0:
                self.entries.add(node)
            if len(node.children) == 0:
                self.leaves.add(node)

        # print('entries:')
        # for entry in self.entries:
        #     print(str(entry))
        # print('leaves:')
        # for leaf in self.leaves:
        #     print(str(leaf))

    def _gen_graph(self, use, recursive=1) -> "DefUseGraph.Node":
        cur_node = DefUseGraph.Node(use.node)
        if cur_node not in self.bodies:
            # Update children
            for child in use.users():
                if (
                    not isinstance(child.node, ast.AST)
                    or not hasattr(child.node, 'lineno')
                    or child.node.lineno is None
                ):
                    # AST node has None lineno, just skip it
                    continue
                if child.node.lineno < self.func_def.lineno or child.node.end_lineno > self.func_def.end_lineno:
                    continue

                if recursive <= Configure.max_recursive:
                    child_node = self._gen_graph(child, recursive=recursive + 1)
                    cur_node.children.add(child_node)
                    child_node.parents.add(cur_node)

            self.bodies.append(cur_node)

            return cur_node
        else:
            return self.bodies[self.bodies.index(cur_node)]
