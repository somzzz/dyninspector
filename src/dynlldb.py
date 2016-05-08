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
    logger  = logging.getLogger('dynload_lldb')

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

    class GotFuncInfo(object):
        """
        An entry in the .got table: (addres, pointer value).
        """

        def __init__(self):

            self.addr   = None
            self.value  = None

    class PltFuncInfo(object):
        """
        A stub in the .got.plt section.
        """

        def __init__(self):

            self.name       = None
            self.sym        = None
            self.plt_addr   = None
            self.bp         = None
            self.got_entry  = None

    def __init__(self):

        # Debugger insance
        self.debugger = lldb.SBDebugger.Create()
        self.debugger.SetAsync(False)

        # Target info
        self.elf            = None
        self.target_elf     = None
        self.process        = None
        self.plt_entries    = []
        self.plt_symbols    = {}
        self.plt            = {}
        self.got            = {}
        self.saved_pc       = None

        # Breakpoints
        self.bps            = []
        self.bp_func_name   = None
        self.bp_func        = None
        self.bp_main        = None

    def set_elf(self, elf):
        """ Create a target.
            elf : elf executable path
        """

        self.elf = elf

        if self.target_elf is not None:
            self.target_elf.Clear()

        self.target_elf = self.debugger.CreateTargetWithFileAndArch(
            self.elf.__str__(), lldb.LLDB_ARCH_DEFAULT)

        if self.target_elf:
            return 0
        else:
            return None

    def set_breakpoint(self, func, en):
        """
        Set breakpoints for a target. Enable or disable them.
        Breakpoints can only be set for functions in the .plt.
        """

        self.bp_func_name = func

        if self.target_elf:
            entry = self.plt[func]
            if entry is not None:
                entry.bp.SetEnabled(en)

            for breakpoint in self.target_elf.breakpoint_iter():
                self.logger.info(breakpoint.__str__() + " enabled = "
                                 + str(breakpoint.IsEnabled()))

    def set_breakpoint_on_return(self):
        """
        Set a breakpoint on return from the the current frame.
        Useful for stopping after returning from the .plt.
        """

        if self.target_elf is None:
            return

        stack_p = self.get_pc_from_frame(1)
        self.target_elf.BreakpointCreateByAddress(stack_p)

        # Log breakpoint set
        self.logger.info("Set bp on return from plt 0x%0.7X" % stack_p)

    def run_target(self):
        """
        Run the target. Create a process and read its plt data.
        """

        if self.target_elf is None:
            return

        # Set the main bp before start
        self.bp_main = self.target_elf.BreakpointCreateByName(
            'main',
            self.target_elf.GetExecutable().GetFilename())

        # Run target
        self.process = self.target_elf.LaunchSimple(None, None, os.getcwd())
        if self.process is None:
            return None

        # Create breakpoints for plt entries
        self.read_plt()
        self.create_plt_breakpoints()

        return self.process

    def stop_target(self):
        """
        Stop the current lldb session. Disable breakpoints.
        Clear all internal data related to the session.
        """

        if self.target_elf is None:
            return

        self.logger.info("stop_target")

        if self.process:
            self.process.Stop()

        self.target_elf.DeleteAllBreakpoints()

        # Reset internal data
        self.process        = None
        self.plt_entries    = []
        self.plt_symbols    = {}
        self.plt            = {}

        self.bps            = []
        self.bp_func_name   = None
        self.bp_func        = None
        self.bp_main        = None

        self.set_elf(self.elf)

    def continue_target(self):
        """
        Continue execution of the target if process was paused on a
        breakpoint. We only have plt breakpoints.
        Return a message with the state of the process after this call.
        """

        if self.process is None:
            return None, None

        state = self.process.GetState()
        if state == lldb.eStateStopped:
            self.process.Continue()
            self.saved_pc = self.get_pc_from_frame(1)
            self.logger.info(self.process)

            # Update internal data structure for got entries
            self.read_got()

            # Check if we stopped in a plt breakpoint and set breakpoint on SP

        return state, self.process.__str__()

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

            # Update internal data structure for got entries
            self.read_got()

        return state, self.process.__str__()

    def step_over(self):
        """
        Return to the previous frame.
        """

        if self.process is None:
            return None, None

        state = self.process.GetState()
        if state == lldb.eStateStopped:
            thread = self.process.GetThreadAtIndex(0)
            frame0  = thread.GetFrameAtIndex(0)
            thread.StepOutOfFrame(frame0)

            # Update internal data structure for got entries
            self.read_got()

        return state, self.process.__str__()

    def create_plt_breakpoints(self):
        """
        Creates breakpoints at the locations provided as arguments
        Breakpoints are disabled
        """

        if self.target_elf is None:
            return

        for key in self.plt:
            entry = self.plt[key]
            bp = self.target_elf.BreakpointCreateByAddress(entry.addr)
            bp.SetEnabled(False)
            entry.bp = bp

            # Log breakpoint set
            self.logger.info(bp)

    def read_plt(self):
        """
        After the process is started, read the plt data. Fill internal class
        data.
        """

        if self.process is None:
            return

        state = self.process.GetState()

        if state == lldb.eStateStopped:
            thread  = self.process.GetThreadAtIndex(0)
            frame0  = thread.GetFrameAtIndex(0)
            context = frame0.GetSymbolContext(lldb.eSymbolContextEverything)
            module  = context.GetModule()

            for sec in module.section_iter():
                if sec.GetName() == '.plt':
                    addrs = lldb.SBAddress()
                    addrs.SetAddress(sec, 16)

                    addre = lldb.SBAddress()
                    addre.SetAddress(sec, sec.size)

                    i = 1
                    addr = addrs
                    while addr.__hex__() != addre.__hex__():
                        sym = addr.GetSymbol()

                        if sym.GetName().__str__().startswith('__') is False:
                            plt_func        = self.PltFuncInfo()
                            plt_func.name   = sym.GetName()
                            plt_func.sym    = sym
                            plt_func.addr   = int(addr.__hex__(), 16)

                            # Disasemble the first instruction and get the
                            # got address and value.
                            instrs = sym.GetInstructions(self.target_elf)
                            got_plt_jmp = instrs[0]
                            got_plt_addr = got_plt_jmp \
                                .GetOperands(self.target_elf)

                            addr_val = int(got_plt_addr[1:], 16)
                            got_plt_value = self.process \
                                .ReadPointerFromMemory(addr_val,
                                                       lldb.SBError())

                            plt_func.got_entry       = self.GotFuncInfo()
                            plt_func.got_entry.addr  = got_plt_addr[1:]
                            plt_func.got_entry.value = got_plt_value.__hex__()

                            self.plt[plt_func.name] = plt_func

                        i += 1
                        addr.SetAddress(sec, i * 16)

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

            entry.got_entry.value = got_plt_value.__hex__()

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
                .GetLoadAddress(self.target_elf).__int__()

        return pc

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
                .GetLoadAddress(self.target_elf).__int__()

        for mod in self.target_elf.module_iter():
            for sec in mod.section_iter():
                if sec.GetName() in self.SECTIONS:
                    load_addr = sec.GetLoadAddress(self.target_elf)
                    size = sec.size
                    mod_name = mod.__str__()
                    if pc >= load_addr and pc <= load_addr + size:
                        sec_data = [hex(load_addr), hex(load_addr + size),
                                    mod_name + sec.GetName(), hex(pc)]
                    else:
                        sec_data = [hex(load_addr), hex(load_addr + size),
                                    mod_name + sec.GetName(), ""]
                    sections.append(sec_data)

        return sections

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

        state = self.process.GetState()
        if state == lldb.eStateStopped:
            thread  = self.process.GetThreadAtIndex(0)
            frame   = thread.GetFrameAtIndex(idx)
            symbol  = frame.GetSymbol()
            pc      = frame.GetPCAddress().GetLoadAddress(self.target_elf)

            if symbol:
                offset = 0

                insts = symbol.GetInstructions(self.target_elf)
                for i in insts:
                    load_addr   = i.GetAddress() \
                        .GetLoadAddress(self.target_elf).__int__()
                    offset      = i.GetAddress().__int__() \
                        - symbol.GetStartAddress().__int__()
                    sym_offset  = "%s + %u" % (symbol.GetName(), offset)
                    mnemonic    = i.GetMnemonic(self.target_elf)
                    operands    = i.GetOperands(self.target_elf)
                    comment     = i.GetComment(self.target_elf)

                    line = ''
                    if comment:
                        line += "0x%0.7X <%s> %8s %s \t\t ; %s" \
                            % (load_addr, sym_offset,
                                mnemonic, operands, comment)
                    else:
                        line += "0x%0.7X <%s> %8s %s \t\t" \
                            % (load_addr, sym_offset, mnemonic, operands)

                    if load_addr == pc.__int__():
                        pc_offset = count - 1 if idx else count

                    lines.append(line)
                    count += 1

        text = ''
        for i in range(count):
            if i == pc_offset:
                text += "-->\t%s\n" % lines[i]
            else:
                text += "\t%s\n" % lines[i]

        return pc_offset, text