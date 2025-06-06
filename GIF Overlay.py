import sys
import os
import shutil
from pathlib import Path
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication, QLabel, QFileDialog, QWidget,
    QVBoxLayout, QMenu, QMessageBox, QInputDialog,
    QListWidget, QListWidgetItem, QDialog, QPushButton, QHBoxLayout,
    QSlider, QGridLayout, QSystemTrayIcon, QAction
)
from PyQt5.QtGui import QMovie, QIcon
from PyQt5.QtCore import Qt, QSize

# Thư mục lưu cấu hình trong %APPDATA%
CONFIG_DIR = Path(os.getenv('APPDATA')) / "GIF Overlay"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "last_gif_path.txt"

GIF_SAVE_DIR = Path.home() / "Documents" / "GIF-save"

class GifListItemWidget(QWidget):
    def __init__(self, file_path: Path, parent_dialog: QDialog):
        super().__init__()
        self.file_path = file_path
        self.parent_dialog = parent_dialog

        layout = QHBoxLayout()
        layout.setContentsMargins(5, 0, 5, 0)

        self.label = QLabel(file_path.name)
        layout.addWidget(self.label)

        layout.addStretch()

        self.rename_btn = QPushButton("Đổi tên")
        self.rename_btn.setFixedSize(70, 25)
        self.rename_btn.clicked.connect(self.rename_file)
        layout.addWidget(self.rename_btn)

        self.delete_btn = QPushButton("Xóa")
        self.delete_btn.setFixedSize(50, 25)
        self.delete_btn.clicked.connect(self.delete_file)
        layout.addWidget(self.delete_btn)

        self.setLayout(layout)

    def rename_file(self):
        base_name = self.file_path.stem
        new_name, ok = QInputDialog.getText(
            self, "Đổi tên file", "Nhập tên file mới (không cần đuôi .gif):", text=base_name
        )
        if not (ok and new_name.strip()):
            return
        if not new_name.lower().endswith(".gif"):
            new_name += ".gif"
        new_path = self.file_path.with_name(new_name)
        if new_path.exists():
            QMessageBox.warning(self, "Đổi tên file", "File đã tồn tại với tên này!")
            return
        try:
            self.file_path.rename(new_path)
            self.file_path = new_path
            self.label.setText(new_path.name)
            self.parent_dialog.load_gif_list()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể đổi tên file:\n{e}")

    def delete_file(self):
        try:
            os.remove(self.file_path)
            self.parent_dialog.load_gif_list()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể xóa file:\n{e}")

class GifManagerDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Quản lý ảnh GIF đã lưu")
        self.resize(450, 300)

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.load_gif_list()

    def load_gif_list(self):
        self.list_widget.clear()
        if not GIF_SAVE_DIR.exists():
            return
        for gif_path in sorted(GIF_SAVE_DIR.glob("*.gif")):
            item = QListWidgetItem()
            widget = GifListItemWidget(gif_path, self)
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

