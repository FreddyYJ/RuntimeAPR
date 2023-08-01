from types import CodeType
from bytecode import Instr,Bytecode,Label,dump_bytecode

class Instrumenter:
    def insert_try_except(self,code:CodeType):
        bc=Bytecode.from_code(code)
        print(code.co_firstlineno)
        # dump_bytecode(bc,lineno=True)
        new_bc=[Instr('LOAD_CONST','__runtime_apr__',lineno=1)]
        skip_insert=False
        for i,instr in enumerate(bc):
            if isinstance(instr,Instr) and (instr.name=='CALL_FUNCTION' or instr.name=='CALL_FUNCTION_KW' or \
                                            instr.name=='CALL_FUNCTION_EX' or instr.name=='CALL_METHOD'):
                cur_lineno=instr.lineno

                dummy_label=Label()  # Unmatch exceptions (Maybe dummy?)
                except_exception_label=Label()  # Exception in except block
                except_label=Label()

                # Find POP_TOPs after function call and remaining instructions
                pop_tops=[]
                remain_instrs=[]
                is_finished=False
                for instr2 in bc[i+1:]:
                    if isinstance(instr2,Instr) and instr2.name=='POP_TOP' and not is_finished:
                        pop_tops.append(instr2)
                    else:
                        is_finished=True
                        remain_instrs.append(instr2)

                # Create try
                orig_label=Label()
                new_bc.append(Instr('SETUP_FINALLY',except_label, lineno=cur_lineno+1))
                new_bc.append(instr)  # CALL_FUNCTION
                new_bc+=pop_tops    # POP_TOPs
                new_bc.append(Instr('POP_BLOCK', lineno=cur_lineno+1))  # Pop try block
                if isinstance(remain_instrs[0],Instr) and remain_instrs[0].name=='JUMP_ABSOLUTE':
                    # Add Jump directly if next instr is Jump
                    new_bc.append(remain_instrs[0])
                    skip_insert=True
                else:
                    new_bc.append(Instr('JUMP_ABSOLUTE', orig_label, lineno=cur_lineno+1))

                # Except block
                new_bc.append(except_label)
                new_bc.append(Instr('DUP_TOP',lineno=cur_lineno+1))
                new_bc.append(Instr('LOAD_NAME', 'Exception', lineno=cur_lineno+1))
                new_bc.append(Instr('JUMP_IF_NOT_EXC_MATCH',dummy_label, lineno=cur_lineno+1)) # Jump if current Exception is not Exception
                new_bc.append(Instr('POP_TOP', lineno=cur_lineno+1))
                new_bc.append(Instr('STORE_NAME', 'e', lineno=cur_lineno+1))
                new_bc.append(Instr('POP_TOP', lineno=cur_lineno+1))
                new_bc+=pop_tops    # Pop return values

                new_bc.append(Instr('SETUP_FINALLY',except_exception_label, lineno=cur_lineno+1)) # Exception in except block
                # new_bc.append(Instr('LOAD_CONST',0,lineno=instr.lineno))
                # new_bc.append(Instr('LOAD_CONST',('RepairloopRunner',),lineno=instr.lineno))
                # new_bc.append(Instr('IMPORT_NAME','slipcover.jurigged.loop',lineno=instr.lineno))
                # new_bc.append(Instr('IMPORT_FROM','RepairloopRunner',lineno=instr.lineno))
                # new_bc.append(Instr('STORE_NAME','RepairloopRunner',lineno=instr.lineno))
                # new_bc.append(Instr('POP_TOP',lineno=instr.lineno))

                # new_bc.append(Instr('LOAD_NAME', 'print', lineno=cur_lineno+2))
                # new_bc.append(Instr('LOAD_NAME', 'RepairloopRunner', lineno=cur_lineno+2))
                # new_bc.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno+2))
                # new_bc.append(Instr('POP_TOP', lineno=cur_lineno+2))

                # new_bc.append(Instr('LOAD_NAME','RepairloopRunner', lineno=cur_lineno+1))
                # new_bc.append(Instr('CALL_FUNCTION',0, lineno=cur_lineno+1))
                # new_bc.append(Instr('LOAD_METHOD','loop', lineno=cur_lineno+1))
                # new_bc.append(Instr('LOAD_NAME','e', lineno=cur_lineno+1))
                # new_bc.append(Instr('CALL_METHOD',1, lineno=cur_lineno+1))
                new_bc.append(Instr('LOAD_NAME', 'print', lineno=cur_lineno+2)) # TODO: Call Develoop(fn, on_error=only_on_error, runner_class=interface)
                new_bc.append(Instr('LOAD_NAME', 'e', lineno=cur_lineno+2))
                new_bc.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno+2))
                new_bc.append(Instr('POP_TOP', lineno=cur_lineno+2))
                new_bc.append(Instr('POP_BLOCK', lineno=cur_lineno+2)) # Pop except block
                new_bc.append(Instr('POP_EXCEPT', lineno=cur_lineno+2)) # Pop current Exception

                new_bc.append(Instr('LOAD_CONST', None, lineno=cur_lineno+2))
                new_bc.append(Instr('STORE_NAME', 'e', lineno=cur_lineno+2))
                new_bc.append(Instr('DELETE_NAME', 'e', lineno=cur_lineno+2))

                if isinstance(remain_instrs[0],Instr) and remain_instrs[0].name=='JUMP_ABSOLUTE':
                    new_bc.append(remain_instrs[0])
                else:
                    new_bc.append(Instr('JUMP_ABSOLUTE', orig_label, lineno=cur_lineno+1))

                # Create dummy and except_exception block
                new_bc.append(dummy_label)  # Not handled exceptions
                new_bc.append(Instr('RERAISE',1, lineno=cur_lineno+1))
                new_bc.append(except_exception_label)  # Exception in except block
                new_bc.append(Instr('LOAD_CONST',None, lineno=cur_lineno+1))
                new_bc.append(Instr('STORE_NAME','e', lineno=cur_lineno+1))
                new_bc.append(Instr('DELETE_NAME','e', lineno=cur_lineno+1))
                new_bc.append(Instr('RERAISE',0, lineno=cur_lineno+1))

                # Create remaining instructions
                if not isinstance(remain_instrs[0],Instr) or remain_instrs[0].name!='JUMP_ABSOLUTE':
                    new_bc.append(orig_label)

            elif skip_insert:
                skip_insert=False
            elif isinstance(instr,Instr) and instr.name=='LOAD_CONST' and isinstance(instr.arg,CodeType) and \
                        instr.arg.co_filename==code.co_filename and '__runtime_apr__' not in instr.arg.co_consts:
                new_bc.append(Instr('LOAD_CONST',self.insert_try_except(instr.arg),lineno=instr.lineno))
            else:
                new_bc.append(instr)
                    
        new_bytecode=Bytecode(new_bc)
        new_bytecode.freevars=list(code.co_freevars)
        new_bytecode.cellvars=list(code.co_cellvars)
        new_bytecode.name=code.co_name
        new_bytecode.filename=code.co_filename
        new_bytecode.first_lineno=code.co_firstlineno
        new_bytecode._copy_attr_from(bc)
        dump_bytecode(new_bytecode,lineno=True)
        return new_bytecode.to_code()