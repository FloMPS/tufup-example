import sys

from myapp.auto_update_adapter import AutoUpdateApdapter
from PySide6.QtCore import  Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
from myapp.settings import APP_NAME, APP_VERSION
__version__ = APP_VERSION

# Main window application
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.hw_label = QLabel("Hello World !!", alignment=Qt.AlignCenter)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.hw_label)
        self.central_widget = QWidget()
        self.central_widget.setLayout(self.layout)
        self.setCentralWidget(self.central_widget)
        self.resize(640, 480)

def main(cmd_line):
    #pre_release_channel = cmd_args[0] if cmd_args else None  # 'a', 'b', or 'rc'
    # Launch the application
    app = QApplication(sys.argv)
    window = MainWindow()
    AutoUpdateApdapter(window)
    window.show()
    app.exec_()


