import os
import json
from PyQt6.QtWidgets import (
    QMainWindow, QToolBar, QWidget, QSizePolicy, QLabel, QComboBox,
    QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QFileDialog,
    QTextEdit, QApplication, QTreeWidgetItem, QMenu, QAbstractItemView
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QFont, QKeySequence, QAction, QTextCursor, QTextCharFormat, QColor, QIcon

from widgets import EqualizingSplitter, ChapterTreeWidget, ManuscriptTextEditor
from highlighter import DictionaryManagerDialog
import config

class NovelWriterApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("CustomWriter", "NovelWriterApp")
        self.current_file_path = None
        self.is_dirty = False
        self.is_loading = False
        self.dual_view_active = False

        self.themes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")

        self.init_ui()
        self.load_themes_into_combo()

        last_file = self.settings.value("last_project", "")
        if last_file and os.path.exists(last_file):
            if not self.load_project_file(last_file):
                self.create_default_project()
        else:
            self.create_default_project()

    @property
    def inactive_editor(self):
        return self.editor_2 if self.active_editor == self.editor_1 else self.editor_1

    def init_ui(self):
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)

        new_act = toolbar.addAction("New Project")
        new_act.setShortcut(QKeySequence.StandardKey.New)
        new_act.triggered.connect(self.new_project)

        open_act = toolbar.addAction("Open Project")
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self.open_project)

        save_act = toolbar.addAction("Save Project")
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_act.triggered.connect(self.save_project)

        toolbar.addSeparator()

        dict_act = toolbar.addAction("Dictionary Manager")
        dict_act.triggered.connect(self.open_dictionary_manager)

        toolbar.addSeparator()

        self.chapters_act = QAction("Chapters", self)
        self.chapters_act.setCheckable(True)
        self.chapters_act.setChecked(True)
        self.chapters_act.toggled.connect(self.toggle_chapters_panel)
        toolbar.addAction(self.chapters_act)

        self.dual_view_act = QAction("Dual View", self)
        self.dual_view_act.setCheckable(True)
        self.dual_view_act.toggled.connect(self.toggle_dual_view)
        toolbar.addAction(self.dual_view_act)
        dual_view_btn = toolbar.widgetForAction(self.dual_view_act)
        if dual_view_btn:
            dual_view_btn.setMinimumWidth(config.DUAL_VIEW_BUTTON_MIN_WIDTH)

        self.notes_act = QAction("Notes", self)
        self.notes_act.setCheckable(True)
        self.notes_act.toggled.connect(self.toggle_notes_panel)
        toolbar.addAction(self.notes_act)

        toolbar.addSeparator()

        self.italic_act = QAction("Italic", self)
        self.italic_act.setCheckable(True)
        self.italic_act.setShortcut(QKeySequence.StandardKey.Italic)
        self.italic_act.triggered.connect(self.toggle_italic)
        toolbar.addAction(self.italic_act)

        italic_btn = toolbar.widgetForAction(self.italic_act)
        if italic_btn:
            italic_btn.setObjectName("italicButton")

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        theme_label = QLabel(" Theme: ")
        toolbar.addWidget(theme_label)
        self.theme_combo = QComboBox()
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        toolbar.addWidget(self.theme_combo)

        self.main_splitter = EqualizingSplitter(Qt.Orientation.Horizontal)

        self.tree_container = QWidget()
        tree_layout = QVBoxLayout(self.tree_container)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(2)

        self.tree = ChapterTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setFont(QFont(config.FONT_FAMILY_SANS, config.TREE_FONT_SIZE))
        self.tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )

        self.tree.itemSelectionChanged.connect(self.on_chapter_selected)
        self.tree.emptySpaceDoubleClicked.connect(self.add_chapter)
        self.tree.itemChanged.connect(self.on_item_changed)

        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_chapter_context_menu)

        tree_layout.addWidget(self.tree)

        chap_btn_layout = QHBoxLayout()
        chap_btn_layout.setContentsMargins(4, 4, 4, 4)

        add_chap_btn = QPushButton("Add Chapter")
        add_chap_btn.setObjectName("chapterButton")
        add_chap_btn.clicked.connect(self.add_chapter)

        del_chap_btn = QPushButton("Delete Chapter")
        del_chap_btn.setObjectName("chapterButton")
        del_chap_btn.clicked.connect(self.delete_chapter)

        chap_btn_layout.addWidget(add_chap_btn)
        chap_btn_layout.addWidget(del_chap_btn)

        tree_layout.addLayout(chap_btn_layout)

        self.main_splitter.addWidget(self.tree_container)

        self.editor_splitter = EqualizingSplitter(Qt.Orientation.Horizontal)

        self.editor_1 = ManuscriptTextEditor()
        self.editor_2 = ManuscriptTextEditor()

        shared_dictionary = set()
        self.editor_1.highlighter.ignored_words = shared_dictionary
        self.editor_2.highlighter.ignored_words = shared_dictionary

        self.editor_1.focused.connect(self.on_editor_focused)
        self.editor_2.focused.connect(self.on_editor_focused)

        self.editor_1.textChanged.connect(self.on_text_changed)
        self.editor_2.textChanged.connect(self.on_text_changed)

        self.editor_1.cursorPositionChanged.connect(self.update_format_actions)
        self.editor_2.cursorPositionChanged.connect(self.update_format_actions)

        self.editor_splitter.addWidget(self.editor_1)
        self.editor_splitter.addWidget(self.editor_2)
        self.editor_2.hide()

        self.active_editor = self.editor_1

        self.main_splitter.addWidget(self.editor_splitter)

        self.notes_panel = QTextEdit()
        self.notes_panel.setPlaceholderText("Write story notes here...")
        self.notes_panel.setFont(QFont(config.FONT_FAMILY_SANS, config.NOTES_FONT_SIZE))
        saved_notes = self.settings.value("app_notes", "")
        self.notes_panel.setPlainText(saved_notes)
        self.notes_panel.hide()

        self.main_splitter.addWidget(self.notes_panel)

        self.main_splitter.setSizes([200, 800, 250])
        self.setCentralWidget(self.main_splitter)
        self.resize(1150, 650)

        quit_act = QAction("Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)  # Maps to Ctrl+Q
        quit_act.triggered.connect(self.close)
        self.addAction(quit_act)

    def toggle_chapters_panel(self, enabled):
        self.tree_container.setVisible(enabled)

    def toggle_italic(self):
        if not self.active_editor:
            return

        old_html = self.active_editor.toHtml()

        fmt = QTextCharFormat()
        fmt.setFontItalic(self.italic_act.isChecked())
        self.active_editor.mergeCurrentCharFormat(fmt)

        new_html = self.active_editor.toHtml()

        if not self.is_loading and old_html != new_html:
            self.mark_dirty(True)
            if self.active_editor.current_item:
                self.active_editor.current_item.setData(0, Qt.ItemDataRole.UserRole, new_html)

    def update_format_actions(self):
        if self.active_editor:
            fmt = self.active_editor.currentCharFormat()
            self.italic_act.blockSignals(True)
            self.italic_act.setChecked(fmt.fontItalic())
            self.italic_act.blockSignals(False)

    def update_dual_view_action_text(self):
        if not self.dual_view_active:
            self.dual_view_act.setText("Dual View")
        else:
            if self.active_editor == self.editor_1:
                self.dual_view_act.setText("Close Right")
            else:
                self.dual_view_act.setText("Close Left")

    def toggle_dual_view(self, enabled):
        self.is_loading = True
        self.dual_view_active = enabled
        try:
            if enabled:
                self.editor_2.show()
                if not self.editor_2.current_item and self.tree.topLevelItemCount() > 0:
                    current_idx = self.tree.indexOfTopLevelItem(self.active_editor.current_item) if self.active_editor.current_item else 0
                    next_idx = min(current_idx + 1, self.tree.topLevelItemCount() - 1)
                    item = self.tree.topLevelItem(next_idx)
                    if item:
                        self.load_item_into_editor(self.editor_2, item)
                self.editor_splitter.setSizes([100, 100])
            else:
                self.save_current_text()

                if self.inactive_editor == self.editor_1 and self.editor_2.current_item:
                    item_to_keep = self.editor_2.current_item
                    self.load_item_into_editor(self.editor_1, item_to_keep)

                self.editor_2.hide()
                self.active_editor = self.editor_1
                self.editor_1.setFocus()

                if self.editor_1.current_item:
                    self.tree.blockSignals(True)
                    self.tree.setCurrentItem(self.editor_1.current_item)
                    self.tree.blockSignals(False)

            self.update_dual_view_action_text()
            self.update_tree_highlights()
        finally:
            self.is_loading = False

    def toggle_notes_panel(self, enabled):
        if enabled:
            self.notes_panel.show()
            sizes = self.main_splitter.sizes()
            total = sum(sizes)
            if len(sizes) == 3:
                self.main_splitter.setSizes([int(total * 0.18), int(total * 0.62), int(total * 0.20)])
        else:
            self.notes_panel.hide()

    def on_editor_focused(self, editor):
        if self.active_editor != editor:
            self.active_editor = editor

            if editor.current_item:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(editor.current_item)
                self.tree.blockSignals(False)

            self.update_tree_highlights()
            self.update_format_actions()
            self.update_dual_view_action_text()

    def load_item_into_editor(self, editor, item):
        editor.current_item = item
        content = item.data(0, Qt.ItemDataRole.UserRole) or ""

        self.is_loading = True
        editor.blockSignals(True)
        editor.setHtml(content)

        cursor = editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)

        fmt = cursor.blockFormat()
        fmt.setAlignment(Qt.AlignmentFlag.AlignJustify)
        fmt.setTextIndent(editor.indent_pixels)
        cursor.mergeBlockFormat(fmt)

        cursor.clearSelection()
        editor.setTextCursor(cursor)

        editor.blockSignals(False)
        self.is_loading = False

    def update_tree_highlights(self):
        self.tree.blockSignals(True)
        try:
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                item.setBackground(0, QColor(0, 0, 0, 0))

            if self.dual_view_active and self.inactive_editor.current_item:
                if self.inactive_editor.current_item != self.active_editor.current_item:
                    self.inactive_editor.current_item.setBackground(0, QColor(128, 128, 128, 60))
        finally:
            self.tree.blockSignals(False)

    def load_themes_into_combo(self):
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()

        if os.path.exists(self.themes_dir):
            files = sorted([f for f in os.listdir(self.themes_dir) if f.endswith(".qss")])
        else:
            files = []

        for f in files:
            theme_name = os.path.splitext(f)[0]
            self.theme_combo.addItem(theme_name, userData=f)

        saved_theme = self.settings.value("last_selected_theme", "standardRed")
        if saved_theme:
            index = self.theme_combo.findText(saved_theme)
            if index >= 0:
                self.theme_combo.setCurrentIndex(index)

        self.theme_combo.blockSignals(False)
        if self.theme_combo.count() > 0:
            self.apply_theme(self.theme_combo.currentText())

    def apply_theme(self, theme_name):
        if not theme_name:
            return

        filename = f"{theme_name}.qss"
        theme_path = os.path.join(self.themes_dir, filename)

        if os.path.exists(theme_path):
            try:
                with open(theme_path, "r", encoding="utf-8") as f:
                    color_qss = f.read()

                layout_qss = f"""
                QWidget {{
                    font-family: {config.UI_FONT_FAMILY};
                }}
                QToolBar {{
                    spacing: {config.TOOLBAR_SPACING}px;
                    padding: {config.TOOLBAR_PADDING}px;
                }}
                QToolBar QToolButton {{
                    padding: {config.TOOL_BUTTON_PADDING};
                    margin: {config.TOOL_BUTTON_MARGIN};
                    font-size: {config.BUTTON_FONT_SIZE}px;
                }}
                QTreeWidget {{
                    font-size: {config.TREE_FONT_SIZE}px;
                }}
                QHeaderView::section {{
                    padding: {config.HEADER_SECTION_PADDING}px;
                    font-size: {config.HEADER_FONT_SIZE}px;
                    text-transform: {config.HEADER_TEXT_TRANSFORM};
                }}
                QListWidget::item {{
                    padding: {config.LIST_ITEM_PADDING};
                }}
                QPushButton {{
                    padding: {config.PUSH_BUTTON_PADDING};
                    margin: {config.PUSH_BUTTON_MARGIN};
                    min-width: {config.PUSH_BUTTON_MIN_WIDTH}px;
                    font-size: {config.BUTTON_FONT_SIZE}px;
                }}
                QMenu::item {{
                    padding: {config.MENU_ITEM_PADDING};
                }}
                QComboBox {{
                    padding: 4px 8px;
                }}
                QComboBox QAbstractItemView::item {{
                    padding: 0px 8px;
                    border-radius: 2px;
                }}
                QToolBar::separator {{
                    background: #383838;
                    width: 1px;
                    margin: 0px;
                }}
                QToolBar::handle:horizontal {{
                    width: 6px;
                    margin-right: 15px;
                }}
                dualViewButton {{
                    min-width: {config.DUAL_VIEW_BUTTON_MIN_WIDTH}px;
                }}
                QPushButton#chapterButton {{
                    min-width: {config.CHAPTER_BUTTON_MIN_WIDTH}px;
                }}
                """

                full_qss = color_qss + "\n\n/* Layout Metrics from config.py */\n" + layout_qss

                self.settings.setValue("last_selected_theme", theme_name)
                QApplication.instance().setStyleSheet(full_qss)
            except Exception as e:
                QMessageBox.warning(self, "Theme Error", f"Could not load theme:\n{str(e)}")

    def open_dictionary_manager(self):
        dialog = DictionaryManagerDialog(self.active_editor.highlighter, self)
        dialog.exec()
        self.editor_1.highlighter.force_refresh()
        self.editor_2.highlighter.force_refresh()
        if getattr(dialog, 'is_modified', False):
            self.mark_dirty(True)

    def new_project(self):
        if self.is_dirty:
            reply = QMessageBox.question(
                self, 'Unsaved Changes',
                'You have unsaved changes. Do you want to save before starting a new project?',
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self.save_project():
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        self.create_default_project()

    def create_default_project(self):
        self.is_loading = True
        self.tree.clear()
        self.current_file_path = None
        self.editor_1.current_item = None
        self.editor_2.current_item = None

        self.editor_1.highlighter.ignored_words.clear()
        self.editor_1.highlighter.force_refresh()
        self.editor_2.highlighter.force_refresh()

        self.add_chapter("Chapter 1")
        self.is_loading = False
        self.mark_dirty(False)
        self.update_title()

    def mark_dirty(self, dirty=True):
        if self.is_dirty != dirty:
            self.is_dirty = dirty
            self.update_title()

    def update_title(self):
        if self.current_file_path:
            filename = os.path.basename(self.current_file_path)
            name, _ = os.path.splitext(filename)
        else:
            name = "Untitled Project"

        dirty_marker = " *" if self.is_dirty else ""
        self.setWindowTitle(f"{name}{dirty_marker} — NovelCraft")

    def on_text_changed(self):
        if self.is_loading:
            return
        editor = self.sender()
        if not editor or not getattr(editor, 'current_item', None):
            return
        editor.current_item.setData(0, Qt.ItemDataRole.UserRole, editor.toHtml())

    def on_item_changed(self, item, column):
        if not self.is_loading:
            self.mark_dirty(True)

    def add_chapter(self, title=None):
        if not title or isinstance(title, bool):
            count = self.tree.topLevelItemCount() + 1
            title = f"Chapter {count}"

        item = QTreeWidgetItem(self.tree, [title])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0, Qt.ItemDataRole.UserRole, "")
        self.tree.setCurrentItem(item)

        if not self.is_loading:
            self.mark_dirty(True)

    def delete_chapter(self):
        item = self.tree.currentItem()
        if not item:
            return

        chapter_title = item.text(0)
        reply = QMessageBox.question(
            self,
            'Confirm Delete',
            f"Are you sure you want to delete '{chapter_title}'?\n\nThere ain't no going back from this...",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            index = self.tree.indexOfTopLevelItem(item)

            if self.editor_1.current_item == item:
                self.editor_1.current_item = None
            if self.editor_2.current_item == item:
                self.editor_2.current_item = None

            self.tree.takeTopLevelItem(index)

            if self.tree.topLevelItemCount() > 0:
                new_index = max(0, min(index, self.tree.topLevelItemCount() - 1))
                next_item = self.tree.topLevelItem(new_index)
                self.tree.setCurrentItem(next_item)
            else:
                self.is_loading = True
                self.editor_1.clear()
                self.editor_2.clear()
                self.is_loading = False

            self.mark_dirty(True)

    def on_chapter_selected(self):
        self.save_current_text()
        selected_items = self.tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            self.load_item_into_editor(self.active_editor, item)
            self.update_tree_highlights()

    def show_chapter_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return

        self.tree.setCurrentItem(item)

        menu = QMenu(self)

        new_below_act = menu.addAction("Make new chapter below")
        move_act = menu.addAction("Move chapter...")
        delete_act = menu.addAction("Delete chapter")

        action = menu.exec(self.tree.mapToGlobal(pos))

        if action == new_below_act:
            self.add_chapter_below(item)
        elif action == move_act:
            self.tree.start_detached_move(item)
        elif action == delete_act:
            self.delete_chapter()

    def move_chapter_relative(self, item, direction):
        index = self.tree.indexOfTopLevelItem(item)
        new_index = index + direction

        if 0 <= new_index < self.tree.topLevelItemCount():
            self.tree.takeTopLevelItem(index)
            self.tree.insertTopLevelItem(new_index, item)
            self.tree.setCurrentItem(item)

            if not self.is_loading:
                self.mark_dirty(True)

    def add_chapter_below(self, target_item):
        index = self.tree.indexOfTopLevelItem(target_item)
        count = self.tree.topLevelItemCount() + 1
        title = f"Chapter {count}"

        item = QTreeWidgetItem([title])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        item.setData(0, Qt.ItemDataRole.UserRole, "")

        self.tree.insertTopLevelItem(index + 1, item)
        self.tree.setCurrentItem(item)

        if not self.is_loading:
            self.mark_dirty(True)

    def save_current_text(self):
        if self.editor_1.current_item:
            self.editor_1.current_item.setData(0, Qt.ItemDataRole.UserRole, self.editor_1.toHtml())
        if self.dual_view_active and self.editor_2.current_item:
            self.editor_2.current_item.setData(0, Qt.ItemDataRole.UserRole, self.editor_2.toHtml())

    def save_project(self):
        self.save_current_text()

        if not self.current_file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Manuscript Project", "", "Manuscript Files (*.json)"
            )
            if not file_path:
                return False
            if not file_path.endswith(".json"):
                file_path += ".json"
            self.current_file_path = file_path

        chapters_data = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            chapters_data.append({
                "title": item.text(0),
                "content": item.data(0, Qt.ItemDataRole.UserRole) or ""
            })

        dictionary_data = list(self.editor_1.highlighter.ignored_words)

        project_data = {
            "chapters": chapters_data,
            "dictionary": dictionary_data
        }

        try:
            with open(self.current_file_path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, indent=2)

            self.settings.setValue("last_project", self.current_file_path)
            self.mark_dirty(False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save file:\n{str(e)}")
            return False

    def load_project_file(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            if isinstance(raw_data, list):
                chapters = raw_data
                dictionary_words = []
            else:
                chapters = raw_data.get("chapters", [])
                dictionary_words = raw_data.get("dictionary", [])

            self.is_loading = True
            self.tree.clear()
            self.editor_1.current_item = None
            self.editor_2.current_item = None

            for chap in chapters:
                item = QTreeWidgetItem(self.tree, [chap.get("title", "Untitled")])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setData(0, Qt.ItemDataRole.UserRole, chap.get("content", ""))

            self.editor_1.highlighter.ignored_words.clear()
            self.editor_1.highlighter.ignored_words.update(dictionary_words)
            self.editor_1.highlighter.force_refresh()
            self.editor_2.highlighter.force_refresh()

            self.current_file_path = file_path
            self.settings.setValue("last_project", file_path)

            if self.tree.topLevelItemCount() > 0:
                self.tree.setCurrentItem(self.tree.topLevelItem(0))

            self.is_loading = False
            self.mark_dirty(False)
            self.update_title()
            return True

        except Exception:
            self.is_loading = False
            return False

    def open_project(self):
        if self.is_dirty:
            reply = QMessageBox.question(
                self, 'Unsaved Changes',
                'You have unsaved changes. Do you want to save before opening another file?',
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self.save_project():
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Manuscript Project", "", "Manuscript Files (*.json)"
        )
        if not file_path:
            return

        if not self.load_project_file(file_path):
            QMessageBox.critical(self, "Error", f"Failed to open file:\n{file_path}")

    def closeEvent(self, event):
        self.settings.setValue("app_notes", self.notes_panel.toPlainText())

        if not self.is_dirty:
            event.accept()
            return

        reply = QMessageBox.question(
            self, 'Exit',
            'Do you want to save your work before closing?',
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
        )

        if reply == QMessageBox.StandardButton.Save:
            if self.save_project():
                event.accept()
            else:
                event.ignore()
        elif reply == QMessageBox.StandardButton.Discard:
            event.accept()
        else:
            event.ignore()

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    app.setDesktopFileName("NovelCraft")
    window = NovelWriterApp()
    window.show()
    sys.exit(app.exec())
