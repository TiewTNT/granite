from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QToolButton,
    QLineEdit, QFileSystemModel, QTreeView, QSplitter, QVBoxLayout, QFileIconProvider, QStyledItemDelegate,
    QLabel, QWidget, 
)

from PySide6.QtGui import (
    QFont, QIcon, QTextCharFormat, QBrush, QTextCursor, QPixmap, QPainter, QDesktopServices,
    QTextBlockFormat, QKeySequence, QShortcut, QPalette, QTextListFormat, QTextFormat, QAction 
)
from PySide6.QtCore import QSize, Qt, QEvent, QPoint, QUrl, QSignalBlocker, QDir, QObject, Signal, QTimer, QItemSelectionModel
from PySide6.QtSvg import QSvgRenderer

from pathlib import Path
import ast, json, os
from platformdirs import user_data_dir

app_name = "Granite"

data_path = Path(user_data_dir(app_name))
data_path.mkdir(parents=True, exist_ok=True)
print(data_path)

class TypographyScale:
    def __init__(self, base_size=12, ratio=1.25):
        self.base_size = base_size
        self.ratio = ratio

    def size_for(self, level):
        return round(self.base_size * (self.ratio ** (4-level)))
    
INDENT_MAP = {
    "1": (0, 0),     # H1 — no indent
    "2": (10, 10),   # H2 — slight indent
    "3": (20, 20),   # H3 — more indent
    "4": (30, 30),   # Body — maximum indent
}

class GraniteFileSystemModel(QFileSystemModel):
    # emits index to re-expand after rename, so you can restore expansion
    renameFinished = Signal("QModelIndex")

    def __init__(self, parent=None):
        super().__init__(parent)
        # Start watching directories under rootpath automatically:
        self.setReadOnly(True)  # ⚡ disable watchers initially

    def flags(self, index):
        f = super().flags(index)
        # Only column 0 can be edited, only for files (not directories)
        if index.isValid() and index.column() == 0 and not self.isDir(index):
            return f | Qt.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole and index.isValid() and index.column() == 0:
            old_path = self.filePath(index)
            new_name = value
            if not new_name.lower().endswith(".grnt"):
                new_name += ".grnt"
            new_path = os.path.join(os.path.dirname(old_path), new_name)

            if new_path.lower() == old_path.lower():
                return False  # no change

            if Path(new_path).exists():
                return False  # avoid overwriting

            # 1) collapse parent index in attached view to release any locks
            parent = index.parent()
            if hasattr(self, "treeView"):
                self.treeView.collapse(parent)

            # 2) enable rename (triggers internal QFileSystemModel.rename())
            self.setReadOnly(True)  # make sure watchers are off
            ok = super().setData(index, new_name, role)
            self.setReadOnly(False)  # turn watchers back on

            if ok:
                # save collapse state then re-expand after directory scanning finishes
                QTimer.singleShot(0, lambda idx=index: self.renameFinished.emit(idx))
            return ok
        return super().setData(index, value, role)
    

    
class GraniteFileIconProvider(QFileIconProvider):
    def icon(self, fileInfo):
        if fileInfo.isDir():
            return QIcon("./assets/folder.svg")
        elif fileInfo.suffix().lower() == "grnt":
            return QIcon("./assets/grnt_icon.svg")
        return super().icon(fileInfo) 
    
class GraniteDelegate(QStyledItemDelegate):
    def displayText(self, value, locale):
        if isinstance(value, str):
            return Path(value).stem
        return value

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
                App.update_margins(app, body_fmt)
            
                cursor.mergeBlockFormat(body_fmt)

                font = QFont()
                font.setPointSizeF(TypographyScale(App.settings_dict["scale_base"], App.settings_dict["scale_ratio"]).size_for(4))
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

