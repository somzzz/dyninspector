"""
Module script for the LLDB wrapper class offering support for dynamic
linking and loading.
"""

import os
import lldb
import logging

class DynLldb(object):
    """
    This is a wrapper class over LLDB. It offers support for dynamic
    and loading analysis.
    """

    MAIN    = "main"
    logger  = logging.getLogger('dynlldb')

    SECTIONS    = [".plt", ".text", ".got", ".got_plt", ".data"]

    class ProcessState(object):
        """
        The states of a process. We do not need RUNNING as the
        state is always checked on program paused / breakpoints.
        """

        STOPPED = 0
        EXITED  = 1

        def __init__(self):
            pass

    class Breakpoint(object):
        """
        A breakpoint in the program.
        """

        PLT_BP              = 0
        RET_FROM_PLT_BP     = 1
        DLOPEN_BP           = 2
        DLSYM_BP            = 3
        DLCLOSE_BP          = 4
        RET_FROM_DLOPEN     = 5
        RET_FROM_DLCLOSE    = 6
        RET_FROM_DLSYM      = 7
        DYN_CALL_FUNC_BP    = 8
        RET_FROM_DYN_CALL   = 9

        def __init__(self):
            self.addr       = None
            self.tag        = None
            self.callback   = None
            self.bp_object  = None
            self.details    = None

    class GotFuncInfo(object):
        """
        An entry in the .got table: (addres, pointer value)
        """

        def __init__(self):

            self.addr   = None
            self.value  = None

    class PltFuncInfo(object):
        """
        A stub in the .got.plt section
        """

        def __init__(self):

            self.name           = None
            self.sym            = None
            self.addr           = None
            self.bp             = None
            self.bp_callback    = None
            self.got_entry      = None

    class DynLibrary(object):
        """
        A Dynamically loaded library
        """

        def __init__(self):
            self.symbols    = []

    class DynSymbol(object):
        """
        A symbol from a dynamically loaded library
        """

        def __init__(self):
            self.name       = None
            self.address    = None

    def __init__(self):

        # Debugger insance
        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(False)

        # Target info
        self.elf            = None
        self.target     = None
        self.process        = None
        self.plt_entries    = []
        self.plt_symbols    = {}
        self.plt            = {}
        self.got            = {}
        self.saved_pc       = None
        self.static_modules = []

        # Breakpoints
        self.bps            = []
        self.bp_func_name   = None
        self.bp_func        = None
        self.bp_main        = None

    def clean(self):
        # Target info
        self.elf            = None
        self.target     = None
        self.process        = None
        self.plt_entries    = []
        self.plt_symbols    = {}
        self.plt            = {}
        self.got            = {}
        self.saved_pc       = None
        self.static_modules = []

        # Breakpoints
        self.bps            = []
        self.bp_func_name   = None
        self.bp_func        = None
        self.bp_main        = None

    def set_elf(self, elf):
        """ Create a target.
            elf : elf executable path
        """

        self.clean()
        self.elf = elf

        if self.target is not None:
            self.target.Clear()

        self.target = self.debugger.CreateTargetWithFileAndArch(
            self.elf.__str__(), lldb.LLDB_ARCH_DEFAULT)

        if self.target:
            return True
        else:
            return False

    def set_breakpoint(self, func, en):
        """
        Set breakpoints for a target. Enable or disable them.
        Breakpoints can only be set for functions in the .plt.
        """

        self.bp_func_name = func

        if self.target:
            entry = self.plt[func]
            if entry is not None:
                entry.bp.SetEnabled(en)

            for breakpoint in self.target.breakpoint_iter():
                self.logger.info(breakpoint.__str__() + " enabled = "
                                 + str(breakpoint.IsEnabled()))

    def run_target(self):
        """
        Run the target. Create a process and read its plt data.
        """

        if self.target is None:
            return

        # Set the main bp before start
        self.bp_main = self.target.BreakpointCreateByName(
            'main',
            self.target.GetExecutable().GetFilename())

        # Run target
        self.process = self.target.LaunchSimple(None, None, os.getcwd())
        if self.process is None:
            return None

        # Read PLT data
        self.read_plt()

        # Get statically loaded modules
        self.static_modules = self.read_modules()

        return self.process

    def stop_target(self):
        """
        Stop the current lldb session. Disable breakpoints.
        Clear all internal data related to the session.
        """

        if self.target is None:
            return

        self.logger.info("stop_target")

        if self.process:
            self.process.Stop()

        self.target.DeleteAllBreakpoints()

        # Reset internal data
        self.process        = None
        self.plt_entries    = []
        self.plt_symbols    = {}
        self.plt            = {}
        self.static_modules = {}

        self.bps            = []
        self.bp_func_name   = None
        self.bp_func        = None
        self.bp_main        = None

        self.set_elf(self.elf)

    def continue_target(self):
        """
        Continue execution of the target if process was paused on a
        breakpoint.
        Return a message with the state of the process after this call.
        """

        if self.process is None:
            return None, None

        state = self.process.GetState()

        if state == lldb.eStateStopped:
            err = self.process.Continue()

            self.saved_pc = self.get_pc_from_frame(1)
            self.logger.info(self.process)

            self.invoke_breakpoint_callback()

            # Update internal data structure for got entries
            self.read_got()

        return self.get_current_breakpoint()

    def step_instruction(self):
        """
        Step to the next instruction.
        Update internal process data.
        """

        if self.process is None:
            return None, None

        state = self.process.GetState()
        if state == lldb.eStateStopped:
            thread = self.process.GetThreadAtIndex(0)
            thread.StepInstruction(False)
            frame0  = thread.GetFrameAtIndex(0)

            # Update internal data structure for got entries
            self.read_got()

        return state, self.process.__str__()

    def get_current_breakpoint(self):
        current_pc = self.get_pc_from_frame(0)
        for bp in self.bps:
            if current_pc == bp.addr:
                return bp 

    def invoke_breakpoint_callback(self):
        self.logger.info("INVOKE BP CALLBACK")

        # Call bp callback if any
        current_pc = self.get_pc_from_frame(0)
        for bp in self.bps:
            if current_pc == bp.addr and bp.callback is not None:
                bp.callback()

    def create_plt_breakpoints(self):
        """
        Creates breakpoints at the locations provided as arguments
        Breakpoints are disabled
        """

        if self.target is None:
            return

        for key in self.plt:
            entry = self.plt[key]
            bp = self.target.BreakpointCreateByAddress(entry.addr)
            bp.SetEnabled(False)
            entry.bp = bp

            breakpoint = self.Breakpoint()
            breakpoint.addr = entry.addr
            breakpoint.tag = self.Breakpoint.PLT_BP
            breakpoint.callback = self.on_plt_breakpoint
            breakpoint.bp_object = bp

            self.bps.append(breakpoint)

            # Log breakpoint set
            self.logger.info(bp)

    def create_dl_breakpoints(self):
        if self.target is None:
            return

        if self.target is None:
            return

        for key in self.plt:
            entry = self.plt[key]

            if key == "dlopen" or key == "dlclose" or key == "dlsym":
                breakpoint = self.Breakpoint()
                breakpoint.addr = entry.addr
                breakpoint.bp_object = self.target.BreakpointCreateByAddress(breakpoint.addr)

                if key == "dlopen":
                    breakpoint.tag = self.Breakpoint.DLOPEN_BP
                    breakpoint.callback = self.on_dlopen_called
                if key == "dlclose":
                    breakpoint.tag = self.Breakpoint.DLCLOSE_BP
                    breakpoint.callback = self.on_dlclose_called
                if key == "dlsym":
                    breakpoint.tag = self.Breakpoint.DLSYM_BP
                    breakpoint.callback = self.on_dlsym_called

                self.bps.append(breakpoint)

    def on_dlopen_called(self):
        self.logger.info("DLOPEN callback")

        breakpoint = self.Breakpoint()
        breakpoint.addr = self.get_pc_from_frame(1)
        breakpoint.tag = self.Breakpoint.RET_FROM_DLOPEN
        breakpoint.callback = self.on_return_from_dlopen
        breakpoint.bp_object = self.target.BreakpointCreateByAddress(breakpoint.addr)

        self.bps.append(breakpoint)

    def on_return_from_dlopen(self):
        self.logger.info("RETURN FROM DLOPEN")

    def on_dlclose_called(self):
        self.logger.info("DLCLOSE callback")

        breakpoint = self.Breakpoint()
        breakpoint.addr = self.get_pc_from_frame(1)
        breakpoint.tag = self.Breakpoint.RET_FROM_DLCLOSE
        breakpoint.callback = self.on_return_from_dlclose
        breakpoint.bp_object = self.target.BreakpointCreateByAddress(breakpoint.addr)

        self.bps.append(breakpoint)

    def on_return_from_dlclose(self):
        self.logger.info("RETURN FROM DLCLOSE")

    def on_dlsym_called(self):
        self.logger.info("DLSYM callback")

        breakpoint = self.Breakpoint()
        breakpoint.addr = self.get_pc_from_frame(1)
        breakpoint.tag = self.Breakpoint.RET_FROM_DLSYM
        breakpoint.callback = self.on_return_from_dlsym
        breakpoint.bp_object = self.target.BreakpointCreateByAddress(breakpoint.addr)

        self.bps.append(breakpoint)

    def on_return_from_dlsym(self):
        self.logger.info("RETURNED FROM DLSYM")

        addr = self.get_function_return_value()

        breakpoint = self.Breakpoint()
        breakpoint.addr = int(addr, 16)
        breakpoint.tag = self.Breakpoint.DYN_CALL_FUNC_BP
        breakpoint.callback = self.on_dynamic_function_call
        breakpoint.bp_object = self.target.BreakpointCreateByAddress(breakpoint.addr)

        self.bps.append(breakpoint)


    def on_dynamic_function_call(self):
        self.logger.info("CALL DYN FUNC")

        # Automatically create a breakpoint when returning from call
        breakpoint = self.Breakpoint()
        breakpoint.addr = self.get_pc_from_frame(1)
        breakpoint.tag = self.Breakpoint.RET_FROM_DYN_CALL
        breakpoint.callback = self.on_return_from_dynamic_function_call
        breakpoint.bp_object = self.target.BreakpointCreateByAddress(breakpoint.addr)

        self.bps.append(breakpoint)

    def on_return_from_dynamic_function_call(self):
        self.logger.info("RET FROM DYN FUNC CALL")


    def on_plt_breakpoint(self):
        self.logger.info("PLT bp hit")

        # Automatically create a breakpoint when returning from plt
        breakpoint = self.Breakpoint()
        breakpoint.addr = self.get_pc_from_frame(1)
        breakpoint.tag = self.Breakpoint.RET_FROM_PLT_BP
        breakpoint.callback = self.on_return_from_plt
        breakpoint.bp_object = self.target.BreakpointCreateByAddress(breakpoint.addr)

        self.bps.append(breakpoint)

    def on_return_from_plt(self):
        self.logger.info("Return from PLT")

    def read_plt(self):
        """
        After the process is started, read the plt data. Fill internal class
        data.
        """

        if self.process is None:
            return

        state = self.process.GetState()
        print state

        if state == lldb.eStateStopped:
            thread  = self.process.GetThreadAtIndex(0)
            frame0  = thread.GetFrameAtIndex(0)
            context = frame0.GetSymbolContext(lldb.eSymbolContextEverything)
            module  = context.GetModule()

            for sec in module.section_iter():
                if sec.GetName() == '.plt':
                    for sym in module.symbol_in_section_iter(sec):
                        if sym.GetName() is not None and sym.GetName().__str__().startswith('__') is False:
                            plt_func        = self.PltFuncInfo()
                            plt_func.name   = sym.GetName()
                            plt_func.sym    = sym
                            plt_func.addr   = sym.GetStartAddress().GetLoadAddress(self.target)

                            # Disassemble the first instruction and get the
                            # got address and value.
                            instrs = sym.GetInstructions(self.target)
                            got_plt_jmp = instrs[0]
                            got_plt_addr = got_plt_jmp \
                                .GetOperands(self.target)

                            addr_val = int(got_plt_addr[1:], 16)
                            got_plt_value = self.process \
                                .ReadPointerFromMemory(addr_val,
                                                       lldb.SBError())

                            plt_func.got_entry       = self.GotFuncInfo()
                            plt_func.got_entry.addr  = got_plt_addr[1:]
                            plt_func.got_entry.value = hex(got_plt_value.__int__()).rstrip("L")

                            self.plt[plt_func.name] = plt_func

        # Log the plt entries
        self.logger.info(self.plt)

    def read_got(self):
        """
        Read got.plt entries
        """

        for key in self.plt:
            entry = self.plt[key]

            got_plt_addr = entry.got_entry.addr
            got_plt_value = self.process.ReadPointerFromMemory(
                int(got_plt_addr, 16), lldb.SBError())

            entry.got_entry.value = hex(got_plt_value.__int__()).rstrip("L")

    # Debugging Status

    def get_process_state(self):
        """
        Return the state of the current target process as ProcessState.
        """

        if self.process is None:
            return

        state = self.process.GetState()
        if state == lldb.eStateStopped:
            return self.ProcessState.STOPPED

        return self.ProcessState.EXITED

    def get_function_return_value(self):
        """
        Get function return value
        """

        # Read value from the return register
        if self.process is None:
            return

        state = self.process.GetState()

        if state == lldb.eStateStopped:
            thread = self.process.GetThreadAtIndex(0)
            frame = thread.GetFrameAtIndex(0)

            GPRs = []
            registers = frame.GetRegisters()
            for regs in registers:
                if 'general purpose registers' in regs.GetName().lower():
                    GPRs = regs
                    break

            for reg in GPRs:
                # Intel x86 => return value is in EAX
                if 'eax' in reg.GetName().lower():
                    addr = reg.GetValue()
                    return addr

        return None

    def get_pc_from_frame(self, frame):
        """
        Return the current program counter
        """

        pc = None

        if self.process is None:
            return pc

        state = self.process.GetState()
        if state == lldb.eStateStopped:
            thread  = self.process.GetThreadAtIndex(0)
            frame   = thread.GetFrameAtIndex(frame)
            pc      = frame.GetPCAddress() \
                .GetLoadAddress(self.target).__int__()

        return pc

    def get_modules(self):
        """
        Get detailed info about the loaded_modules
        """

        final_data = []
        new_modules = self.read_modules()

        for m in new_modules:
            if m in self.static_modules:
                data = ["Statically loaded", m[0], m[1], m[2], m[3]]
            else:
                data = ["Dynamically loaded", m[0], m[1], m[2], m[3]]

            final_data.append(data)

        return final_data

    def read_modules(self):
        """
        Return a list of all the modules (shared libraries & co)
        loaded in the program address space.
        """

        if self.target is None:
            return

        modules = []
        for m in self.target.module_iter():
            start_addr = None
            end_addr = None
            mod_size = 0

            for sec in m.section_iter():
                load_addr = sec.GetLoadAddress(self.target)

                if hex(load_addr).rstrip("L") == "0xffffffffffffffff":
                    continue;

                # Module start address
                if start_addr is None:
                    offset = sec.GetFileOffset()
                    start_addr = load_addr - offset

                # Keep updating the end address until the last
                # section is found
                size = sec.size
                end_addr = load_addr + size
                mod_size += size

            if start_addr is not None:
                module = [hex(start_addr).rstrip("L"), hex(end_addr).rstrip("L"), hex(mod_size).rstrip("L"), m.__str__()]
                modules.append(module)

        return modules

    def get_symbol_module(self, address):
        """
        Gets the symbol located at the address indicated and its corresponding module.
        """

        sbaddr = lldb.SBAddress(address, self.target)
        if sbaddr is None:
            return None, None

        symbol = sbaddr.GetSymbol()
        module = sbaddr.GetModule()

        return symbol.GetName(), module.__str__()

    def get_plt_function_names(self):
        """
        Return a list of all the functions in the plt.
        """

        funcs = []
        for key in self.plt:
            entry = self.plt[key]
            funcs.append(entry.name)

        return funcs

    def get_got(self):
        """
        Return a list of all got plt entries.
        Each entry has [description, address, value].
        """
        got = []
        for key in self.plt:
            entry = self.plt[key]
            self.logger.info("Got entry: %s " % entry.name)
            got.append([entry.name, entry.got_entry.addr,
                        entry.got_entry.value])

        return got

    def get_func_info(self, func):
        """
        Get plt entry of a function.
        """

        info = None
        for key in self.plt:
            entry = self.plt[key]
            if entry.name == func:
                info = entry
                break

        return info

    def get_sections(self):
        """
        Get sections for current target.
        """

        if self.process is None:
            return

        pc = None
        sections = []
        state = self.process.GetState()

        if state == lldb.eStateStopped:
            thread  = self.process.GetThreadAtIndex(0)
            frame0  = thread.GetFrameAtIndex(0)
            pc      = frame0.GetPCAddress() \
                .GetLoadAddress(self.target).__int__()

        for mod in self.target.module_iter():
            for sec in mod.section_iter():
                if sec.GetName() in self.SECTIONS:
                    load_addr = sec.GetLoadAddress(self.target)
                    size = sec.size
                    mod_name = mod.__str__()
                    if pc >= load_addr and pc <= load_addr + size:
                        sec_data = [hex(load_addr).rstrip("L"), hex(int(load_addr) + size).rstrip("L"),
                                    mod_name + sec.GetName(), hex(pc).rstrip("L")]
                    else:
                        sec_data = [hex(load_addr).rstrip("L"), hex(load_addr + size).rstrip("L"),
                                    mod_name + sec.GetName(), ""]
                    sections.append(sec_data)

        return sections


    def get_previous_instruction_address(self, frame, current_addr):
        """
        Return the address of the previous instruction from a frame.
        If the current_addr is not found in the frame, the same address 
        is returned.
        """

        prev_addr = current_addr
        symbol  = frame.GetSymbol()
        if symbol:
            prev = current_addr

            insts = symbol.GetInstructions(self.target)
            for i in insts:
                load_addr = i.GetAddress() \
                        .GetLoadAddress(self.target).__int__()

                if load_addr == current_addr:
                        return prev_addr

                prev_addr = load_addr

        return prev_addr

    def is_compiled_with_debug_symbols(self):
        """
        Check if the exec is compiled with debug symbols (-g).
        """
        if self.target:
            module = self.target.FindModule(self.target.GetExecutable())
            for cu in module.get_compile_units_array():
                for lineEntry in cu:
                    return True

        return False

    # Modifty stuff

    def write_word_to_address(self, addr, word):
        """
        Write a word (4 bytes on 32b) at the given address.
        Much WOW. Such code. Very hack.
        """

        if self.process is None:
            return

        word = str(hex(word))
        word = word[2:].zfill(8)[::-1]

        value = ''
        for i, j in zip(word[::2], word[1::2]):
            value += j
            value += i

        error = lldb.SBError()
        self.process.WriteMemory(addr, value.decode("hex"), error)
        if not error.Success():
            return None

        # Update internal data structure for got entries
        self.read_got()

        return 0

    # Printing

    def print_frame(self, idx):
        """
        Returns a message with the asm instructions of a frame relative to
        the current execution point. Also returns the address of the
        current instruction (PC).
        idx - frame to print (0 = current frame; 1 = previous frame; etc)
        """

        if self.process is None:
            return None, None

        count       = 0
        pc_offset   = 0
        lines       = []
        text        = ''

        state = self.process.GetState()
        if state == lldb.eStateStopped:
            thread  = self.process.GetThreadAtIndex(0)
            frame   = thread.GetFrameAtIndex(idx)
            symbol  = frame.GetSymbol()
            pc      = frame.GetPCAddress().GetLoadAddress(self.target)

            if symbol:
                offset = 0

                insts = symbol.GetInstructions(self.target)
                for i in insts:
                    load_addr   = i.GetAddress() \
                        .GetLoadAddress(self.target).__int__()
                    offset      = i.GetAddress().__int__() \
                        - symbol.GetStartAddress().__int__()
                    sym_offset  = "%s + %u" % (symbol.GetName(), offset)
                    mnemonic    = i.GetMnemonic(self.target)
                    operands    = i.GetOperands(self.target)
                    comment     = i.GetComment(self.target)

                    line = ''
                    if comment:
                        line += "0x%0.7x <%s> %8s %s \t\t ; %s" \
                            % (load_addr, sym_offset,
                                mnemonic, operands, comment)
                    else:
                        line += "0x%0.7x <%s> %8s %s \t\t" \
                            % (load_addr, sym_offset, mnemonic, operands)

                    if load_addr == pc.__int__():
                        pc_offset = count - 1 if idx else count

                    lines.append(line)
                    count += 1

            for i in range(count):
                if i == pc_offset:
                    text += "-->\t%s\n" % lines[i]
                else:
                    text += "\t%s\n" % lines[i]

            if text == '':
                text = frame.Disassemble()

                for item in text.split("\n"):
                    if "->" in item:
                        return pc_offset, text
                    pc_offset += 1

        return pc_offset, text

    def print_function(self, idx):
        """
        If debug information is available for the function at the current
        program counter from frame idx, print the function. Otherwise write a message.
        """

        if self.process is None:
            return None, None

        code = ''
        line = -1

        if self.is_compiled_with_debug_symbols() is False:
            code = 'The original code can\'t be displayed. ' \
                'The program was not compiled with debugging symbols.'
            line = -2

            return line, code

        state = self.process.GetState()
        if state == lldb.eStateStopped:
            thread  = self.process.GetThreadAtIndex(0)
            frame = thread.GetFrameAtIndex(idx)
            pc_addr = self.get_previous_instruction_address(frame,
                frame.GetPCAddress().GetLoadAddress(self.target))
            addr = lldb.SBAddress()
            addr.SetLoadAddress(pc_addr, self.target)
            function = frame.GetFunction()
            mod_name = frame.GetModule().GetFileSpec().GetFilename()

            if not function:
                code = 'The original code can\'t be displayed. ' \
                    'Either the program was not compiled with debugging ' \
                    'symbols or the current frame does not have a corresponding ' \
                    'function in the source code. \n Please check the assembly ' \
                    'code for more details.'
            else:
                # Debug info is available for 'function'.
                func_name = frame.GetFunctionName()
                dir_name = frame.GetLineEntry().GetFileSpec().GetDirectory()
                file_name = frame.GetLineEntry().GetFileSpec().GetFilename()
                line_num = addr.GetLineEntry().GetLine()
                line_num = line_num - 1

                try:
                    file = open(dir_name + '/' + file_name, 'r')
                except (OSError, IOError) as e:
                    return line, "Could not find source file."

                code = file.read()
                file.close()
                line = line_num

        return line, code
