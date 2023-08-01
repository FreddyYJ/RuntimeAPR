from types import CodeType
from bytecode import Instr,Bytecode,Label,dump_bytecode

class Instrumenter:
    def __init__(self):
        self.delta=0
        self.skip_next_insert=False

    def __generate_try_except(self,orig_bc:Bytecode,index:int,instr:Instr,no_orig_label:bool=False):
        try_block=[]
        except_block=[]
        cur_lineno=instr.lineno

        dummy_label=Label()  # Unmatch exceptions (Maybe dummy?)
        except_exception_label=Label()  # Exception in except block
        except_label=Label()

        # Find POP_TOPs after function call and remaining instructions
        pop_tops=[]
        remain_instrs=[]
        is_finished=False
        for instr2 in orig_bc[index+1:]:
            if isinstance(instr2,Instr) and instr2.name=='POP_TOP' and not is_finished:
                pop_tops.append(instr2)
            elif isinstance(instr2,Label):
                break
            else:
                is_finished=True
                remain_instrs.append(instr2)
        # Create try
        orig_label=Label()
        try_block.append(Instr('SETUP_FINALLY',except_label, lineno=cur_lineno+1))
        try_block.append(instr)  # CALL_FUNCTION
        try_block+=pop_tops    # POP_TOPs
        try_block.append(Instr('POP_BLOCK', lineno=cur_lineno+1))  # Pop try block
        if len(remain_instrs)==0:
            pass
        elif len(remain_instrs)==1:
            if isinstance(remain_instrs[0],Instr) and (remain_instrs[0].name=='CALL_FUNCTION' or \
                                                        remain_instrs[0].name=='CALL_FUNCTION_KW' or \
                                                        remain_instrs[0].name=='CALL_FUNCTION_EX' or \
                                                        remain_instrs[0].name=='CALL_METHOD'):
                _try_block,_except_block=self.__generate_try_except(orig_bc,index+1,remain_instrs[0],no_orig_label=True)
                try_block+=_try_block
                except_block+=_except_block
                self.skip_next_insert=True
            else:
                # Add Jump directly if next instr is Jump
                try_block.append(remain_instrs[0])
                self.skip_next_insert=True
        else:
            if len(pop_tops)>0:
                self.delta=len(pop_tops)
            try_block.append(Instr('JUMP_ABSOLUTE', orig_label, lineno=cur_lineno+1))

        # Except block
        except_block.append(except_label)
        except_block.append(Instr('DUP_TOP',lineno=cur_lineno+1))
        except_block.append(Instr('LOAD_GLOBAL', 'Exception', lineno=cur_lineno+1))
        except_block.append(Instr('JUMP_IF_NOT_EXC_MATCH',dummy_label, lineno=cur_lineno+1)) # Jump if current Exception is not Exception
        except_block.append(Instr('POP_TOP', lineno=cur_lineno+1))
        except_block.append(Instr('STORE_FAST', 'e', lineno=cur_lineno+1))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno+1))
        except_block+=pop_tops    # Pop return values

        except_block.append(Instr('SETUP_FINALLY',except_exception_label, lineno=cur_lineno+1)) # Exception in except block
        except_block.append(Instr('LOAD_FAST','e', lineno=cur_lineno+1))
        except_block.append(Instr('RAISE_VARARGS',1,lineno=instr.lineno+1))
        # except_block.append(Instr('LOAD_CONST',0,lineno=instr.lineno))
        # except_block.append(Instr('LOAD_CONST',('RepairloopRunner',),lineno=instr.lineno))
        # except_block.append(Instr('IMPORT_NAME','slipcover.jurigged.loop',lineno=instr.lineno))
        # except_block.append(Instr('IMPORT_FROM','RepairloopRunner',lineno=instr.lineno))
        # except_block.append(Instr('STORE_NAME','RepairloopRunner',lineno=instr.lineno))
        # except_block.append(Instr('POP_TOP',lineno=instr.lineno))

        # except_block.append(Instr('LOAD_NAME', 'print', lineno=cur_lineno+2))
        # except_block.append(Instr('LOAD_NAME', 'RepairloopRunner', lineno=cur_lineno+2))
        # except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno+2))
        # except_block.append(Instr('POP_TOP', lineno=cur_lineno+2))

        # except_block.append(Instr('LOAD_NAME','RepairloopRunner', lineno=cur_lineno+1))
        # except_block.append(Instr('CALL_FUNCTION',0, lineno=cur_lineno+1))
        # except_block.append(Instr('LOAD_METHOD','loop', lineno=cur_lineno+1))
        # except_block.append(Instr('LOAD_NAME','e', lineno=cur_lineno+1))
        # except_block.append(Instr('CALL_METHOD',1, lineno=cur_lineno+1))
        # except_block.append(Instr('LOAD_NAME', 'print', lineno=cur_lineno+2)) # TODO: Call Develoop(fn, on_error=only_on_error, runner_class=interface)
        # except_block.append(Instr('LOAD_NAME', 'e', lineno=cur_lineno+2))
        # except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno+2))
        # except_block.append(Instr('POP_TOP', lineno=cur_lineno+2))
        # except_block.append(Instr('POP_BLOCK', lineno=cur_lineno+2)) # Pop except block
        # except_block.append(Instr('POP_EXCEPT', lineno=cur_lineno+2)) # Pop current Exception

        # except_block.append(Instr('LOAD_CONST', None, lineno=cur_lineno+2))
        # except_block.append(Instr('STORE_NAME', 'e', lineno=cur_lineno+2))
        # except_block.append(Instr('DELETE_NAME', 'e', lineno=cur_lineno+2))

        # if len(remain_instrs)==1:
        #     except_block.append(remain_instrs[0])
        # else:
        #     except_block.append(Instr('JUMP_ABSOLUTE', orig_label, lineno=cur_lineno+1))

        # Create dummy and except_exception block
        except_block.append(dummy_label)  # Not handled exceptions
        except_block.append(Instr('RERAISE',1, lineno=cur_lineno+1))
        except_block.append(except_exception_label)  # Exception in except block
        except_block.append(Instr('LOAD_CONST',None, lineno=cur_lineno+1))
        except_block.append(Instr('STORE_FAST','e', lineno=cur_lineno+1))
        except_block.append(Instr('DELETE_FAST','e', lineno=cur_lineno+1))
        except_block.append(Instr('RERAISE',0, lineno=cur_lineno+1))

        # Create remaining instructions
        if len(remain_instrs)>1 and not no_orig_label:
            try_block.append(orig_label)
        
        return try_block,except_block

    def insert_try_except(self,code:CodeType):
        bc=Bytecode.from_code(code)
        # print(code.co_firstlineno)
        # dump_bytecode(bc,lineno=True)
        new_bc=[Instr('LOAD_CONST','__runtime_apr__',lineno=1)]
        except_bc=[]
        self.skip_next_insert=False
        self.delta=0
        for i,instr in enumerate(bc):
            if self.skip_next_insert:
                self.skip_next_insert=False
            elif isinstance(instr,Instr) and (instr.name=='CALL_FUNCTION' or instr.name=='CALL_FUNCTION_KW' or \
                                            instr.name=='CALL_FUNCTION_EX' or instr.name=='CALL_METHOD'):
                try_block,except_block=self.__generate_try_except(bc,i,instr)
                new_bc+=try_block
                except_bc+=except_block
            elif self.delta>0:
                self.delta-=1
            elif isinstance(instr,Instr) and instr.name=='LOAD_CONST' and isinstance(instr.arg,CodeType) and \
                        instr.arg.co_filename==code.co_filename and '__runtime_apr__' not in instr.arg.co_consts:
                new_bc.append(Instr('LOAD_CONST',self.insert_try_except(instr.arg),lineno=instr.lineno))
            else:
                new_bc.append(instr)
                    
        new_bytecode=Bytecode(new_bc+except_bc)
        new_bytecode._copy_attr_from(bc)
        # print('--------------')
        # dump_bytecode(new_bytecode,lineno=True)
        try:
            new_code=new_bytecode.to_code()
            new_code.replace(co_varnames=tuple(list(new_code.co_varnames)+['e','Exception']))
        except:
            print(code.co_filename)
            dump_bytecode(bc,lineno=True)
            print('------------------')
            dump_bytecode(new_bytecode,lineno=True)
            raise
        return new_code