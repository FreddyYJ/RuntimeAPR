from types import CodeType
from bytecode import Instr,Bytecode,Label,dump_bytecode,Compare
import sys

PYTHON_VERSION=sys.version_info[:2]

class Instrumenter:
    def __init__(self,is_script_mode:bool=False,throw_exception_when_error:bool=False):
        self.delta=0
        self.skip_next_insert=False
        self.next_label=None
        self.is_script_mode=is_script_mode
        self.throw_exception_when_error=throw_exception_when_error

    def __generate_try_except__debug(self,orig_bc:Bytecode,index:int,instr:Instr,no_orig_label:bool=False):
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
        next_label=None
        for instr2 in orig_bc[index+1:]:
            if isinstance(instr2,Instr) and instr2.name=='POP_TOP' and not is_finished:
                pop_tops.append(instr2)
            elif isinstance(instr2,Label):
                next_label=instr2
                break
            else:
                is_finished=True
                remain_instrs.append(instr2)
        # Create try
        orig_label=Label()
        try_block.append(Instr('SETUP_FINALLY',except_label, lineno=cur_lineno+10000))
        instr.lineno=cur_lineno+20000
        try_block.append(instr)  # CALL_FUNCTION
        for i,pop_top in enumerate(pop_tops):
            pop_top.lineno=cur_lineno+(30000+i*1000)
            try_block.append(pop_top)
        # try_block+=pop_tops    # POP_TOPs
        try_block.append(Instr('POP_BLOCK', lineno=cur_lineno+110000))  # Pop try block
        if len(remain_instrs)==0:
            self.next_label=next_label
            try_block.append(Instr('JUMP_ABSOLUTE', self.next_label, lineno=cur_lineno+120000))
        elif len(remain_instrs)==1 and isinstance(remain_instrs[0],Instr) and (remain_instrs[0].name=='CALL_FUNCTION' or \
                                                        remain_instrs[0].name=='CALL_FUNCTION_KW' or \
                                                        remain_instrs[0].name=='CALL_FUNCTION_EX' or \
                                                        remain_instrs[0].name=='CALL_METHOD'):
            _try_block,_except_block=self.__generate_try_except__debug(orig_bc,index+1,remain_instrs[0],no_orig_label=True)
            try_block+=_try_block
            except_block+=_except_block
            self.skip_next_insert=True
        elif len(remain_instrs)==1 and isinstance(remain_instrs[0],Instr) and remain_instrs[0].name!='JUMP_ABSOLUTE':
            try_block.append(remain_instrs[0])
            self.next_label=next_label
            self.skip_next_insert=True
        elif len(remain_instrs)==1:
            # Add Jump directly if next instr is Jump
            try_block.append(remain_instrs[0])
            self.next_label=None
            self.skip_next_insert=True
        else:
            if len(pop_tops)>0:
                self.delta=len(pop_tops)
            try_block.append(Instr('JUMP_ABSOLUTE', orig_label, lineno=cur_lineno+120000))

        # Create remaining instructions
        if len(remain_instrs)>1 and not no_orig_label:
            try_block.append(orig_label)

        # Except block
        except_block.append(except_label)
        except_block.append(Instr('DUP_TOP',lineno=cur_lineno+130000))
        except_block.append(Instr('LOAD_GLOBAL', 'Exception', lineno=cur_lineno+140000))
        except_block.append(Instr('JUMP_IF_NOT_EXC_MATCH',dummy_label, lineno=cur_lineno+150000)) # Jump if current Exception is not Exception
        except_block.append(Instr('POP_TOP', lineno=cur_lineno+160000))
        if self.is_script_mode:
            except_block.append(Instr('STORE_NAME', '_sc_e', lineno=cur_lineno+170000))
        else:
            except_block.append(Instr('STORE_FAST', '_sc_e', lineno=cur_lineno+170000))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno+180000))

        except_block.append(Instr('SETUP_FINALLY',except_exception_label, lineno=cur_lineno+190000)) # Exception in except block
        if self.throw_exception_when_error:
            except_block.append(Instr('RAISE_VARARGS',0, lineno=cur_lineno+200000))
        except_block.append(Instr('LOAD_CONST',0,lineno=instr.lineno+112000))
        except_block.append(Instr('LOAD_CONST',('RepairloopRunner',),lineno=instr.lineno+113000))
        except_block.append(Instr('IMPORT_NAME','slipcover.loop',lineno=instr.lineno+114000))
        except_block.append(Instr('IMPORT_FROM','RepairloopRunner',lineno=instr.lineno+115000))
        if self.is_script_mode:
            except_block.append(Instr('STORE_NAME','RepairloopRunner',lineno=instr.lineno+116000))
        else:
            except_block.append(Instr('STORE_FAST','RepairloopRunner',lineno=instr.lineno+116000))
        except_block.append(Instr('POP_TOP',lineno=instr.lineno+117000))

        if self.is_script_mode:
            except_block.append(Instr('LOAD_NAME', 'print', lineno=cur_lineno+118000))
        else:
            except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno+118000))
        if self.is_script_mode:
            except_block.append(Instr('LOAD_NAME', 'RepairloopRunner', lineno=cur_lineno+119000))
        else:
            except_block.append(Instr('LOAD_FAST', 'RepairloopRunner', lineno=cur_lineno+119000))
        except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno+120000))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno+121000))

        if self.is_script_mode:
            except_block.append(Instr('LOAD_NAME', 'print', lineno=cur_lineno+121000))
        else:
            except_block.append(Instr('LOAD_GLOBAL', 'print', lineno=cur_lineno+122000)) # TODO: Call Develoop(fn, on_error=only_on_error, runner_class=interface)
        if self.is_script_mode:
            except_block.append(Instr('LOAD_NAME', '_sc_e', lineno=cur_lineno+123000))
        else:
            except_block.append(Instr('LOAD_FAST', '_sc_e', lineno=cur_lineno+123000))
        except_block.append(Instr('CALL_FUNCTION', 1, lineno=cur_lineno+124000))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno+127000)) # Pop except block
        except_block.append(Instr('RAISE_VARARGS', 0, lineno=cur_lineno+131000))
        except_block.append(Instr('POP_BLOCK', lineno=cur_lineno+127000)) # Pop except block
        except_block.append(Instr('POP_EXCEPT', lineno=cur_lineno+128000)) # Pop current Exception

        except_block.append(Instr('LOAD_CONST', None, lineno=cur_lineno+129000))
        if self.is_script_mode:
            except_block.append(Instr('STORE_NAME', '_sc_e', lineno=cur_lineno+130000))
            except_block.append(Instr('DELETE_NAME', '_sc_e', lineno=cur_lineno+131000))
        else:
            except_block.append(Instr('STORE_FAST', '_sc_e', lineno=cur_lineno+130000))
            except_block.append(Instr('DELETE_FAST', '_sc_e', lineno=cur_lineno+131000))

        if len(remain_instrs)==0 and self.next_label is not None:
            except_block.append(Instr('JUMP_ABSOLUTE', self.next_label, lineno=cur_lineno+132000))
            self.next_label=None
        elif len(remain_instrs)==1:
            if remain_instrs[0].name!='JUMP_ABSOLUTE' and self.next_label is not None:
                except_block.append(Instr('JUMP_ABSOLUTE', self.next_label, lineno=cur_lineno+133000))
                self.next_label=None
            else:
                except_block.append(remain_instrs[0])
        else:
            except_block.append(Instr('JUMP_ABSOLUTE', orig_label, lineno=cur_lineno+134000))

        # Create dummy and except_exception block
        except_block.append(dummy_label)  # Not handled exceptions
        except_block.append(Instr('RERAISE',1, lineno=cur_lineno+135000))
        except_block.append(except_exception_label)  # Exception in except block
        except_block.append(Instr('LOAD_CONST',None, lineno=cur_lineno+136000))
        if self.is_script_mode:
            except_block.append(Instr('STORE_NAME','_sc_e', lineno=cur_lineno+137000))
            except_block.append(Instr('DELETE_NAME','_sc_e', lineno=cur_lineno+138000))
        else:
            except_block.append(Instr('STORE_FAST','_sc_e', lineno=cur_lineno+137000))
            except_block.append(Instr('DELETE_FAST','_sc_e', lineno=cur_lineno+138000))
        except_block.append(Instr('RERAISE',0, lineno=cur_lineno+139000))
        
        return try_block,except_block


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
        next_label=None
        for instr2 in orig_bc[index+1:]:
            if isinstance(instr2,Instr) and instr2.name=='POP_TOP' and not is_finished:
                pop_tops.append(instr2)
            elif isinstance(instr2,Label):
                next_label=instr2
                break
            else:
                is_finished=True
                remain_instrs.append(instr2)

        # Create try
        orig_label=Label()
        try_block.append(Instr('SETUP_FINALLY',except_label, lineno=cur_lineno))  # Declare try block
        try_block.append(instr)  # CALL_FUNCTION
        try_block+=pop_tops    # POP_TOPs: When ignore return value (length is 0 or 1)
        try_block.append(Instr('POP_BLOCK', lineno=cur_lineno))  # Pop try block
        if len(remain_instrs)==0:
            # If no remaining instructions, jump to next label
            self.next_label=next_label
            try_block.append(Instr('JUMP_ABSOLUTE', self.next_label, lineno=cur_lineno))
        elif len(remain_instrs)==1 and isinstance(remain_instrs[0],Instr) and (remain_instrs[0].name=='CALL_FUNCTION' or \
                                                        remain_instrs[0].name=='CALL_FUNCTION_KW' or \
                                                        remain_instrs[0].name=='CALL_FUNCTION_EX' or \
                                                        remain_instrs[0].name=='CALL_METHOD'):
            # If next instruction is function call, generate nested try-except
            _try_block,_except_block=self.__generate_try_except(orig_bc,index+1,remain_instrs[0],no_orig_label=True)
            try_block+=_try_block
            except_block+=_except_block
            self.skip_next_insert=True
        elif len(remain_instrs)==1 and isinstance(remain_instrs[0],Instr) and remain_instrs[0].name!='JUMP_ABSOLUTE':
            # Add remaining instrs directly if next instr is not Jump
            try_block.append(remain_instrs[0])
            self.next_label=next_label
            self.skip_next_insert=True
        elif len(remain_instrs)==1:
            # Add Jump directly if next instr is Jump
            try_block.append(remain_instrs[0])
            self.next_label=None
            self.skip_next_insert=True
        else:
            # Add POP_TOPs and proceed to next instructions
            if len(pop_tops)>0:
                self.delta=len(pop_tops)
            try_block.append(Instr('JUMP_ABSOLUTE', orig_label, lineno=cur_lineno))

        # Create remaining instructions
        if len(remain_instrs)>1 and not no_orig_label:
            try_block.append(orig_label)

        # Except block
        except_block.append(except_label)
        except_block.append(Instr('DUP_TOP',lineno=cur_lineno))
        except_block.append(Instr('LOAD_GLOBAL', 'Exception', lineno=cur_lineno))
        if PYTHON_VERSION[1]<=8:
            except_block.append(Instr('COMPARE_OP', Compare.EXC_MATCH, lineno=cur_lineno))
            except_block.append(Instr('POP_JUMP_IF_FALSE', dummy_label, lineno=cur_lineno))
        else:
            except_block.append(Instr('JUMP_IF_NOT_EXC_MATCH',dummy_label, lineno=cur_lineno)) # Jump if current Exception is not Exception
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))
        if self.is_script_mode:
            except_block.append(Instr('STORE_NAME', '_sc_e', lineno=cur_lineno))
        else:
            except_block.append(Instr('STORE_FAST', '_sc_e', lineno=cur_lineno))
        except_block.append(Instr('POP_TOP', lineno=cur_lineno))  # Until now: except Exception as _sc_e:

        except_block.append(Instr('SETUP_FINALLY',except_exception_label, lineno=cur_lineno)) # Exception in except block
        if self.throw_exception_when_error:  # Raise original exception if option specified
            except_block.append(Instr('RAISE_VARARGS',0, lineno=cur_lineno))
        except_block.append(Instr('LOAD_CONST',0,lineno=instr.lineno))
        except_block.append(Instr('LOAD_CONST',('except_handler',),lineno=instr.lineno))
        except_block.append(Instr('IMPORT_NAME','slipcover.loop',lineno=instr.lineno))
        except_block.append(Instr('IMPORT_FROM','except_handler',lineno=instr.lineno))
        if self.is_script_mode:
            except_block.append(Instr('STORE_NAME', 'except_handler', lineno=cur_lineno))
        else:
            except_block.append(Instr('STORE_FAST', 'except_handler', lineno=cur_lineno))
        except_block.append(Instr('POP_TOP',lineno=instr.lineno))  # Until now: from slipcover.loop import except_handler

        if self.is_script_mode:
            except_block.append(Instr('LOAD_NAME','except_handler', lineno=cur_lineno))
        else:
            except_block.append(Instr('LOAD_FAST','except_handler', lineno=cur_lineno))
        if self.is_script_mode:
            except_block.append(Instr('LOAD_NAME', '_sc_e', lineno=cur_lineno))
        else:
            except_block.append(Instr('LOAD_FAST', '_sc_e', lineno=cur_lineno))    
        except_block.append(Instr('CALL_FUNCTION',1, lineno=cur_lineno))
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
        except_block.append(Instr('POP_BLOCK', lineno=cur_lineno)) # Pop except block
        except_block.append(Instr('POP_EXCEPT', lineno=cur_lineno)) # Pop current Exception

        # Delete _sc_e
        except_block.append(Instr('LOAD_CONST', None, lineno=cur_lineno))
        if self.is_script_mode:
            except_block.append(Instr('STORE_NAME', '_sc_e', lineno=cur_lineno))
            except_block.append(Instr('DELETE_NAME', '_sc_e', lineno=cur_lineno))
        else:
            except_block.append(Instr('STORE_FAST', '_sc_e', lineno=cur_lineno))
            except_block.append(Instr('DELETE_FAST', '_sc_e', lineno=cur_lineno))

        # Jump to next instruction
        if len(remain_instrs)==0 and self.next_label is not None:
            except_block.append(Instr('JUMP_ABSOLUTE', self.next_label, lineno=cur_lineno))
            self.next_label=None
        elif len(remain_instrs)==1:
            if remain_instrs[0].name!='JUMP_ABSOLUTE' and self.next_label is not None:
                except_block.append(Instr('JUMP_ABSOLUTE', self.next_label, lineno=cur_lineno))
                self.next_label=None
            else:
                except_block.append(remain_instrs[0])
        else:
            except_block.append(Instr('JUMP_ABSOLUTE', orig_label, lineno=cur_lineno))

        # Create dummy and except_exception block
        except_block.append(dummy_label)  # Not handled exceptions
        if PYTHON_VERSION[1]<=8:
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('RAISE_VARARGS',0, lineno=cur_lineno))
        else:
            except_block.append(Instr('RERAISE',1, lineno=cur_lineno))

        except_block.append(except_exception_label)  # Exception in except block
        if PYTHON_VERSION[1]<=8:
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('POP_TOP', lineno=cur_lineno))
            except_block.append(Instr('RAISE_VARARGS',0, lineno=cur_lineno))
        else:
            except_block.append(Instr('LOAD_CONST',None, lineno=cur_lineno))
            if self.is_script_mode:
                except_block.append(Instr('STORE_NAME','_sc_e', lineno=cur_lineno))
                except_block.append(Instr('DELETE_NAME','_sc_e', lineno=cur_lineno))
            else:
                except_block.append(Instr('STORE_FAST','_sc_e', lineno=cur_lineno))
                except_block.append(Instr('DELETE_FAST','_sc_e', lineno=cur_lineno))
            except_block.append(Instr('RERAISE',0, lineno=cur_lineno))
        
        return try_block,except_block

    def insert_try_except(self,code:CodeType):
        bc=Bytecode.from_code(code)
        # Skip if already instrumented
        if isinstance(bc[0],Instr) and bc[0].name=='LOAD_CONST' and bc[0].arg=='__runtime_apr__':
            return code
        
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
                new_bc+=try_block  # Replace function call with try block
                except_bc+=except_block  # Store except blocks sepeerately to insert at the end of the bytecode
            elif self.delta>0:
                self.delta-=1
            elif isinstance(instr,Instr) and instr.name=='LOAD_CONST' and isinstance(instr.arg,CodeType) and \
                        instr.arg.co_filename==code.co_filename and '__runtime_apr__' not in instr.arg.co_consts:
                # Instrument nested CodeType
                new_bc.append(Instr('LOAD_CONST',self.insert_try_except(instr.arg),lineno=instr.lineno))
            else:
                new_bc.append(instr)
                    
        # We insert except blocks at the end of bytecode
        new_bytecode=Bytecode(new_bc+except_bc)
        new_bytecode._copy_attr_from(bc)
        # print('--------------')
        # dump_bytecode(new_bytecode,lineno=True)
        try:
            new_code=new_bytecode.to_code()
            # Add new variables
            new_code.replace(co_varnames=tuple(list(new_code.co_varnames)+['_sc_e','Exception']))
        except:
            print(code.co_filename)
            dump_bytecode(bc,lineno=True)
            print('------------------')
            dump_bytecode(new_bytecode,lineno=True)
            raise
        return new_code