def format_action(icon_name, check_state_func, order, block=False, give_cursor=False):
    """
    Decorator for creating formatting actions.
    If give_cursor=True, the QTextCursor will be passed to both func and check_state_func.
    Works correctly for both character and block formats (e.g. headings).
    """
    def decorator(func):
        def wrapper(instance, checked=None):
            cursor = instance.text_edit.textCursor()
            cursor.beginEditBlock()

            if block:
                block_fmt = cursor.blockFormat()
                if give_cursor:
                    func(instance, cursor, block_fmt, checked)
                else:
                    func(instance, block_fmt, checked)
                # Ensure block format changes (like headings) are applied to the block
                cursor.setBlockFormat(block_fmt)
            else:
                char_fmt = QTextCharFormat()
                if give_cursor:
                    func(instance, cursor, char_fmt, checked)
                else:
                    func(instance, char_fmt, checked)
                if cursor.hasSelection():
                    cursor.mergeCharFormat(char_fmt)
                else:
                    instance.text_edit.mergeCurrentCharFormat(char_fmt)

            cursor.endEditBlock()
            instance.text_edit.viewport().update()
            instance.update_format_states()

        if give_cursor:
            def wrapped_check(fmt, instance):
                return check_state_func(instance.text_edit.textCursor(), fmt)
            wrapper._check_state_func = wrapped_check
        else:
            wrapper._check_state_func = check_state_func

        wrapper._action_icon = icon_name
        wrapper._order = order
        wrapper._give_cursor = give_cursor
        return wrapper
    return decorator


def format_action(icon_name, check_state_func, order, block=False, give_cursor=False):
    def decorator(func):
        def wrapper(self, checked=None):
            cursor = self.text_edit.textCursor()

            # Tell Qt: "I'm about to do a batch of edits—hold off repainting."
            cursor.beginEditBlock()

            # 1) Prepare fresh formats
            block_fmt = QTextBlockFormat() if block else None
            char_fmt  = QTextCharFormat()

            # 2) Let the action set its bits
            if give_cursor: func(self, cursor, block_fmt or char_fmt, checked) 
            else: func(self, block_fmt or char_fmt, checked)

            if block:
                level = block_fmt.property(1001)

                # 3) Merge only this block's block‐format
                cursor.mergeBlockFormat(block_fmt)

                # 4) If it set a header property, size & merge that block's char‐format
                
                if level:
                    idx = int(level)               # "h2" → 2
                    font = QFont()
                    font.setPointSizeF(TypographyScale(self.settings_dict["scale_base"], self.settings_dict["scale_ratio"]).size_for(idx))
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
        if give_cursor:
            def wrapped_check(fmt, instance):
                return check_state_func(instance.text_edit.textCursor(), fmt)
            wrapper._check_state_func = wrapped_check
        else:
            wrapper._check_state_func = check_state_func
        return wrapper
    return decorator




