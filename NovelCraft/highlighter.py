import re
import enchant
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QListWidget,
    QHBoxLayout, QPushButton
)
from PyQt6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor
)


class SpellCheckHighlighter(QSyntaxHighlighter):
    """Highlights misspelled words using British English dictionary and custom ignored words list."""
    def __init__(self, editor):
        super().__init__(editor.document())
        self.editor = editor

        # Ignored words are managed project-by-project via app.py
        self.ignored_words = set()

        try:
            self.dictionary = enchant.Dict("en_GB")
        except enchant.errors.DictNotFoundError:
            self.dictionary = None

        self.error_format = QTextCharFormat()
        self.error_format.setUnderlineColor(QColor("#ff2a85"))
        self.error_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)

    def force_refresh(self):
        doc = self.editor.document()
        doc.markContentsDirty(0, doc.characterCount())
        self.rehighlight()
        self.editor.viewport().update()

    def _notify_dirty(self):
        main_window = self.editor.window()
        if hasattr(main_window, "mark_dirty"):
            main_window.mark_dirty(True)

    def add_ignored_word(self, word):
        if not word:
            return
        self.ignored_words.add(word)
        self.force_refresh()
        self._notify_dirty()

    def remove_ignored_word(self, word):
        if word in self.ignored_words:
            self.ignored_words.remove(word)
            self.force_refresh()
            self._notify_dirty()

    def highlightBlock(self, text):
        if not self.dictionary or not text:
            return

        cursor = self.editor.textCursor()
        cursor_block_num = cursor.blockNumber()
        cursor_pos_in_block = cursor.positionInBlock()
        is_active_block = (self.currentBlock().blockNumber() == cursor_block_num)

        for match in re.finditer(r"\b[A-Za-z]+(?:[''][A-Za-z]+)*\b", text):
            start, end = match.span()

            if is_active_block and (start <= cursor_pos_in_block <= end):
                continue

            raw_word = match.group(0)

            # Strip possessive endings for checking purposes:
            # e.g., "Theo's" -> check "Theo", "James'" -> check "James"
            check_word = raw_word
            if raw_word.lower().endswith("'s"):
                check_word = raw_word[:-2]
            elif raw_word.endswith("'") or raw_word.endswith("’"):
                check_word = raw_word[:-1]

            check_word = check_word.strip("'")

            if check_word and check_word not in self.ignored_words and not self.dictionary.check(check_word):
                self.setFormat(start, end - start, self.error_format)

class DictionaryManagerDialog(QDialog):
    """Dialog to search, view, and remove custom lore/ignored dictionary terms."""
    def __init__(self, highlighter, parent=None):
        super().__init__(parent)
        self.highlighter = highlighter
        self.setWindowTitle("Custom Dictionary Manager")
        self.resize(380, 480)

        layout = QVBoxLayout(self)

        search_label = QLabel("Search / Filter Dictionary Terms:")
        layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type term to filter...")
        self.search_input.textChanged.connect(self.populate_list)
        layout.addWidget(self.search_input)

        self.word_list = QListWidget()
        layout.addWidget(self.word_list)

        btn_layout = QHBoxLayout()

        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_selected_word)
        btn_layout.addWidget(self.remove_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        self.populate_list()

    def populate_list(self):
        self.word_list.clear()
        filter_text = self.search_input.text().strip().lower()
        sorted_words = sorted(self.highlighter.ignored_words)

        for word in sorted_words:
            if not filter_text or filter_text in word.lower():
                self.word_list.addItem(word)

    def remove_selected_word(self):
        current_item = self.word_list.currentItem()
        if current_item:
            word = current_item.text()
            self.highlighter.remove_ignored_word(word)
            self.populate_list()
