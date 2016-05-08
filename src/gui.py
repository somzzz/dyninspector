"""
This module contains the graphical user interface for the
dyninspector tool.
"""

import logging
from PySide import QtCore, QtGui


class MainWindow(QtGui.QWidget):
    """
    GUI has only one windows with several widgets.
    This is it!
    """

    # String constants
    START_BTN       = "Start"
    ELF_SELECT_BTN  = "Open ELF executable"
    CONTINUE_BTN    = "Continue"

    # Logging
    logger = logging.getLogger('gui')

    def __init__(self, worker):
        QtGui.QWidget.__init__(self)

        # Background thread & info
        self.elf            = None
        self.worker         = worker
        self.worker_thread  = None

        # Window title
        self.setWindowTitle('DynInspector')
        self.showMaximized()

        # Components
        self.asm_display        = None
        self.plt_display        = None
        self.got_plt_table      = None
        self.sections_table     = None
        self.console_output     = None
        self.elf_button         = None
        self.func_selector      = None
        self.restart_button     = None
        self.continue_button    = None

        # Layouts
        self.layout     = QtGui.QVBoxLayout()
        self.top_layout = QtGui.QHBoxLayout()
        self.bot_layout = QtGui.QHBoxLayout()

        # Data
        self.got_plt_table_data     = []
        self.tablemodel             = None
        self.tableheader            = None

        self.sections_table_data     = []
        self.sections_tablemodel    = None
        self.sections_tableheader   = None

        self.build_top_layout()
        self.build_bottom_layout()

        self.layout.addLayout(self.top_layout)
        self.layout.addLayout(self.bot_layout)

        self.setLayout(self.layout)

        self.connect_signals()

    def connect_signals(self):
        """
        Connect methods to receive data from the background worker.
        """

        self.worker.clear_gui_sig.connect(self.clear)
        self.worker.add_func_selector_sig.connect(self.add_func_selector)
        self.worker.write_asm_display_sig.connect(self.write_asm_display)
        self.worker.write_console_output_sig.connect(self.write_console_output)
        self.worker.set_cont_btn_sig.connect(self.set_continue_btn)
        self.worker.update_got_plt_table.connect(self.update_got_plt_table)
        self.worker.update_sections_table.connect(self.update_sections_table)

    def run(self):
        """
        Start the GUI thread.
        """

        self.worker_thread = QtCore.QThread(self)
        self.worker.moveToThread(self.worker_thread)

        self.worker_thread.start()
        self.show()

    def closeEvent(self, event):
        """
        Needed to close the background worker thread
        """

        self.worker_thread.exit()

    def clear(self):
        """
        Clear all widgets.
        """

        self.logger.info("GUI cleared")

        self.asm_display.clear()
        #self.plt_display.clear()
        self.console_output.clear()

        self.func_selector.clear()
        self.clear_got_table()
        self.clear_sections_table()

    def clear_got_table(self):
        """
        Clear data from the .got.plt widget.
        """

        del self.got_plt_table_data[:]
        self.got_plt_table.model().layoutChanged.emit()

    def clear_sections_table(self):
        """
        Clear data from the program sections widget.
        """

        del self.sections_table_data[:]
        self.sections_table.model().layoutChanged.emit()

    def build_top_layout(self):
        """
        Build the upper part of the display.
        """

        # Asm display
        self.asm_display = QtGui.QTextEdit(self)
        self.asm_display.setReadOnly(True)
        self.asm_display.setLineWrapMode(QtGui.QTextEdit.NoWrap)

        font = self.asm_display.font()
        font.setFamily("Courier")
        font.setPointSize(10)

        self.top_layout.addWidget(self.asm_display)

        # .got.plt / .plt display
        self.got_plt_table = QtGui.QTableView()

        self.tableheader = ['Function name', 'Location/Address', 'Value']
        self.tablemodel = GotPltTableModel(self.got_plt_table_data,
                                           self.tableheader, self)
        self.got_plt_table.setModel(self.tablemodel)

        self.got_plt_table.setShowGrid(False)
        self.got_plt_table.resizeColumnsToContents()
        self.got_plt_table.resizeRowsToContents()

        vh = self.got_plt_table.verticalHeader()
        vh.setVisible(False)

        hh = self.got_plt_table.horizontalHeader()
        hh.setStretchLastSection(True)

        self.got_plt_table.resizeColumnsToContents()

        self.top_layout.addWidget(self.got_plt_table)

        # Control menu
        control_layout = self.build_control_menu()
        self.top_layout.addLayout(control_layout)

    def build_bottom_layout(self):
        """
        Build the lower part of the display.
        """

        self.console_output = QtGui.QTextEdit(self)
        self.console_output.setReadOnly(True)
        self.console_output.setLineWrapMode(QtGui.QTextEdit.NoWrap)

        font = self.console_output.font()
        font.setFamily("Courier")
        font.setPointSize(10)

        self.bot_layout.addWidget(self.console_output)

        # sections table
        self.sections_table = QtGui.QTableView()

        self.sections_tableheader = ['First Address', 'Last Address',
                                     'Name', 'Program Counter']
        self.sections_tablemodel = ElfSectionsTableModel(
            self.sections_table_data,
            self.sections_tableheader,
            self)
        self.sections_table.setModel(self.sections_tablemodel)

        self.sections_table.setShowGrid(True)
        self.sections_table.resizeColumnsToContents()
        self.sections_table.resizeRowsToContents()

        vh = self.sections_table.verticalHeader()
        vh.setVisible(False)

        hh = self.sections_table.horizontalHeader()
        hh.setStretchLastSection(False)

        self.sections_table.resizeColumnsToContents()
        self.bot_layout.addWidget(self.sections_table)

    def build_control_menu(self):
        """
        Create the control menu.
        """

        control_menu = QtGui.QVBoxLayout()

        # Set executable button
        self.elf_button = QtGui.QPushButton(self)
        self.elf_button.setText(self.ELF_SELECT_BTN)
        self.elf_button.clicked.connect(self.elf_button_clicked)

        control_menu.addWidget(self.elf_button)

        # Drop down widget
        self.func_selector = QtGui.QComboBox()
        self.func_selector.currentIndexChanged.connect(self.selection_change)

        control_menu.addWidget(self.func_selector)

        # Restart button
        self.restart_button = QtGui.QPushButton(self)
        self.restart_button.setText(self.START_BTN)
        self.restart_button.clicked.connect(self.restart_button_clicked)

        control_menu.addWidget(self.restart_button)

        # Continue button
        self.continue_button = QtGui.QPushButton(self)
        self.continue_button.setText(self.CONTINUE_BTN)
        self.continue_button.setEnabled(False)
        self.continue_button.clicked.connect(self.continue_button_clicked)

        control_menu.addWidget(self.continue_button)

        return control_menu

    def elf_button_clicked(self):
        """
        OnClick method for the set_elf button.
        """

        self.elf = QtGui.QFileDialog.getOpenFileName()[0]
        self.worker.set_elf_sig.emit(self.elf)

    def restart_button_clicked(self):
        """
        OnClick method for the start program button.
        """

        self.worker.run_target_sig.emit()
        self.continue_button.setEnabled(True)

    def continue_button_clicked(self):
        """
        OnClick method for the continue program button.
        """

        self.worker.continue_target_sig.emit()

    def set_continue_btn(self, en):
        """
        Enables or disables the continue button.
        """

        self.continue_button.setEnabled(en)

    def selection_change(self, i):
        """
        On combobox selection change, notify the worker thread.
        """

        text = str(self.func_selector.currentText())
        self.logger.info('selected ' + text)
        self.worker.set_breakpoint_sig.emit(text)

    def add_func_selector(self, func):
        """
        Adds items to the function selector combobox.
        """

        self.func_selector.addItem(func)

    def write_asm_display(self, text, line):
        """
        Writes text to the asm display. The old text is
        replaced.
        """

        self.asm_display.setText(text)
        self.highlight(line)
        for _ in range(line):
            self.asm_display.moveCursor(QtGui.QTextCursor.Down)

    def write_console_output(self, text):
        """
        Appends text to the console output
        """

        self.logger.info("Console_output: " + text)

        co_text = self.console_output.toPlainText()
        self.console_output.setText(co_text + '\n' + text)
        self.console_output.moveCursor(QtGui.QTextCursor.End)

    def highlight(self, line):
        """
        Color a specific line on the asm_display widget.
        The line represents the current instruction in this case.
        """

        cursor = self.asm_display.textCursor()
        cursor.movePosition(QtGui.QTextCursor.Start)

        for _ in range(line):
            cursor.movePosition(QtGui.QTextCursor.Down)

        cursor.movePosition(QtGui.QTextCursor.EndOfLine)
        cursor.movePosition(QtGui.QTextCursor.StartOfLine,
                            QtGui.QTextCursor.KeepAnchor)
        tmp = cursor.blockFormat()
        tmp.setBackground(QtGui.QBrush(QtCore.Qt.yellow))
        cursor.setBlockFormat(tmp)

        hi_selection = QtGui.QTextEdit.ExtraSelection()
        hi_selection.cursor = cursor
        self.asm_display.setExtraSelections([hi_selection])

    def update_got_plt_table(self, entry, clear):
        """
        Append an entry to the .got.plt table widget. Clear
        table is clear param is True.
        """

        if clear is True:
            self.clear_got_table()

        if entry != []:
            self.logger.info("Appending entry " + entry.__str__()
                             + " to got plt table.")
            self.got_plt_table_data.append(entry)
            self.got_plt_table.model().layoutChanged.emit()

        self.got_plt_table.resizeColumnsToContents()
        hh = self.got_plt_table.horizontalHeader()
        hh.setStretchLastSection(True)

    def update_sections_table(self, entry, clear):
        """
        Append an entry to the sections table widget. Clear
        table is clear param is True.
        """

        if clear is True:
            self.clear_sections_table()

        if entry != []:
            self.sections_table_data.append(entry)
            self.sections_table.model().layoutChanged.emit()

        self.sections_table.resizeColumnsToContents()
        hh = self.sections_table.horizontalHeader()
        hh.setStretchLastSection(True)