class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Granite")
        self.setWindowIcon(QIcon('./assets/app_icon.svg'))
        layout = QVBoxLayout()
        

        # — text edit —
        self.text_edit = LinkableTextEdit()
        
        self.text_edit.document().setDocumentMargin(30)

        default_font = QFont()
        default_font.setPointSizeF(TypographyScale(self.settings_dict["scale_base"], self.settings_dict["scale_ratio"]).size_for(4)) 

        default_fmt = QTextCharFormat()
        default_fmt.setFont(default_font)
        self.text_edit.setCurrentCharFormat(default_fmt)
        self.text_edit.setFont(default_font)
        


        # — toolbar —
        self.toolbar = QToolBar("Formatting")
        self.toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(self.toolbar)

        # — files —

        # Create a QFileSystemModel
        self.model = GraniteFileSystemModel()

        self.model.setIconProvider(GraniteFileIconProvider())
        self.model.setRootPath(str(data_path))  # Set the root path (empty string for the entire file system)
        self.model.setNameFilters(["*.grnt"])
        self.model.setNameFilterDisables(False)  # Hide files not matching
        self.model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot | QDir.Files)

        # Create a QTreeView
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(str(data_path)))  # Set the root index to the file system root
        self.tree_view.setMinimumWidth(75)

        self.tree_view.setEditTriggers(QTreeView.EditKeyPressed | QTreeView.SelectedClicked)
        self.model.setReadOnly(False)

        for col in range(1, self.model.columnCount() - 1):
            self.tree_view.hideColumn(col)

        self.tree_view.setItemDelegateForColumn(0, GraniteDelegate(self.tree_view))




        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.text_edit)
        
        self.tree_view.selectionModel().selectionChanged.connect(self.on_file_selection_changed)
        layout.addWidget(self.splitter)

        # Make a files toolbar
        file_panel = QWidget()
        file_layout = QVBoxLayout(file_panel)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(0)

        # Create toolbar for tree view
        file_toolbar = QToolBar()
        file_toolbar.setIconSize(QSize(24, 24))

        self.file_toolbar_text_edit = QLineEdit()

        file_toolbar.addWidget(self.file_toolbar_text_edit)

        file_layout.addWidget(file_toolbar)
        file_layout.addWidget(self.tree_view)

        # Replace in splitter
        self.splitter.addWidget(file_panel)

        self.selected_dir = None
        def update_selected_dir():
            if self.current_file:
                if Path(self.current_file).is_dir():
                    self.selected_dir = str(Path(self.current_file))
                else:
                    self.selected_dir = str(Path(self.current_file).parent)
            else:
                self.selected_dir = data_path

            print(self.selected_dir)


        self.tree_view.selectionModel().selectionChanged.connect(update_selected_dir)


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
        self.non_link_fg = self.text_edit.palette().brush(QPalette.Text)

        self.link_input.hide()
        text_edit_block_fmt = QTextBlockFormat()
        text_edit_block_fmt.setProperty(1001, "4")
        
        cursor = self.text_edit.textCursor()
        self.update_margins(text_edit_block_fmt)
        self.auto_indent_bodies()
        cursor.mergeBlockFormat(text_edit_block_fmt)

        self.setCentralWidget(self.splitter)
        self.setLayout(layout)

        file_view_toggle_shortcut = QShortcut(QKeySequence("Ctrl+J"), self)
        file_view_toggle_shortcut.activated.connect(lambda: self.tree_view.setVisible(not self.tree_view.isVisible()))

        self.text_edit.document().contentsChange.connect(self.save)

        self.on_file_selection_changed()
        self.save()

        update_selected_dir()


        self._last_clicked_index = None

        self.tree_view.clicked.connect(self._toggle_tree_selection)

        new_btn = QAction(QIcon("./assets/add_file.svg"), "New File", self)
        new_btn.triggered.connect(self.create_new_file)
        file_toolbar.addAction(new_btn)

    def _toggle_tree_selection(self, index):
        if self._last_clicked_index == index:
            # Second click on same index → deselect
            self.tree_view.clearSelection()
            self.statusBar().showMessage("No file selected")
            self._last_clicked_index = None
        else:
            # First click → select
            self._last_clicked_index = index



    def create_new_file(self):
        p = str(Path(self.selected_dir) / self.file_toolbar_text_edit.text())
        p += ".grnt" if not p.endswith(".grnt") else ""
        with open(p, 'w'):
            if not self.current_file:
                Path(p).write_bytes(Path('./user/file.grnt').read_bytes())
            self.tree_view_select_path(p)

    def tree_view_select_path(self, file_path):
        file_path = str(file_path)

        # Get the index for the file
        index = self.model.index(file_path, 0)

        if index.isValid():
            self.tree_view.setCurrentIndex(index)  # moves current highlight
            self.tree_view.selectionModel().select(index, 
                QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)  # selects visually
            self.tree_view.scrollTo(index)  # scrolls to make it visible


    text_fg = Qt.white
    current_file = None

    settings_dict = {
        "accent_color": "#c7795f",
        "scale_ratio": 1.25,
        "scale_base": 12,
    }

    
    def on_file_selection_changed(self):
        def get(p):
            self.current_file = p
            raw = Path(self.current_file).read_text(encoding="utf-8")

            if ":::" in raw:
                settings_str, html = raw.split(":::", 1)
                try:
                    settings = json.loads(settings_str)
                except json.JSONDecodeError:
                    settings = {}
            else:
                settings, html = {}, raw

            with QSignalBlocker(self.text_edit.document()):
                self.text_edit.setHtml(html)

            self.settings_dict.update({k: settings.get(k, self.settings_dict.get(k))
                                    for k in ("scale_base", "scale_ratio", "accent_color")})

            doc = self.text_edit.document()
            for b in settings.get("block_states", []):
                block = doc.findBlock(b["pos"])

                if block.isValid():
                    block.setUserState(b["userState"])
                    cursor = QTextCursor(block)
                    fmt = block.blockFormat()
                    fmt.setProperty(1001, b.get('1001', 4))
                    cursor.setBlockFormat(fmt)
                    

            self.apply_typography_scale()
            self.auto_indent_bodies()

        if not self.tree_view.selectedIndexes():
            self.statusBar().showMessage("No file selected")
            path = "./user/file.grnt"
            get(path)
            self.current_file = None
            return
        
        path = self.tree_view.model().filePath(self.tree_view.selectedIndexes()[0])
        
        if Path(path).is_dir():
            self.current_file = path
            return
        
        self.statusBar().showMessage('Editing "'+Path(path).stem+'"')
        


        get(path)


    def save(self):
        def store(path):
            settings = {"scale_base": self.settings_dict["scale_base"],
            "scale_ratio": self.settings_dict["scale_ratio"],
            "accent_color": self.settings_dict["accent_color"]}

            blocks_data = []
            doc = self.text_edit.document()
            block = doc.begin()
            while block.isValid():                        # QTextBlock.isValid()
            
                state = block.userState()                 # per-block integer

                p1001 = block.blockFormat().property(1001)

                blocks_data.append({
                    "pos": block.position(),
                    "userState": state,
                    "1001": p1001
                })
                block = block.next()                      # QTextBlock.next()
            settings["block_states"] = blocks_data

            settings_str = json.dumps(settings)  # Use JSON reliably


            with QSignalBlocker(doc):  # prevents recursive documentsignal emission
                html = doc.toHtml()

            Path(path).write_text(settings_str + ":::" + html, encoding="utf-8")
        if self.current_file and not Path(self.current_file).is_dir():
            store(self.current_file)
        else:
            self.statusBar().showMessage("No file selected")
            store("./user/file.grnt")


    def auto_indent_bodies(self):
        doc = self.text_edit.document()
        block = doc.firstBlock()
        prev_header_level = None

        while block.isValid():
            fmt = block.blockFormat()
            level = fmt.property(1001)

            # Check if this block is a heading
            if level in ("1", "2", "3"):
                prev_header_level = int(level)
            
            # If it's a body block, decide indent
            elif level == "4":
                if prev_header_level is not None:
                    # Indent body to match its header's indent
                    left_indent, right_indent = INDENT_MAP.get(str(prev_header_level + 1), (0, 0))
                else:
                    # No header above → flush left
                    left_indent, right_indent = (0, 0)
                
                fmt.setLeftMargin(left_indent)
                fmt.setRightMargin(right_indent)
                cursor = QTextCursor(block)
                cursor.setBlockFormat(fmt)

            else:
                prev_header_level = None  # Reset when encountering unknown format
            
            block = block.next()

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
                self.link_input.raise_()
                self.link_input.activateWindow()

                self.link_input.setFocus()
                
                return True
            elif event.type() == QEvent.Leave:
                self._on_link_entered()
                return False

        return super().eventFilter(obj, event)

    def _on_link_entered(self):
        self.url = self.link_input.text().strip()
        
        self._pending_link_url = self.url
        self.link_input.hide()

        # If link button is checked and no selection, typing will use this link
        if self.link_button.isChecked():
            self._apply_or_remove_link(True)

    def _apply_or_remove_link(self, checked):
        cursor = self.text_edit.textCursor()

        fmt = QTextCharFormat()
        if checked:
            if not self._pending_link_url:
                btn_pos = self.link_button.mapToGlobal(QPoint(0, self.link_button.height()))
                self.link_input.move(btn_pos)
                self.link_input.show()
                self.link_input.setFocus()
                return
            
            fmt.setAnchor(True)
            fmt.setAnchorHref(self._pending_link_url)
            fmt.setFontUnderline(True)
            fmt.setForeground(QBrush(self.settings_dict["accent_color"]))
        else:
            fmt.setAnchor(False)
            fmt.setAnchorHref("")
            fmt.setFontUnderline(False)
            fmt.setForeground(self.text_edit.palette().brush(QPalette.Text))

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
                try:
                    btn.setChecked(check(fmt) if check else False)
                except TypeError:
                    btn.setChecked(check(fmt, self) if check else False)

        self.auto_indent_bodies()


    def apply_typography_scale(self):
        doc = self.text_edit.document()
        block = doc.firstBlock()
        while block.isValid():

            fmt = block.blockFormat()
            level = fmt.property(1001)
            if not level: level = 4
            if level:
                font = QFont()
                font.setPointSizeF(TypographyScale(
                    self.settings_dict["scale_base"],
                    self.settings_dict["scale_ratio"]
                ).size_for(int(level)))

                char_fmt = QTextCharFormat()
                char_fmt.setFont(font)

                cursor = QTextCursor(block)
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.mergeCharFormat(char_fmt) 
            block = block.next()


    def update_margins(self, fmt):
        left_indent, right_indent = INDENT_MAP.get(fmt.property(1001), (0, 0))

        assert type(fmt) == QTextBlockFormat
        fmt.setLeftMargin(left_indent)
        fmt.setRightMargin(right_indent)
        


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

    @format_action("highlight.svg", lambda fmt: fmt.background().color() == App.settings_dict["accent_color"] + "55", 4)
    def toggle_highlight(self, fmt, checked):
        fmt.setBackground(QBrush(self.settings_dict["accent_color"] + "55") if checked else QBrush("#00000000"))

    @format_action("color_text.svg", lambda fmt: fmt.foreground().color() == App.settings_dict["accent_color"], 5)
    def toggle_colored_text(self, fmt, checked):
        fmt.setForeground(QBrush(self.settings_dict["accent_color"]) if checked else self.text_edit.palette().brush(QPalette.Text))

    @format_action("h1.svg", lambda fmt: fmt.property(1001) == "1", 7, block=True)
    def apply_h1(self, fmt, checked):
        fmt.setProperty(1001, "1")
        self.update_margins(fmt)

    @format_action("h2.svg", lambda fmt: fmt.property(1001) == "2", 8, block=True)
    def apply_h2(self, fmt, checked):
        fmt.setProperty(1001, "2")
        self.update_margins(fmt)

    @format_action("h3.svg", lambda fmt: fmt.property(1001) == "3", 9, block=True)
    def apply_h3(self, fmt, checked):
        fmt.setProperty(1001, "3")
        self.update_margins(fmt)

    @format_action("body.svg", lambda fmt: fmt.property(1001) == "4", 10, block=True)
    def apply_body(self, fmt, checked):
        fmt.setProperty(1001, "4")
        self.update_margins(fmt)

    @format_action("align_left.svg", lambda fmt: False, 12, block=True)
    def align_left(self, fmt, checked):
        fmt.setAlignment(Qt.AlignLeft)
        self.update_margins(fmt)

    @format_action("align_center.svg", lambda fmt: False, 13, block=True)
    def align_center(self, fmt, checked):
        fmt.setAlignment(Qt.AlignCenter)

    @format_action("align_right.svg", lambda fmt: False, 14, block=True)
    def align_right(self, fmt, checked):
        fmt.setAlignment(Qt.AlignRight)



    @format_action(
        "bullet_list.svg",
        # check_state_func: is this block in a ListDisc?
        lambda cursor, fmt: (
            bool(cursor.block().textList()) and cursor.block().textList().format() == QTextListFormat.ListDisc
        ),
        order=16,
        block=True,
        give_cursor=True
    )
    def bullet_list(self, c, fmt, checked):
        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock()

        if checked:
            # wrap in a disc‐style list
            list_fmt = QTextListFormat()
            list_fmt.setStyle(QTextListFormat.ListDisc)
            cursor.createList(list_fmt)
        else:
            # remove from list
            fmt.setObjectIndex(-1)
            fmt.setMarker(QTextBlockFormat.MarkerType.NoMarker)
            cursor.mergeBlockFormat(fmt)

        cursor.endEditBlock()


    @format_action(
        "number_list.svg",
        # check_state_func: is this block in a ListDecimal?
        lambda cursor, fmt: (
            bool(cursor.block().textList()) and cursor.block().textList().format() == QTextListFormat.ListDecimal
        ),
        order=17,
        block=True,
        give_cursor=True
    )
    def number_list(self, c, fmt, checked):
        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock()

        if checked:
            # wrap in a disc‐style list
            list_fmt = QTextListFormat()
            list_fmt.setStyle(QTextListFormat.ListDecimal)

            cursor.createList(list_fmt)
        else:
            # remove from list
            fmt.setObjectIndex(-1)
            fmt.setMarker(QTextBlockFormat.MarkerType.NoMarker)
            cursor.mergeBlockFormat(fmt)

        cursor.endEditBlock()







if __name__ == "__main__":
    app = QApplication([])
    window = App()
    window.show()
    app.exec()
