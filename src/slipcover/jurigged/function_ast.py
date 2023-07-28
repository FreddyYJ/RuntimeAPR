import ast
from typing import List

class ParentInsertionVisitor(ast.NodeTransformer):
    def __init__(self):
        self.parent = None

    def visit(self, node):
        node.parent = self.parent

        self.parent = node
        super().visit(node)
        if isinstance(node,ast.AST):
            self.parent = node.parent
        return node

class FunctionVisitor(ast.NodeVisitor):
    def __init__(self,root):
        # Format: [module:][class.]<function>
        self.functions:List[ast.FunctionDef] = []
        self.func_names:List[List[str]] = []

        parent_insert=ParentInsertionVisitor()
        parent_insert.visit(root)

    def visit_FunctionDef(self,node:ast.FunctionDef):
        self.functions.append(node)
        if node.parent is not None:
            if isinstance(node.parent,ast.ClassDef):
                self.func_names.append([node.parent.name,node.name])
            else:
                self.func_names.append([node.name])