class GotPltTableModel(QtCore.QAbstractTableModel):
    """
    Module for the widget to dispay the .got.plt entries.
    """

    def __init__(self, datain, headerdata, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.arraydata = datain
        self.headerdata = headerdata

    def rowCount(self, parent):
        return len(self.arraydata)

    def columnCount(self, parent):
        if len(self.arraydata) > 0:
            return len(self.arraydata[0])
        return 0

    def data(self, index, role):
        if not index.isValid():
            return None
        elif role != QtCore.Qt.DisplayRole:
            return None
        return self.arraydata[index.row()][index.column()]

    def setData(self, index, value, role):
        pass

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and \
                role == QtCore.Qt.DisplayRole:
            return self.headerdata[col]
        return None


class ElfSectionsTableModel(QtCore.QAbstractTableModel):
    """
    Module for the widget to dispay the sections of the program and of the
    shared libraries.
    """

    def __init__(self, datain, headerdata, parent=None):

        QtCore.QAbstractTableModel.__init__(self, parent)
        self.arraydata = datain
        self.headerdata = headerdata

    def rowCount(self, parent):
        return len(self.arraydata)

    def columnCount(self, parent):
        if len(self.arraydata) > 0:
            return len(self.arraydata[0])
        return 0

    def data(self, index, role):
        if not index.isValid():
            return None
        elif role != QtCore.Qt.DisplayRole:
            if role == QtCore.Qt.BackgroundRole:
                status = index.sibling(index.row(), 3).data()
                if status != '':
                    return QtGui.QColor(QtCore.Qt.yellow)
                else:
                    return None
            else:
                return None

        return self.arraydata[index.row()][index.column()]

    def setData(self, index, value, role):
        pass

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and \
                role == QtCore.Qt.DisplayRole:
            return self.headerdata[col]
        return None
