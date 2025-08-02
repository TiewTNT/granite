from PySide6.QtWidgets import QApplication, QMainWindow, QTextEdit, QToolBar, QToolButton
from PySide6.QtGui import QFont, QIcon, QTextCharFormat
from PySide6.QtCore import QSize
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPixmap, QPainter, QIcon, QTextCursor
from PySide6.QtCore import Qt

def load_svg_icon(path, size=24):
    renderer = QSvgRenderer(path)
    icon = QIcon()

    # Account for devicePixelRatio
    dpr = QApplication.primaryScreen().devicePixelRatio()
    px_size = int(size * dpr)

    pixmap = QPixmap(px_size, px_size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    pixmap.setDevicePixelRatio(dpr)
    icon.addPixmap(pixmap)
    return icon

def format_action(icon_name, check_state_func):
    def decorator(func):
        def wrapper(self, checked=None):
            cursor = self.text_edit.textCursor()
            assert type(cursor) == QTextCursor

            new_fmt = QTextCharFormat()
            func(self, new_fmt, checked)
            
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
                btn.setIcon(load_svg_icon(f"./assets/{method._action_icon}"))

                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, m=method: m(checked))
                self.toolbar.addWidget(btn)
                self._format_actions.append((btn, method))

                self.text_edit.cursorPositionChanged.connect(self.update_format_states)
                self.update_format_states()

    def update_format_states(self):
        cursor = self.text_edit.textCursor()

        if cursor.hasSelection():
            # Move to start of selection (always inside selection, regardless of drag direction)
            start = min(cursor.anchor(), cursor.position())
            cursor.setPosition(start, QTextCursor.MoveMode.MoveAnchor)

            # Move one character into the selection
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)

            fmt = cursor.charFormat()
            print("Selection format:", fmt.fontWeight(), fmt.fontItalic())
        else:
            fmt = self.text_edit.currentCharFormat()
            print("Cursor format:", fmt.fontWeight(), fmt.fontItalic())

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
