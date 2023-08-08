import ast
from typing import Any, List

class FunctionFinderVisitor(ast.NodeVisitor):
    def __init__(self,buggy_line) -> None:
        self.buggy_line=buggy_line
        self.functiondefs:List[ast.FunctionDef]=[]
        super().__init__()
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        if node.lineno<=self.buggy_line<=node.end_lineno:
            self.functiondefs.append(node)
    
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        if node.lineno<=self.buggy_line<=node.end_lineno:
            self.functiondefs.append(node)
    
    def get_funcs(self):
        max_start_lineno=self.functiondefs[0].lineno
        min_end_lineno=self.functiondefs[0].end_lineno
        target_func=self.functiondefs[0]
        for func in self.functiondefs:
            if func.lineno>=max_start_lineno and func.end_lineno<=min_end_lineno:
                target_func=func
                max_start_lineno=func.lineno
                min_end_lineno=func.end_lineno

        return target_func