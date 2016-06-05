"""
This module contains the graphical user interface for the
dyninspector tool.
"""

import os
import sys
import logging
from PySide import QtCore, QtGui


class MainWindow(QtGui.QWidget):
    """
    Interface for viewing dynamic linking and lazy binding and dynamic loading
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
        self.c_display          = None
        self.code_tabs          = None
        self.plt_display        = None
        self.got_plt_table      = None
        self.sections_table     = None
        self.modules_table      = None
        self.console_output     = None
        self.openAction         = None
        self.func_selector      = None
        self.startAction        = None
        self.continueAction     = None
        self.selectAction       = None

        # Data
        self.got_plt_table_data     = []
        self.tablemodel             = None
        self.tableheader            = None

        self.sections_table_data     = []
        self.sections_tablemodel    = None
        self.sections_tableheader   = None

        self.modules_table_data     = []
        self.modules_tablemodel    = None
        self.modules_tableheader   = None

        # Layouts
        self.layout     = QtGui.QVBoxLayout()
        self.top_layout = QtGui.QHBoxLayout()
        self.bot_layout = QtGui.QHBoxLayout()

        # Toolbar
        self.create_toolbar()
        self.layout.addWidget(self.toolbar)

        # Menu
        self.menu = QtGui.QMenuBar(self)
        m = QtGui.QMenu('App Mode', self.menu)
        self.menu.addMenu(m)

        dynlink_action = QtGui.QAction('Dynamic Linking / Lazy Binding Inspector', m, checkable=False)
        dynlink_action.triggered.connect(self.show_dynlink_iface)
        m.addAction(dynlink_action)

        dynload_action = QtGui.QAction('Dynamic Loading Inspector', m, checkable=False)
        dynload_action.triggered.connect(self.show_dynload_iface)
        m.addAction(dynload_action)

        self.build_top_layout()
        self.build_bottom_layout()

        self.layout.addLayout(self.top_layout)
        self.layout.addLayout(self.bot_layout)

        self.setLayout(self.layout)
        self.show_dynlink_iface()

        self.connect_signals()

    def show_dynlink_iface(self):
        self.set_continue_btn(False)
        self.create_dynlink_iface()
        self.worker.set_app_mode_sig.emit(self.worker.AppMode.DYN_LINK)

    def create_dynlink_iface(self):
        self.modules_table.setVisible(False)

        self.selectAction.setVisible(True)
        self.sections_table.setVisible(True)
        self.got_plt_table.setVisible(True)

    def show_dynload_iface(self):
        self.set_continue_btn(False)
        self.create_dynload_iface()
        self.worker.set_app_mode_sig.emit(self.worker.AppMode.DYN_LOAD)

    def create_dynload_iface(self):
        self.got_plt_table.setVisible(False)
        self.sections_table.setVisible(False)
        self.selectAction.setVisible(False)

        self.modules_table.setVisible(True)


    def connect_signals(self):
        """
        Connect methods to receive data from the background worker.
        """

        self.worker.clear_gui_sig.connect(self.clear)
        self.worker.add_func_selector_sig.connect(self.add_func_selector)
        self.worker.write_asm_display_sig.connect(self.write_asm_display)
        self.worker.write_c_display_sig.connect(self.write_c_display)
        self.worker.write_console_output_sig.connect(self.write_console_output)
        self.worker.set_cont_btn_sig.connect(self.set_continue_btn)
        self.worker.update_got_plt_table.connect(self.update_got_plt_table)
        self.worker.update_sections_table.connect(self.update_sections_table)
        self.worker.update_modules_table.connect(self.update_modules_table)

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
        self.c_display.clear()
        #self.plt_display.clear()
        self.console_output.clear()

        self.func_selector.clear()
        self.clear_got_table()
        self.clear_sections_table()
        self.clear_modules_table()

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

    def clear_modules_table(self):
        """
        Clear data from the modules widget
        """

        del self.modules_table_data[:]
        self.modules_table.model().layoutChanged.emit()

    def create_toolbar(self):
        """
        Build the app toolbar
        """

        # Open File button
        self.toolbar = QtGui.QToolBar(self)
        path = os.path.join(os.path.dirname(sys.modules[__name__].__file__), 'res/open.png')
        self.openAction = QtGui.QAction(QtGui.QIcon(path), 'Open ELF executable', self)
        self.toolbar.addAction(self.openAction)
        self.openAction.triggered.connect(self.elf_button_clicked)

        self.toolbar.addSeparator()
        
        # Start
        path = os.path.join(os.path.dirname(sys.modules[__name__].__file__), 'res/start.png')
        self.startAction = QtGui.QAction(QtGui.QIcon(path), 'Start program', self)
        self.toolbar.addAction(self.startAction)
        self.startAction.triggered.connect(self.restart_button_clicked)
        self.startAction.setEnabled(False)

        self.toolbar.addSeparator()

        # Continue button
        path = os.path.join(os.path.dirname(sys.modules[__name__].__file__), 'res/continue.png')
        self.continueAction = QtGui.QAction(QtGui.QIcon(path), 'Continue', self)
        self.toolbar.addAction(self.continueAction)
        self.continueAction.triggered.connect(self.continue_button_clicked)
        self.continueAction.setEnabled(False)

        self.toolbar.addSeparator()

        # Drop down widget
        self.func_selector = QtGui.QComboBox(self.toolbar)
        self.selectAction = self.toolbar.addWidget(self.func_selector)
        self.func_selector.currentIndexChanged.connect(self.selection_change)
        self.func_selector.setMinimumContentsLength(20)
        self.func_selector.setToolTip("Select breakpoint function")


    def build_top_layout(self):
        """
        Build the upper part of the display.
        """

        # C display
        self.c_display = QtGui.QTextEdit(self)
        self.c_display.setReadOnly(True)
        self.c_display.setLineWrapMode(QtGui.QTextEdit.NoWrap)

        font = self.c_display.font()
        font.setFamily("Courier")
        font.setPointSize(10)

        # Asm display
        self.asm_display = QtGui.QTextEdit(self)
        self.asm_display.setReadOnly(True)
        self.asm_display.setLineWrapMode(QtGui.QTextEdit.NoWrap)

        font = self.asm_display.font()
        font.setFamily("Courier")
        font.setPointSize(10)

        # Code tabs widget
        self.code_tabs = QtGui.QTabWidget()
        self.code_tabs.addTab(self.asm_display, "Assembly Code")
        self.code_tabs.addTab(self.c_display, "Source Code")

        self.top_layout.addWidget(self.code_tabs)

        # .got.plt / .plt display
        self.got_plt_table = QtGui.QTableView()

        self.tableheader = ['Function name', 'Intermediate Stub Location Address', 'Function Address']
        self.tablemodel = GotPltTableModel(self.got_plt_table_data,
                                           self.tableheader, self)
        self.got_plt_table.setModel(self.tablemodel)

        self.got_plt_table.setShowGrid(True)
        self.got_plt_table.resizeColumnsToContents()
        self.got_plt_table.resizeRowsToContents()

        vh = self.got_plt_table.verticalHeader()
        vh.setVisible(False)

        hh = self.got_plt_table.horizontalHeader()
        hh.setStretchLastSection(True)

        self.got_plt_table.resizeColumnsToContents()

        self.top_layout.addWidget(self.got_plt_table)

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

        # module table
        self.modules_table = QtGui.QTableView()

        self.modules_tableheader = ['Type', 'First Address', 'Last Address', 'Size',
                                     'Name']
        self.modules_tablemodel = ElfModulesTableModel(
            self.modules_table_data,
            self.modules_tableheader,
            self)
        self.modules_table.setModel(self.modules_tablemodel)

        self.modules_table.setShowGrid(True)
        self.modules_table.resizeColumnsToContents()
        self.modules_table.resizeRowsToContents()

        vh = self.modules_table.verticalHeader()
        vh.setVisible(False)

        hh = self.modules_table.horizontalHeader()
        hh.setStretchLastSection(False)

        self.modules_table.resizeColumnsToContents()
        self.bot_layout.addWidget(self.modules_table)


    def elf_button_clicked(self):
        """
        OnClick method for the set_elf button.
        """

        self.elf = QtGui.QFileDialog.getOpenFileName()[0]

        if self.elf is not None and len(self.elf) is not 0:
            self.worker.set_elf_sig.emit(self.elf)
            self.startAction.setEnabled(True)

    def restart_button_clicked(self):
        """
        OnClick method for the start program button.
        """

        self.worker.run_target_sig.emit()
        self.continueAction.setEnabled(True)

    def continue_button_clicked(self):
        """
        OnClick method for the continue program button.
        """

        self.worker.continue_target_sig.emit()

    def set_continue_btn(self, en):
        """
        Enables or disables the continue button.
        """

        self.continueAction.setEnabled(en)

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
        self.highlight(self.asm_display, line)
        for _ in range(line):
            self.asm_display.moveCursor(QtGui.QTextCursor.Down)

    def write_c_display(self, text, line):
        """
        Writes text to the c display. The old text is
        replaced.
        """

        self.c_display.setText(text)
        self.highlight(self.c_display, line)
        for _ in range(line):
            self.c_display.moveCursor(QtGui.QTextCursor.Down)

    def write_console_output(self, text):
        """
        Appends text to the console output
        """

        self.logger.info("Console_output: " + text)

        co_text = self.console_output.toPlainText()
        self.console_output.setText(co_text + '\n' + text)
        self.console_output.moveCursor(QtGui.QTextCursor.End)

    def highlight(self, qtextwidget, line):
        """
        Color a specific line on the asm_display widget.
        The line represents the current instruction in this case.
        """

        cursor = qtextwidget.textCursor()
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
        qtextwidget.setExtraSelections([hi_selection])

    def update_got_plt_table(self, entry, clear):
        """
        Append an entry to the .got.plt table widget. Clear
        table is clear param is True.
        """

        if clear is True:
            self.clear_got_table()

        if entry != []:
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

    def update_modules_table(self, entry, clear):
        """
        Append an entry to the modules table widget. Clear
        table is clear param is True.
        """

        if clear is True:
            self.clear_modules_table()

        if entry != []:
            self.modules_table_data.append(entry)
            self.modules_table.model().layoutChanged.emit()

        self.modules_table.resizeColumnsToContents()
        hh = self.modules_table.horizontalHeader()
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

class ElfModulesTableModel(QtCore.QAbstractTableModel):
    """
    Python module for the table widget to dispay the modules loaded in the ELF.
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
