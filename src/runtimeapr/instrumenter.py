from types import CodeType
from bytecode import Instr, Bytecode, Label, dump_bytecode, Compare
import sys
import os

PYTHON_VERSION = sys.version_info[:2]


class Instrumenter:
    def __init__(self, is_script_mode: bool = False, throw_exception_when_error: bool = False):
        self.delta = 0
        self.skip_next_insert = False
        self.next_label = None
        self.is_script_mode = is_script_mode
        self.throw_exception_when_error = throw_exception_when_error

        self.block_stack = []  # This contains Instrs that may need POP_BLOCK to check exception is already handled
        self.handled_exceptions = set()  # This contains exceptions that are already handled
        self.code_stack = []

    def _get_handled_exception(self, setup_finally_instr: Instr):
        except_label: Label = setup_finally_instr.arg
        for code in self.code_stack:
            if setup_finally_instr in code:
                label_index = code.index(except_label)
                specified_exception = set()

                def search_next_exception(next_label: Label):
                    next_index = code.index(next_label)
                    if isinstance(code[next_index + 1], Instr) and code[next_index + 1].name == 'DUP_TOP':
                        specified_exception.add(code[next_index + 2].arg)
                        return code[next_index + 4]
                    else:
                        return None

                if isinstance(code[label_index + 1], Instr) and code[label_index + 1].name == 'DUP_TOP':
                    # Exception specified
                    specified_exception.add(code[label_index + 2].arg)
                    next_label = code[label_index + 4]
                    while next_label is not None:
                        next_label = search_next_exception(next_label)

                return specified_exception

        # assert False, 'Except block not found in code stack'
        return set()

    def insert_try_except(self, code: CodeType):
        bc = Bytecode.from_code(code)
        is_global = bc.name == '<module>'
        # Skip if already instrumented
        if isinstance(bc[0], Instr) and bc[0].name == 'LOAD_CONST' and bc[0].arg == '__runtime_apr__':
            return code

        self.code_stack.append(bc)

        # print(code.co_firstlineno)
        # dump_bytecode(bc,lineno=True)
        cur_lineno = code.co_firstlineno
        new_bc = [Instr('LOAD_CONST', '__runtime_apr__', lineno=1)]
        except_block = []
        except_label = Label()
        dummy_label = Label()
        except_exception_label = Label()

        # # TODO: Store func entry: remove later
        # if 'FUNC_NAME' in os.environ:
        #     if bc.name.endswith(os.environ['FUNC_NAME']):
        #         new_bc.append(Instr('LOAD_CONST',0,lineno=cur_lineno))
        #         new_bc.append(Instr('LOAD_CONST',('func_entry',),lineno=cur_lineno))
        #         new_bc.append(Instr('IMPORT_NAME','runtimeapr.loop.repairloop',lineno=cur_lineno))
        #         new_bc.append(Instr('IMPORT_FROM','func_entry',lineno=cur_lineno))
        #         if is_global:
        #             new_bc.append(Instr('STORE_NAME', 'func_entry', lineno=cur_lineno))
        #         else:
        #             new_bc.append(Instr('STORE_FAST', 'func_entry', lineno=cur_lineno))
        #         new_bc.append(Instr('POP_TOP',lineno=cur_lineno))
        #         if is_global:
        #             new_bc.append(Instr('LOAD_NAME','func_entry', lineno=cur_lineno))
        #         else:
        #             new_bc.append(Instr('LOAD_FAST','func_entry', lineno=cur_lineno))
        #         new_bc.append(Instr('LOAD_GLOBAL','globals', lineno=cur_lineno))
        #         new_bc.append(Instr('CALL_FUNCTION',0, lineno=cur_lineno))
        #         new_bc.append(Instr('CALL_FUNCTION',1, lineno=cur_lineno))
        #         new_bc.append(Instr('POP_TOP', lineno=cur_lineno))  # Until now: func_entry(globals())

        # Entry try block
        new_bc.append(Instr('SETUP_FINALLY', except_label, lineno=cur_lineno))  # Declare try block
        for instr in bc:
            if (
                isinstance(instr, Instr)
                and instr.name == 'LOAD_CONST'
                and isinstance(instr.arg, CodeType)
                and instr.arg.co_filename == code.co_filename
                and '__runtime_apr__' not in instr.arg.co_consts
            ):
                # Instrument nested CodeType
                new_bc.append(Instr('LOAD_CONST', self.insert_try_except(instr.arg), lineno=instr.lineno))
            elif isinstance(instr, Instr) and instr.name == 'RETURN_VALUE':
                new_bc.append(Instr('POP_BLOCK', lineno=cur_lineno))
                new_bc.append(instr)
            else:
                new_bc.append(instr)

        except_block.append(except_label)
        except_block.append(Instr('DUP_TOP', lineno=cur_lineno))
        except_block.append(Instr('LOAD_GLOBAL', 'Exception', lineno=cur_lineno))
        if PYTHON_VERSION[1] <= 8:
            except_block.append(Instr('COMPARE_OP', Compare.EXC_MATCH, lineno=cur_lineno))
            except_block.append(Instr('POP_JUMP_IF_FALSE', dummy_label, lineno=cur_lineno))
        else:
            except_block.append(
                Instr('JUMP_IF_NOT_EXC_MATCH', dummy_label, lineno=cur_lineno)
            )  # Jump if current Exception is not Exception
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))
        if is_global:
            except_block.append(Instr('STORE_NAME', '_sc_e', lineno=cur_lineno))
        else:
            except_block.append(Instr('STORE_FAST', '_sc_e', lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))  # Until now: except Exception as _sc_e:

        except_block.append(
            Instr('SETUP_FINALLY', except_exception_label, lineno=cur_lineno)
        )  # Exception in except block
        if self.throw_exception_when_error:  # Raise original exception if option specified
            except_block.append(Instr('RAISE_VARARGS', 0, lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST', 0, lineno=instr.lineno))
        except_block.append(Instr('LOAD_CONST', ('except_handler',), lineno=instr.lineno))
        except_block.append(Instr('IMPORT_NAME', 'slipcover.loop', lineno=instr.lineno))
        except_block.append(Instr('IMPORT_FROM', 'except_handler', lineno=instr.lineno))

        if is_global:
            except_block.append(Instr('STORE_NAME', 'except_handler', lineno=cur_lineno))
        else:
            except_block.append(Instr('STORE_FAST', 'except_handler', lineno=cur_lineno))
        except_block.append(
            Instr('POP_TOP', lineno=instr.lineno)
        )  # Until now: from slipcover.loop import except_handler

        if is_global:
            except_block.append(Instr('LOAD_NAME', 'except_handler', lineno=cur_lineno))
        else:
            except_block.append(Instr('LOAD_FAST', 'except_handler', lineno=cur_lineno))
        if is_global:
            except_block.append(Instr('LOAD_NAME', '_sc_e', lineno=cur_lineno))
        else:
            except_block.append(Instr('LOAD_FAST', '_sc_e', lineno=cur_lineno))
        except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))  # Until now: except_handler(_sc_e)
        # TODO: Handle return value from repair loop

        # # Print exception
        # if self.is_script_mode:
        #     except_block.append(Instr('LOAD_NAME', 'print', lineno=cur_lineno))
        # else:
        #     except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno))
        # if self.is_script_mode:
        #     except_block.append(Instr('LOAD_NAME', '_sc_e', lineno=cur_lineno))
        # else:
        #     except_block.append(Instr('LOAD_FAST', '_sc_e', lineno=cur_lineno))
        # except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno))
        # except_block.append(Instr('POP_TOP', lineno=cur_lineno)) # Pop return

        except_block.append(Instr('POP_BLOCK', lineno=cur_lineno))  # Pop except block
        # except_block.append(Instr('BEGIN_FINALLY', lineno=cur_lineno))  # Pop current Exception

        # Delete _sc_e
        except_block.append(except_exception_label)  # Exception in except block
        except_block.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        if is_global:
            except_block.append(Instr('STORE_NAME', '_sc_e', lineno=cur_lineno))
            except_block.append(Instr('DELETE_NAME', '_sc_e', lineno=cur_lineno))
        else:
            except_block.append(Instr('STORE_FAST', '_sc_e', lineno=cur_lineno))
            except_block.append(Instr('DELETE_FAST', '_sc_e', lineno=cur_lineno))
        except_block.append(Instr('END_FINALLY', lineno=cur_lineno))
        except_block.append(Instr('POP_EXCEPT', lineno=cur_lineno))
        # TODO: Change to return _except_handler(_sc_e)'s return
        except_block.append(Instr('LOAD_CONST', 'None', lineno=cur_lineno))
        except_block.append(Instr('RETURN_VALUE', lineno=cur_lineno))

        # Create dummy and except_exception block
        except_block.append(dummy_label)  # Not handled exceptions
        if PYTHON_VERSION[1] <= 8:
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('RAISE_VARARGS', 0, lineno=cur_lineno))
        else:
            except_block.append(Instr('RERAISE', 1, lineno=cur_lineno))

        # We insert except blocks at the end of bytecode
        new_bytecode = Bytecode(new_bc + except_block)
        new_bytecode._copy_attr_from(bc)
        # print('--------------')
        # dump_bytecode(new_bytecode,lineno=True)
        try:
            new_code = new_bytecode.to_code()
            # Add new variables
            new_code.replace(co_varnames=tuple(list(new_code.co_varnames) + ['_sc_e', 'Exception']))
        except:
            print(code.co_filename)
            dump_bytecode(bc, lineno=True)
            print('------------------')
            dump_bytecode(new_bytecode, lineno=True)
            raise

        self.code_stack.pop()
        return new_code
