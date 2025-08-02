from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QToolBar, QToolButton
from PySide6.QtGui import QFont, QIcon, QTextCharFormat
from PySide6.QtCore import QSize
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPixmap, QPainter, QIcon
from PySide6.QtCore import Qt

def theme_icon(path, widget, size=24):
    renderer = QSvgRenderer(path)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setPen(widget.palette().color(widget.foregroundRole()))
    painter.setBrush(widget.palette().color(widget.foregroundRole()))
    print(widget.foregroundRole())
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)

def format_action(icon_name, check_state_func):
    def decorator(func):
        def wrapper(self, checked=None):  # Accept checked state from button
            cursor = self.text_edit.textCursor()
            new_fmt = QTextCharFormat()
            func(self, new_fmt, checked)  # Pass checked state to toggle logic
            if cursor.hasSelection():
                cursor.mergeCharFormat(new_fmt)
            else:
                self.text_edit.mergeCurrentCharFormat(new_fmt)
            self.update_format_states()
        wrapper._action_icon = icon_name
        wrapper._check_state_func = check_state_func
        return wrapper
    return decorator

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tiny Rich Text Editor")

        self.text_edit = QTextEdit()
        self.text_edit.setHtml("<p>Edit <b>me</b>!</p>")
        self.setCentralWidget(self.text_edit)

        self.toolbar = QToolBar("Formatting")
        self.toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self.toolbar)

        self._format_actions = []

        for attr_name in dir(self):
            method = getattr(self, attr_name)
            if callable(method) and hasattr(method, "_action_icon"):
                btn = QToolButton()
                btn.setIcon(theme_icon(f"./assets/{method._action_icon}", btn))
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, m=method: m(checked))  # Pass checked state
                self.toolbar.addWidget(btn)
                self._format_actions.append((btn, method))

        self.text_edit.cursorPositionChanged.connect(self.update_format_states)
        self.update_format_states()

    def update_format_states(self):
        fmt = self.text_edit.currentCharFormat()
        for btn, method in self._format_actions:
            check_func = getattr(method, "_check_state_func", None)
            if check_func:
                btn.setChecked(check_func(fmt))

    @format_action("bold.svg", lambda fmt: fmt.fontWeight() > QFont.Normal)
    def toggle_bold(self, fmt, checked):
        fmt.setFontWeight(QFont.Bold if checked else QFont.Normal)

    @format_action("italics.svg", lambda fmt: fmt.fontItalic())
    def toggle_italic(self, fmt, checked):
        fmt.setFontItalic(checked)

if __name__ == "__main__":
    app = QApplication([])
    window = App()
    window.show()
    app.exec()
