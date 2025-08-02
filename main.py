from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QToolButton,
    QLineEdit,
)
from PySide6.QtGui import (
    QFont, QIcon, QTextCharFormat, QBrush, QTextCursor, QPixmap, QPainter, QDesktopServices
)
from PySide6.QtCore import QSize, Qt, QEvent, QPoint, QUrl
from PySide6.QtSvg import QSvgRenderer

class LinkableTextEdit(QTextEdit):
    def mousePressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            cursor = self.cursorForPosition(event.position().toPoint())  # local coords
            char_fmt = cursor.charFormat()
            if char_fmt.isAnchor():
                link_url = char_fmt.anchorHref()
                if link_url:
                    if not link_url.startswith(("http://", "https://")):
                        link_url = "https://" + link_url
                    QDesktopServices.openUrl(QUrl(link_url))
                    return  # Skip normal editing
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Change cursor to pointing hand when hovering link with Ctrl pressed."""
        cursor = self.cursorForPosition(event.position().toPoint())
        char_fmt = cursor.charFormat()
        if event.modifiers() & Qt.ControlModifier and char_fmt.isAnchor():
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.IBeamCursor)
        super().mouseMoveEvent(event)

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

        # — text edit —
        self.text_edit = LinkableTextEdit()
        self.text_edit.setHtml("<p>Edit <b>me</b>!</p>")
        self.setCentralWidget(self.text_edit)

        # — toolbar —
        self.toolbar = QToolBar("Formatting")
        self.toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self.toolbar)

        self._format_actions = []

        # 1) Decorator‐based format buttons (bold/italic/underline)
        for attr_name in dir(self):
            method = getattr(self, attr_name)
            if callable(method) and hasattr(method, "_action_icon"):
                btn = QToolButton()
                btn.setIcon(load_svg_icon(f"./assets/{method._action_icon}"))
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, m=method: m(checked))
                self.toolbar.addWidget(btn)
                self._format_actions.append((btn, method))

        # 2) Link button & URL popup
        self.link_button = QToolButton()
        self.link_button.setIcon(load_svg_icon("./assets/link.svg"))
        self.link_button.setCheckable(True)
        self.link_button.clicked.connect(self._apply_or_remove_link)
        self.link_button.installEventFilter(self)
        self.toolbar.addWidget(self.link_button)

        self.link_input = QLineEdit(self)
        self.link_input.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.link_input.setFocusPolicy(Qt.StrongFocus)  # Can take focus without blocking
        self.link_input.setPlaceholderText("Enter URL and press Enter")
        self.link_input.editingFinished.connect(self._on_link_entered)
        self.link_input.installEventFilter(self)
        self.link_input.setAttribute(Qt.WA_Hover)
        self._pending_link_url = ""
        self.url = ""

        self.text_edit.selectionChanged.connect(self.on_selection_changed)

        # 3) Only *now* hook up the cursor‐moved signal, and do one initial state sync
        self.text_edit.cursorPositionChanged.connect(self.update_format_states)
        self.update_format_states()

        self.non_link_underline = False
        self.non_link_fg = Qt.white

    def on_selection_changed(self):
        if self.link_button.isChecked():
            self.link_input.setText(self.text_edit_fmt().anchorHref())


    def eventFilter(self, obj, event):
        # Show URL box when hovering over the link button
        if obj is self.link_button:
            if event.type() == QEvent.Enter:
                # position the input right below the button
                btn_pos = self.link_button.mapToGlobal(QPoint(0, self.link_button.height()))
                self.link_input.move(btn_pos)
                self.link_input.show()
                self.link_input.setFocus()
                return True
            elif event.type() == QEvent.Leave:
                self._on_link_entered()
                return False
        if obj is self.link_button:
            if event.type() == QEvent.Enter:
                btn_pos = self.link_button.mapToGlobal(QPoint(0, self.link_button.height()))
                self.link_input.move(btn_pos)
                self.link_input.show()
                return True
        return super().eventFilter(obj, event)

    def _on_link_entered(self):
        self.url = self.link_input.text().strip()
        
        self._pending_link_url = self.url
        self.link_input.hide()

        # If link button is checked and no selection, typing will use this link
        if self.link_button.isChecked():
            self._apply_or_remove_link(True)

    def _apply_or_remove_link(self, checked):
        """
        Works like bold/italic:
        - If checked: link is active (selection or typing)
        - If unchecked: link is removed
        """
        cursor = self.text_edit.textCursor()
        
        if checked:
            if not self._pending_link_url:
                # Ask for URL if not set
                btn_pos = self.link_button.mapToGlobal(QPoint(0, self.link_button.height()))
                self.link_input.move(btn_pos)
                self.link_input.show()
                self.link_input.setFocus()
                return
            
            fmt = QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorHref(self._pending_link_url)
            self.non_link_underline = fmt.fontUnderline()
            fmt.setFontUnderline(True)
            self.non_link_fg = fmt.foreground()
            fmt.setForeground(QBrush(Qt.green))
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.text_edit.mergeCurrentCharFormat(fmt)
        else:
            if self.url == self.link_input.text().strip():
                fmt = QTextCharFormat()
                fmt.setAnchor(False)
                fmt.setAnchorHref("")
                fmt.setFontUnderline(self.non_link_underline)
                fmt.setForeground(self.non_link_fg)
                if cursor.hasSelection():
                    cursor.mergeCharFormat(fmt)
                else:
                    self.text_edit.mergeCurrentCharFormat(fmt)
            else:
                fmt = QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorHref(self.link_input.text().strip())
                self.url = self.link_input.text().strip()
                self._pending_link_url = self.url
                if cursor.hasSelection():
                    cursor.mergeCharFormat(fmt)
                else:
                    self.text_edit.mergeCurrentCharFormat(fmt)
            

        self.update_format_states()

    def _apply_link(self, url: str):
        """Sets the given URL on the selected text (or typing position)."""
        cursor = self.text_edit.textCursor()
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setFontUnderline(True)                         # typical link underline
        fmt.setForeground(QBrush(Qt.blue))                 # typical link color
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        else:
            self.text_edit.mergeCurrentCharFormat(fmt)
    def text_edit_fmt(self):
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            # check the format at the start of the selection
            start = min(cursor.anchor(), cursor.position())
            cursor.setPosition(start, QTextCursor.MoveAnchor)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
            fmt = cursor.charFormat()
        else:
            fmt = self.text_edit.currentCharFormat()

        return fmt

    def update_format_states(self):
        fmt = self.text_edit_fmt()

        for btn, method in self._format_actions + [(self.link_button, None)]:
            if btn is self.link_button:
                # link button checked state if this fmt is an anchor
                btn.setChecked(bool(fmt.isAnchor()))
            else:
                check = getattr(method, "_check_state_func", None)
                btn.setChecked(check(fmt) if check else False)

    # format_action decorators for bold/italic/underline
    @format_action("bold.svg", lambda fmt: fmt.fontWeight() > QFont.Normal)
    def toggle_bold(self, fmt, checked):
        fmt.setFontWeight(QFont.Bold if checked else QFont.Normal)

    @format_action("italics.svg", lambda fmt: fmt.fontItalic())
    def toggle_italic(self, fmt, checked):
        fmt.setFontItalic(checked)

    @format_action("underline.svg", lambda fmt: fmt.fontUnderline())
    def toggle_underline(self, fmt, checked):
        fmt.setFontUnderline(checked)


if __name__ == "__main__":
    app = QApplication([])
    window = App()
    window.show()
    app.exec()
