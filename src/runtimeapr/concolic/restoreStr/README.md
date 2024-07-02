# String restorer
## Use
Import the right submodule with 
```python
from runtimeapr.concolic.restoreStr.util_ast.runner import FunctionGenerator
```
Then use it by creating an instance of it:
```python
fun_gen = FunctionGenerator(varname, examples, buggy_local_vars, buggy_global_vars, fuzzer)
```
Where `varname` is the name of the variable of type string one wants to restore, `examples` is a list of examples of inputs and outputs of the buggy function and `buggy_local_var` and `buggy_global_vars` are the local and global variables from the first buggy state observed.

To restore the state of the variable, one just have to call the following method:
```python
state: Optional[str] = fun_gen.get_expected_state()
```
The method returns None if the synthesizer was not able to complete its task.

### Restrictions
- No escaped characters
- No double quote