class GifOnTop(QWidget):
    RESIZE_MARGIN = 8

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)

        self.gif_label = QLabel()
        self.gif_label.setAttribute(Qt.WA_TranslucentBackground)
        self.gif_label.setStyleSheet("background: transparent;")
        self.layout.addWidget(self.gif_label)

        self.movie: Optional[QMovie] = None
        self.current_gif_path: Optional[str] = None
        self.original_size: Optional[QSize] = None

        self.drag_position = None

        self.resize(300, 300)
        self.load_last_gif()
        self.show()
        if not self.current_gif_path:
            self.show_menu_at_center()

        # Xác định thư mục chứa .exe hoặc source (hỗ trợ khi đóng gói PyInstaller)
        base_dir = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))
        icon_path = base_dir / "app_icon.ico"

        self.tray_icon = QSystemTrayIcon(self)
        if icon_path.exists():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(QApplication.style().SP_ComputerIcon))

        tray_menu = QMenu()
        show_action = QAction("Hiện cửa sổ", self)
        quit_action = QAction("Thoát", self)
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)

        show_action.triggered.connect(self.show_normal)
        quit_action.triggered.connect(QApplication.quit)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def create_menu(self):
        menu = QMenu(self)
        change_menu = menu.addMenu("Thay đổi ảnh GIF")
        self.action_change_new = change_menu.addAction("Ảnh GIF mới")
        self.action_change_saved = change_menu.addAction("Ảnh GIF đã lưu")

        menu.addSeparator()

        self.action_change_resize_opacity = menu.addAction("Thay đổi kích thước và độ mờ")

        menu.addSeparator()

        self.action_toggle_pause = menu.addAction("Tạm dừng / Phát GIF")

        menu.addSeparator()

        self.action_manage = menu.addAction("Quản lí ảnh đã lưu")
        self.action_save = menu.addAction("Lưu ảnh GIF")

        close_menu = menu.addMenu("Đóng ảnh GIF (Thoát ứng dụng)")
        self.action_close_quit = close_menu.addAction("Đóng hẳn app")
        self.action_close_minimize = close_menu.addAction("Thu nhỏ vào khay hệ thống")

        return menu

    def handle_menu_action(self, action):
        if action == self.action_change_new:
            self.open_file_dialog()
        elif action == self.action_change_saved:
            self.open_saved_gif_dialog()
        elif action == self.action_change_resize_opacity:
            self.open_resize_opacity_dialog()
        elif action == self.action_toggle_pause:
            self.toggle_pause_gif()
        elif action == self.action_manage:
            self.open_saved_folder()
        elif action == self.action_save:
            self.save_gif_to_documents()
        elif action == self.action_close_quit:
            QApplication.quit()
        elif action == self.action_close_minimize:
            flags = self.windowFlags() | Qt.Tool
            self.setWindowFlags(flags)
            self.show()
            self.raise_()
            self.activateWindow()
            self.tray_icon.showMessage(
                "GIF Overlay",
                "Đã thu nhỏ vào khay hệ thống (ẩn icon taskbar).",
                QSystemTrayIcon.Information,
                2000
            )

    def contextMenuEvent(self, event):
        menu = self.create_menu()
        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action:
            self.handle_menu_action(action)

    def show_menu_at_center(self):
        menu = self.create_menu()
        pos = self.mapToGlobal(self.rect().center())
        action = menu.exec_(pos)
        if action:
            self.handle_menu_action(action)

    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select GIF file", "", "GIF Files (*.gif)")
        if path:
            self.load_gif(path)

    def load_gif(self, path):
        if self.movie:
            self.movie.stop()
        self.movie = QMovie(path)
        self.gif_label.setMovie(self.movie)
        self.movie.start()
        self.original_size = self.movie.currentPixmap().size()
        self.resize(self.original_size)
        self.current_gif_path = path
        self.save_last_gif(path)

    def save_last_gif(self, path):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(path)
        except Exception as e:
            print(f"Error saving last gif path: {e}")

    def load_last_gif(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    path = f.read().strip()
                    if os.path.exists(path):
                        self.load_gif(path)
            except Exception as e:
                print(f"Error loading last gif path: {e}")

    def open_saved_gif_dialog(self):
        if not GIF_SAVE_DIR.exists():
            QMessageBox.information(self, "Ảnh GIF đã lưu", "Chưa có thư mục hoặc ảnh GIF đã lưu.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh GIF đã lưu", str(GIF_SAVE_DIR), "GIF Files (*.gif)")
        if path:
            self.load_gif(path)

    def save_gif_to_documents(self):
        if not self.current_gif_path or not os.path.exists(self.current_gif_path):
            QMessageBox.warning(self, "Lưu ảnh GIF", "Không có ảnh GIF để lưu.")
            return
        GIF_SAVE_DIR.mkdir(exist_ok=True)
        default_name = os.path.basename(self.current_gif_path)
        default_base = os.path.splitext(default_name)[0]
        new_name, ok = QInputDialog.getText(self, "Đổi tên file", "Nhập tên file (không cần đuôi .gif):", text=default_base)
        if ok and new_name.strip():
            if not new_name.lower().endswith(".gif"):
                new_name += ".gif"
            dest = GIF_SAVE_DIR / new_name
            try:
                shutil.copy2(self.current_gif_path, dest)
                QMessageBox.information(self, "Lưu ảnh GIF", f"Đã lưu ảnh GIF vào:\n{dest}")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Lỗi khi lưu ảnh GIF:\n{e}")

    def open_saved_folder(self):
        dlg = GifManagerDialog(self)
        dlg.exec_()

    def toggle_pause_gif(self):
        if not self.movie:
            return
        if self.movie.state() == QMovie.Running:
            self.movie.setPaused(True)
        else:
            self.movie.setPaused(False)

    def open_resize_opacity_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Thay đổi kích thước và độ mờ")
        layout = QGridLayout(dialog)

        label_w = QLabel(f"Chiều rộng: {self.width()}")
        slider_w = QSlider(Qt.Horizontal)
        slider_w.setMinimum(50)
        slider_w.setMaximum(2000)
        slider_w.setValue(self.width())

        label_h = QLabel(f"Chiều cao: {self.height()}")
        slider_h = QSlider(Qt.Horizontal)
        slider_h.setMinimum(50)
        slider_h.setMaximum(2000)
        slider_h.setValue(self.height())

        label_o = QLabel(f"Độ mờ: {int(self.windowOpacity()*100)}%")
        slider_o = QSlider(Qt.Horizontal)
        slider_o.setMinimum(10)
        slider_o.setMaximum(100)
        slider_o.setValue(int(self.windowOpacity()*100))

        def update_width(value):
            label_w.setText(f"Chiều rộng: {value}")
            self.resize(value, self.height())
            if self.movie:
                self.movie.setScaledSize(QSize(value, self.height()))

        def update_height(value):
            label_h.setText(f"Chiều cao: {value}")
            self.resize(self.width(), value)
            if self.movie:
                self.movie.setScaledSize(QSize(self.width(), value))

        def update_opacity(value):
            label_o.setText(f"Độ mờ: {value}%")
            self.setWindowOpacity(value / 100)

        slider_w.valueChanged.connect(update_width)
        slider_h.valueChanged.connect(update_height)
        slider_o.valueChanged.connect(update_opacity)

        layout.addWidget(label_w, 0, 0)
        layout.addWidget(slider_w, 0, 1)
        layout.addWidget(label_h, 1, 0)
        layout.addWidget(slider_h, 1, 1)
        layout.addWidget(label_o, 2, 0)
        layout.addWidget(slider_o, 2, 1)

        btn_reset = QPushButton("Phục hồi mặc định")
        def reset_defaults():
            if self.original_size:
                ow, oh = self.original_size.width(), self.original_size.height()
                slider_w.setValue(ow)
                slider_h.setValue(oh)
                self.resize(self.original_size)
                if self.movie:
                    self.movie.setScaledSize(self.original_size)
            slider_o.setValue(100)
            self.setWindowOpacity(1.0)
        btn_reset.clicked.connect(reset_defaults)
        layout.addWidget(btn_reset, 3, 0, 1, 2)

        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close, 4, 0, 1, 2)

        dialog.exec_()

    def show_normal(self):
        flags = self.windowFlags()
        flags = flags & (~Qt.Tool)
        self.setWindowFlags(flags)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Thoát ứng dụng",
            "Bạn muốn đóng ứng dụng hay thu nhỏ vào khay hệ thống?",
            QMessageBox.Close | QMessageBox.Ignore,
            QMessageBox.Ignore
        )
        if reply == QMessageBox.Close:
            event.accept()
        else:
            event.ignore()
            flags = self.windowFlags() | Qt.Tool
            self.setWindowFlags(flags)
            self.show()
            self.tray_icon.showMessage(
                "GIF Overlay",
                "Đã thu nhỏ vào khay hệ thống (ẩn icon taskbar).",
                QSystemTrayIcon.Information,
                2000
            )

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                flags = self.windowFlags()
                flags = flags & (~Qt.Tool)
                self.setWindowFlags(flags)
                self.show()
                self.raise_()
                self.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()
        else:
            super().mouseMoveEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GifOnTop()
    sys.exit(app.exec_())
