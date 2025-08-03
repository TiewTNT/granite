from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QToolButton,
    QLineEdit,
)
from PySide6.QtGui import (
    QFont, QIcon, QTextCharFormat, QBrush, QTextCursor, QPixmap, QPainter, QDesktopServices, QTextBlockFormat
)
from PySide6.QtCore import QSize, Qt, QEvent, QPoint, QUrl
from PySide6.QtSvg import QSvgRenderer

class TypographyScale:
    def __init__(self, base_size=12, ratio=1.25):
        self.base_size = base_size
        self.ratio = ratio

    def size_for(self, level):
        return round(self.base_size * (self.ratio ** (4-level)))

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

    def keyPressEvent(self, event):
        super().keyPressEvent(event)

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            prev_block_fmt = cursor.block().previous().blockFormat()
            if prev_block_fmt.property(1001) in ("1", "2", "3"):
                body_fmt = QTextBlockFormat()
                body_fmt.setProperty(1001, "4")
                cursor.mergeBlockFormat(body_fmt)

                font = QFont()
                font.setPointSizeF(App.scale.size_for(4))
                char_fmt = QTextCharFormat()
                char_fmt.setFont(font)
                cursor.setBlockCharFormat(char_fmt)


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


def format_action(icon_name, check_state_func, order, block=False):
    def decorator(func):
        def wrapper(self, checked=None):
            cursor = self.text_edit.textCursor()

            # Tell Qt: "I'm about to do a batch of edits—hold off repainting."
            cursor.beginEditBlock()

            # 1) Prepare fresh formats
            block_fmt = QTextBlockFormat() if block else None
            char_fmt  = QTextCharFormat()

            # 2) Let the action set its bits
            func(self, block_fmt or char_fmt, checked)

            if block:
                # 3) Merge only this block's block‐format
                cursor.mergeBlockFormat(block_fmt)

                # 4) If it set a header property, size & merge that block's char‐format
                level = block_fmt.property(1001)
                if level:
                    idx = int(level)               # "h2" → 2
                    font = QFont()
                    font.setPointSizeF(self.scale.size_for(idx))
                    char_fmt.setFont(font)

                    cursor.setBlockCharFormat(char_fmt)
                    # Make new typing inherit the size
                    self.text_edit.mergeCurrentCharFormat(char_fmt)

            else:
                # 5) Normal inline formatting
                if cursor.hasSelection():
                    cursor.mergeCharFormat(char_fmt)
                else:
                    self.text_edit.mergeCurrentCharFormat(char_fmt)

            # Done with our batch—now Qt can repaint
            cursor.endEditBlock()

            # Force the viewport to redraw immediately
            self.text_edit.viewport().update()

            # 6) Sync toolbar states
            self.update_format_states()
        wrapper._action_icon      = icon_name
        wrapper._order            = order
        wrapper._check_state_func = check_state_func
        return wrapper
    return decorator


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Text Editor")
        self.setWindowIcon(QIcon('./assets/app_icon.svg'))

        # — text edit —
        self.text_edit = LinkableTextEdit()
        self.setCentralWidget(self.text_edit)
        self.text_edit.document().setDocumentMargin(30)

        default_font = QFont()
        default_font.setPointSizeF(self.scale.size_for(4)) 
        default_fmt = QTextCharFormat()
        default_fmt.setFont(default_font)
        self.text_edit.setCurrentCharFormat(default_fmt)
        self.text_edit.setFont(default_font)

        self.text_edit.setHtml("<p>Hello, world!</p>")

        # — toolbar —
        self.toolbar = QToolBar("Formatting")
        self.toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self.toolbar)

        self._format_actions = []

        # 1) Decorator‐based format buttons (bold/italic/underline)
        format_funcs = [getattr(self, attr_name) for attr_name in dir(self) if callable(getattr(self, attr_name)) and hasattr(getattr(self, attr_name), "_action_icon")]
        ordered_format_funcs = list("A"*(max([m._order for m in format_funcs]) + 1))
        for i in format_funcs:
            ordered_format_funcs[i._order] = i
        for method in ordered_format_funcs:
            if callable(method) and hasattr(method, "_action_icon"):
                btn = QToolButton()
                btn.setIcon(load_svg_icon(f"./assets/{method._action_icon}"))
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, m=method: m(checked))
                self.toolbar.addWidget(btn)
                self._format_actions.append((btn, method))
            else:
                self.toolbar.addSeparator()

        # 2) Link button & URL popup
        self.toolbar.addSeparator()
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
        self.non_link_fg = self.text_fg

        self.link_input.hide()
        


    accent_color = "#c7795f"
    text_fg = Qt.white
    scale = TypographyScale(12, 1.25)

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
            fmt.setForeground(QBrush(App.accent_color))
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


    def apply_typography_scale(self):
        doc = self.text_edit.document()
        block = doc.firstBlock()
        while block.isValid():
            fmt = block.blockFormat()
            level = fmt.property(1001)
            if level:
                font = QFont()
                font.setPointSizeF(self.scale.size_for(int(level)))  # 'h2' → 2
                # Apply font to block char format
                char_fmt = block.charFormat()
                char_fmt.setFont(font)
                cursor = QTextCursor(block)
                cursor.setBlockCharFormat(char_fmt)
            block = block.next()

    

    # format_action decorators for bold/italic/underline
    @format_action("bold.svg", lambda fmt: fmt.fontWeight() > QFont.Normal, 0)
    def toggle_bold(self, fmt, checked):
        fmt.setFontWeight(QFont.Bold if checked else QFont.Normal)

    @format_action("italics.svg", lambda fmt: fmt.fontItalic(), 1)
    def toggle_italic(self, fmt, checked):
        fmt.setFontItalic(checked)

    @format_action("underline.svg", lambda fmt: fmt.fontUnderline(), 2)
    def toggle_underline(self, fmt, checked):
        fmt.setFontUnderline(checked)

    @format_action("strikethrough.svg", lambda fmt: fmt.fontStrikeOut(), 3)
    def toggle_strikethrough(self, fmt, checked):
        fmt.setFontStrikeOut(checked)

    @format_action("highlight.svg", lambda fmt: fmt.background().color() == App.accent_color + "55", 4)
    def toggle_highlight(self, fmt, checked):
        fmt.setBackground(QBrush(self.accent_color + "55") if checked else QBrush("#00000000"))

    @format_action("color_text.svg", lambda fmt: fmt.foreground().color() == App.accent_color, 5)
    def toggle_colored_text(self, fmt, checked):
        fmt.setForeground(QBrush(self.accent_color) if checked else QBrush(self.text_fg))

    @format_action("h1.svg", lambda fmt: fmt.property(1001) == "1", 7, block=True)
    def apply_h1(self, fmt, checked):
        fmt.setProperty(1001, "1")

    @format_action("h2.svg", lambda fmt: fmt.property(1001) == "2", 8, block=True)
    def apply_h2(self, fmt, checked):
        fmt.setProperty(1001, "2")

    @format_action("h3.svg", lambda fmt: fmt.property(1001) == "3", 9, block=True)
    def apply_h3(self, fmt, checked):
        fmt.setProperty(1001, "3")

    @format_action("body.svg", lambda fmt: fmt.property(1001) == "4", 10, block=True)
    def apply_body(self, fmt, checked):
        fmt.setProperty(1001, "4")
    
    @format_action("align_center.svg", lambda fmt: False, 12, block=True)
    def align_center(self, fmt, checked):
        fmt.setAlignment(Qt.AlignCenter)




if __name__ == "__main__":
    app = QApplication([])
    window = App()
    window.show()
    app.exec()
