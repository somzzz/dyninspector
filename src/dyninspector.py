"""
The script contains the main class for the DynInspector tool.
Run this script to start the app.
"""

import sys
import logging

import PySide
from PySide import QtCore, QtGui

from dynlldb import DynLldb
import log
import gui

DEBUG   = "DEBUG"
INFO    = "INFO"


class DynInspector(QtCore.QObject):
    """
    Middleman class for the project. Interacts with the dynlldb module
    and communicates with the gui module.
    """

    # Constants
    STEPS   = 5

    # Define all communication channels with the GUI (signals)

    # From GUI
    set_elf_sig         = QtCore.Signal(str)
    console_output_sig  = QtCore.Signal(str)
    run_target_sig      = QtCore.Signal()
    continue_target_sig = QtCore.Signal()
    set_breakpoint_sig  = QtCore.Signal(str)
    set_app_mode_sig    = QtCore.Signal(int)

    # To GUI
    clear_gui_sig               = QtCore.Signal()
    add_func_selector_sig       = QtCore.Signal(str)
    write_asm_display_sig       = QtCore.Signal(str, int)
    write_console_output_sig    = QtCore.Signal(str)
    set_cont_btn_sig            = QtCore.Signal(bool)
    update_got_plt_table        = QtCore.Signal(list, bool)
    update_sections_table       = QtCore.Signal(list, bool)
    update_modules_table        = QtCore.Signal(list, bool)

    # Logging
    logger      = logging.getLogger('dynloader')
    step        = STEPS

    class ExecStates(object):
        """
        Possible states for the debugger. We must always be
        aware what the program is doing for the user's sake.
        """

        NONE                    = 0
        START_BP_SET            = 1
        ON_BP_SHOW_PREV_FRAME   = 3
        ON_BP_SHOW_CURR_FRAME   = 4
        STEP_INST_PLT           = 5
        SKIP_TO_NEXT_BP         = 6
        EXIT                    = 7
        INVOKE_LOADER           = 8
        CALL_FUNC               = 9
        RET                     = 10

        def __init__(self):
            pass

    state = ExecStates.NONE

    class AppMode(object):
        """
        App mode
        """

        DYN_LINK    =   0
        DYN_LOAD    =   1

        def __init__(self):
            pass

    mode = AppMode.DYN_LINK

    def __init__(self):
        QtCore.QObject.__init__(self)
        self.debugger   = DynLldb()
        self.elf        = None
        self.bp_func    = None

        self.connect_slots()

    def connect_slots(self):
        """
        Connect the methods for receiving commands from the gui.
        """

        self.set_elf_sig.connect(self.set_elf)
        self.run_target_sig.connect(self.run_target)
        self.continue_target_sig.connect(self.continue_target)
        self.set_breakpoint_sig.connect(self.set_breakpoint)
        self.set_app_mode_sig.connect(self.set_app_mode)

    def set_app_mode(self, mode):
        self.mode = mode

        self.logger.info("MODE IS " + str(mode))

        # Restart App in new mode
        self.clear_gui_sig.emit()

        if self.elf is not None:
            self.set_elf(self.elf)

    def set_elf(self, elf):
        """
        Set the target elf. Command gui to display appropriate messages.
        """

        self.logger.info('set elf ' + elf)
        self.elf = elf
        rc = self.debugger.set_elf(elf)

        # Console message
        if rc is not None:
            self.write_console_output_sig.emit(
                ("[%s] Elf target set to %s" % (DEBUG, elf)))
        else:
            self.write_console_output_sig.emit(
                "[%s] Could not set elf target." % DEBUG)

        self.state = self.ExecStates.START_BP_SET

    def run_target(self):
        """
        Run the current target. Read info from the dynlldb module.
        Command the gui to display appropriate messages.
        """

        self.logger.info('run_target')

        # Clear all fields in GUI
        self.clear_gui_sig.emit()

        # Stop a previous target if it had a process running
        if self.state != self.ExecStates.START_BP_SET:
            self.debugger.stop_target()

        if self.mode == self.AppMode.DYN_LINK:
            self.run_target_dynlink()
        elif self.mode == self.AppMode.DYN_LOAD:
            self.run_target_dynload()

        self.state = self.ExecStates.ON_BP_SHOW_PREV_FRAME


    def run_target_dynlink(self):
        process = self.debugger.run_target()
        self.debugger.create_plt_breakpoints()

        # Console Output
        if process is None:
            self.write_console_output_sig.emit(
                "[%s] Could not launch target." % DEBUG)
        else:
            self.write_console_output_sig.emit(
                "[%s] Target started: %s" % (DEBUG, process.__str__()))

        # Populate breakpoint selector in GUI
        for func in self.debugger.get_plt_function_names():
            self.add_func_selector_sig.emit(func)

        data = self.debugger.get_got()
        self.update_got_plt_table_data(data)

        data = self.debugger.get_sections()
        self.update_sections_table_data(data)

        # Display the current frame
        pc, code = self.debugger.print_frame(0)
        self.write_asm_display_sig.emit(code, pc)

        
    def run_target_dynload(self):
        process = self.debugger.run_target()
        self.debugger.create_dl_breakpoints()

        # Display the current frame
        pc, code = self.debugger.print_frame(0)
        self.write_asm_display_sig.emit(code, pc)

        # Modules table
        data = self.debugger.get_modules()
        self.update_modules_table_data(data)

    def continue_target(self):
        if self.mode == self.AppMode.DYN_LINK:
            self.continue_target_dynlink()
        elif self.mode == self.AppMode.DYN_LOAD:
            self.continue_target_dynload()

    def continue_target_dynload(self):

        self.debugger.get_modules()

        if self.state == self.ExecStates.ON_BP_SHOW_PREV_FRAME:
            breakpoint = self.debugger.continue_target()

            # Check of program has ended
            state = self.debugger.get_process_state()
            if state == self.debugger.ProcessState.EXITED:
                self.write_console_output_sig.emit("[%s] Execution finished. "
                    "Process exited normally." % (DEBUG))
                self.set_cont_btn_sig.emit(False)

                return

            if breakpoint.tag == self.debugger.Breakpoint.RET_FROM_DYN_CALL:
                pc, code = self.debugger.print_frame(0)
                self.write_asm_display_sig.emit(code, pc)
                return

            # Program stopped on breakpoint
            pc, code = self.debugger.print_frame(1)
            self.write_asm_display_sig.emit(code, pc)

            self.logger.info("SHOW PREV FRAME")
            if breakpoint.tag == self.debugger.Breakpoint.DLOPEN_BP or \
                breakpoint.tag == self.debugger.Breakpoint.DLCLOSE_BP or \
                    breakpoint.tag == self.debugger.Breakpoint.DLSYM_BP:
                breakpoint = self.debugger.continue_target()

            if breakpoint.tag == self.debugger.Breakpoint.DYN_CALL_FUNC_BP or \
                breakpoint.tag == self.debugger.Breakpoint.RET_FROM_DLOPEN or \
                   breakpoint.tag == self.debugger.Breakpoint.RET_FROM_DLSYM or \
                    breakpoint.tag == self.debugger.Breakpoint.RET_FROM_DLCLOSE:
                self.state = self.ExecStates.ON_BP_SHOW_CURR_FRAME

        elif self.state == self.ExecStates.ON_BP_SHOW_CURR_FRAME:
            self.logger.info("SHOW CURR FRAME")
            pc, code = self.debugger.print_frame(0)
            self.write_asm_display_sig.emit(code, pc)

            self.state = self.ExecStates.ON_BP_SHOW_PREV_FRAME

        # Modules table
        data = self.debugger.get_modules()
        self.update_modules_table_data(data)


    def continue_target_dynlink(self):
        """
        Continue running the target elf. Depending on the execution point
        we can either step to the next instruction (eg. when in the .plt)
        or skip right to the next breakpoint (eg. after the loader was
        invoked). Each case interacts differently with the gui, thus the
        separate cases.
        Kind of too long...
        """

        self.logger.info('continue target')
        func_info = self.debugger.get_func_info(self.bp_func)

        if self.state == self.ExecStates.ON_BP_SHOW_PREV_FRAME:
            code, _ = self.debugger.continue_target()

            pc, code = self.debugger.print_frame(1)
            self.write_asm_display_sig.emit(code, pc)

            state = self.debugger.get_process_state()
            if state == self.debugger.ProcessState.STOPPED:
                self.state = self.ExecStates.ON_BP_SHOW_CURR_FRAME
                pc = self.debugger.get_pc_from_frame(0)
                #self.debugger.set_breakpoint_on_return()

                self.write_console_output_sig.emit(
                    "[%s] Process stopped on breakpoint. The current "
                    "instruction calls the function monitored." % DEBUG)

                self.write_console_output_sig.emit("[%s] The function "
                    "call is redirected to the .PLT section at address "
                    "0x%0.7X" % (DEBUG, pc))
            else:
                self.state = self.ExecStates.EXIT

        elif self.state == self.ExecStates.ON_BP_SHOW_CURR_FRAME:
            pc, code = self.debugger.print_frame(0)
            self.write_asm_display_sig.emit(code, pc)
            pc = self.debugger.get_pc_from_frame(0)

            self.write_console_output_sig.emit("[%s] The function %s has "
                "a corresponding entry in the .GOT.PLT section at address "
                "%s." % (DEBUG, func_info.name, func_info.got_entry.addr))

            self.write_console_output_sig.emit("[%s] We jump to the "
                "address indicated by the .GOT.PLT entry: "
                " %s" % (DEBUG, func_info.got_entry.value))

            self.state = self.ExecStates.STEP_INST_PLT

        elif self.state == self.ExecStates.STEP_INST_PLT:

            prev_pc = self.debugger.get_pc_from_frame(0)
            code, _ = self.debugger.step_instruction()
            current_pc = self.debugger.get_pc_from_frame(0)

            pc, code = self.debugger.print_frame(0)
            self.write_asm_display_sig.emit(code, pc)

            # We are in the PLT, if the got.plt indicates the next plt
            # instruction, then the loader is to be called. Otherwise
            # we have a direct jump to the code in the library.
            if prev_pc + 6 == current_pc:
                self.step = 4
                self.state = self.ExecStates.INVOKE_LOADER

                self.write_console_output_sig.emit("[%s] It is the first "
                    "call to %s. Lazy binding takes place. Jump returns to "
                    "the .PLT. The dynamic linker will be "
                    "called." % (DEBUG, func_info.name))
            else:
                self.state = self.ExecStates.CALL_FUNC
                self.write_console_output_sig.emit("[%s] It is not the first"
                    " call to %s. The address indicated by the .GOT.PLT "
                    "is %s and is the actual routine address "
                    "." % (DEBUG, func_info.name, func_info.got_entry.value))

                self.write_console_output_sig.emit("[%s] In the actual "
                    "routine for the function." % (DEBUG))

        elif self.state == self.ExecStates.INVOKE_LOADER:
            self.logger.info("step instruction in invoke loader "
                             + str(self.step))

            code, _ = self.debugger.step_instruction()

            (pc, code) = self.debugger.print_frame(0)
            self.write_asm_display_sig.emit(code, pc)

            if self.step == 4:
                self.write_console_output_sig.emit("[%s] Program jumps at "
                    "the beginnig of the .plt section. Here there are "
                    "a couple of instructions "
                    "which invoke the dynamic linker." % (DEBUG))
            if self.step == 1:        
                self.write_console_output_sig.emit("[%s] Dynamic linker "
                    "invoked. It will resolve the address of the function "
                    "called and set the correct address in the .got.plt. "
                    "It also calls the function."% (DEBUG))

            self.step -= 1
            if self.step == 0:
                self.state = self.ExecStates.RET

        elif self.state == self.ExecStates.RET:
            code, _ = self.debugger.continue_target()

            pc, code = self.debugger.print_frame(0)
            self.write_asm_display_sig.emit(code, pc)

            self.logger.info("Returned from PLT")
            self.write_console_output_sig.emit("[%s] Return to caller "
                "context." % (DEBUG))

            self.state = self.ExecStates.ON_BP_SHOW_PREV_FRAME

        elif self.state == self.ExecStates.CALL_FUNC:
            self.logger.info("in call_func")

            code, _ = self.debugger.continue_target()

            pc, code = self.debugger.print_frame(0)
            self.write_asm_display_sig.emit(code, pc)

            self.state = self.ExecStates.ON_BP_SHOW_PREV_FRAME
            self.write_console_output_sig.emit("[%s] Return to caller "
                "context." % (DEBUG))

        else:
            self.write_console_output_sig.emit("[%s] Execution finished. "
                "Process exited normally." % (DEBUG))
            self.set_cont_btn_sig.emit(False)

        # Update got table data
        data = self.debugger.get_got()
        self.update_got_plt_table_data(data)

        # Update sections table data
        data = self.debugger.get_sections()
        self.update_sections_table_data(data)

    def set_breakpoint(self, func):
        """
        Sets the program brakpoint on a function from the .plt. Only
        one breakpoint can be active at a time.
        """

        if func == "":
            return

        if self.bp_func is not None:
            self.debugger.set_breakpoint(self.bp_func, False)

        self.bp_func = func
        self.debugger.set_breakpoint(self.bp_func, True)

        # Console output
        self.write_console_output_sig.emit("[%s] Breakpoint set on "
            "function %s." % (DEBUG, func))

    def exit(self):
        """
        Stop program.
        """

        self.debugger.stop_target()
        self.exit()

    def update_got_plt_table_data(self, new_data):
        """
        Update the gui with appropriate data from the .got.plt.
        """

        self.update_got_plt_table.emit([], True)
        for entry in new_data:
            self.logger.info("Signal emit to update got plt table data  "
                             + entry.__str__())
            self.update_got_plt_table.emit(entry, False)

    def update_sections_table_data(self, new_data):
        """
        Update the gui with appropriate data about the program sections.
        Basically shows the mapped libraries.
        """

        self.update_sections_table.emit([], True)
        for entry in new_data:
            self.update_sections_table.emit(entry, False)

    def update_modules_table_data(self, new_data):
        """
        Update the gui with appropriate data about the program sections.
        Basically shows the mapped libraries.
        """

        self.update_modules_table.emit([], True)
        for entry in new_data:
            self.update_modules_table.emit(entry, False)

def main():
    """
    Start the GUI and the dyninspector.
    """

    log.init_logger()
    logger = logging.getLogger('main')

    logger.info(PySide.__version__)
    logger.info(PySide.QtCore.__version__)

    qt_app = QtGui.QApplication(sys.argv)

    dyninspector = DynInspector()

    window = gui.MainWindow(dyninspector)
    window.run()

    sys.exit(qt_app.exec_())


if __name__ == "__main__":
    main()
