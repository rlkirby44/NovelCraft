from PyQt6.QtWidgets import (
    QSplitter, QSplitterHandle, QTreeWidget, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor, QTextCharFormat, QAction
from highlighter import SpellCheckHighlighter
import config


class EqualizingSplitterHandle(QSplitterHandle):
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            splitter = self.splitter()
            splitter.setSizes([100] * splitter.count())
            return
        super().mouseDoubleClickEvent(event)


class EqualizingSplitter(QSplitter):
    def createHandle(self):
        return EqualizingSplitterHandle(self.orientation(), self)


class ChapterTreeWidget(QTreeWidget):
    emptySpaceDoubleClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.moving_item = None
        self.original_index = -1

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item is None:
                self.emptySpaceDoubleClicked.emit()
                return
        super().mouseDoubleClickEvent(event)

    def start_detached_move(self, item):
        self.moving_item = item
        self.original_index = self.indexOfTopLevelItem(item)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        if self.moving_item:
            target_item = self.itemAt(event.pos())
            if target_item and target_item != self.moving_item:
                target_index = self.indexOfTopLevelItem(target_item)
                current_index = self.indexOfTopLevelItem(self.moving_item)
                if target_index != current_index:
                    self.takeTopLevelItem(current_index)
                    self.insertTopLevelItem(target_index, self.moving_item)
                    self.setCurrentItem(self.moving_item)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self.moving_item:
            if event.button() == Qt.MouseButton.LeftButton:
                self.moving_item = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.setMouseTracking(False)

                parent_app = self.window()
                if hasattr(parent_app, 'mark_dirty'):
                    parent_app.mark_dirty(True)

                event.accept()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                self.cancel_move()
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self.moving_item and event.key() == Qt.Key.Key_Escape:
            self.cancel_move()
            event.accept()
            return
        super().keyPressEvent(event)

    def cancel_move(self):
        if self.moving_item:
            current_index = self.indexOfTopLevelItem(self.moving_item)
            self.takeTopLevelItem(current_index)
            self.insertTopLevelItem(self.original_index, self.moving_item)
            self.moving_item = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setMouseTracking(False)


class IndentedTextEditor(QTextEdit):
    focused = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.indent_pixels = config.EDITOR_INDENT_PIXELS
        self.current_item = None

        font = QFont(config.EDITOR_FONT_FAMILY, config.EDITOR_FONT_SIZE)
        self.setFont(font)
        self.document().setDefaultFont(font)

        self.setViewportMargins(config.EDITOR_SIDE_MARGIN, 0, config.EDITOR_SIDE_MARGIN, 0)

        self.highlighter = SpellCheckHighlighter(self)
        self.cursorPositionChanged.connect(self.highlighter.rehighlight)

    def set_font_size(self, size):
        font = self.font()
        font.setPointSize(size)
        self.setFont(font)
        self.document().setDefaultFont(font)

        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        cursor.mergeCharFormat(fmt)
        cursor.clearSelection()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.apply_paragraph_indent()
        self.focused.emit(self)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.NoModifier:
            cursor = self.textCursor()
            block = cursor.block()
            layout = block.layout()
            relative_pos = cursor.position() - block.position()
            line = layout.lineForTextPosition(relative_pos)

            if event.key() == Qt.Key.Key_Down:
                if block.blockNumber() == self.document().blockCount() - 1:
                    if line and line.lineNumber() == layout.lineCount() - 1:
                        if not cursor.atEnd():
                            cursor.movePosition(QTextCursor.MoveOperation.End)
                            self.setTextCursor(cursor)
                            return

            elif event.key() == Qt.Key.Key_Up:
                if block.blockNumber() == 0:
                    if line and line.lineNumber() == 0:
                        if cursor.position() > 0:
                            cursor.movePosition(QTextCursor.MoveOperation.Start)
                            self.setTextCursor(cursor)
                            return

        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.apply_paragraph_indent()

    def apply_paragraph_indent(self):
        cursor = self.textCursor()
        fmt = cursor.blockFormat()
        fmt.setAlignment(Qt.AlignmentFlag.AlignJustify)
        if fmt.textIndent() != self.indent_pixels:
            fmt.setTextIndent(self.indent_pixels)
        cursor.setBlockFormat(fmt)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        cursor = self.cursorForPosition(event.pos())
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText().strip("' ")

        dictionary = self.highlighter.dictionary
        if dictionary and word and word not in self.highlighter.ignored_words and not dictionary.check(word):
            suggestions = dictionary.suggest(word)[:5]
            first_action = menu.actions()[0] if menu.actions() else None

            add_word_action = QAction(f"Add '{word}' to Dictionary", self)
            add_word_action.triggered.connect(lambda _, w=word: self.highlighter.add_ignored_word(w))

            if first_action:
                menu.insertAction(first_action, add_word_action)
                menu.insertSeparator(first_action)
            else:
                menu.addAction(add_word_action)

            if suggestions:
                for suggestion in (suggestions):
                    action = QAction(suggestion, self)
                    font = action.font()
                    font.setBold(True)
                    action.setFont(font)

                    target_cursor = QTextCursor(cursor)
                    action.triggered.connect(lambda _, s=suggestion, c=target_cursor: self.replace_word(c, s))

                    menu.insertAction(first_action if first_action else add_word_action, action)

                menu.insertSeparator(first_action if first_action else add_word_action)

        menu.exec(event.globalPos())

    def replace_word(self, cursor, new_word):
        cursor.insertText(new_word)


class ManuscriptTextEditor(IndentedTextEditor):
    """Custom text editor subclass to strictly track real user typing and edits."""
    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.text() or event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            main_window = self.window()
            if main_window and not getattr(main_window, 'is_loading', False):
                if hasattr(main_window, 'mark_dirty'):
                    main_window.mark_dirty(True)
                if self.current_item:
                    self.current_item.setData(0, Qt.ItemDataRole.UserRole, self.toHtml())
