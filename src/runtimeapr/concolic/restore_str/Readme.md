# String restorer
## Use
Import the right module with 
```python
from runtimeapr.concolic.restore_str.util_ast.runner import FunctionGenerator
```
Then use it by creating an instance of it:
```python
fun_gen = FunctionGenerator(varname, examples, buggy_local_vars, buggy_global_vars, fuzzer)
```
Where `varname` is the name of the variable of type string one wants to restore, `examples` is a list of examples of inputs and outputs of the buggy function, `buggy_local_var` and `buggy_global_vars` are the local and global variables from the first buggy state observed and `fuzzer` is the fuzzer.

To restore the state of the variable, one just have to call the following method:
```python
state: Optional[str] = fun_gen.get_expected_state()
```
The method returns None if the synthesizer was not able to complete its task.

### Restrictions
- No escaped characters
- No quote
- It is expected that you don't use the semicolon `;`. It is utilized in the program and is therefore removed if present in a test. And for my sanity, please no quotes `"` either.
