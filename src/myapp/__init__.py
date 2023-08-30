import logging
import shutil
import time
import sys
import os

from tufup.client import Client
from tufup.client import install_update 
from myapp import settings
from PySide6 import QtCore, QtGui
from PySide6.QtCore import QSize, Qt, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QDialog, QDialogButtonBox, QProgressDialog
from myapp.settings import APP_NAME, APP_VERSION


images_folder=os.path.join(os.path.dirname(__file__),'images')

logger = logging.getLogger(__name__)

__version__ = settings.APP_VERSION


def download_update(pre: str, progress_hook=None):
    """
    Download the latest update from the update server.
    """

    # Create update client
    client = Client(
        app_name=settings.APP_NAME,
        app_install_dir=settings.INSTALL_DIR,
        current_version=settings.APP_VERSION,
        metadata_dir=settings.METADATA_DIR,
        metadata_base_url=settings.METADATA_BASE_URL,
        target_dir=settings.TARGET_DIR,
        target_base_url=settings.TARGET_BASE_URL,
        refresh_required=False,
    )

    # Perform update
    new_update = client.check_for_updates(pre=pre)
    if new_update:
        # 
        return client._download_updates(progress_hook=progress_hook), client
    else:
        logger.error('Failed to download update.')
    return False, None

def _install_update(client, skip_confirmation: bool = False):
    
    client._apply_updates(
                install=install_update, 
                skip_confirmation=skip_confirmation, 
                # WARNING: Be very careful with `purge_dst_dir=True`, because
                # this will *irreversibly* delete *EVERYTHING* inside the
                # `app_install_dir`, except any paths specified in
                # `exclude_from_purge`. So, *ONLY* use `purge_dst_dir=True` if
                # you are absolutely certain that your `app_install_dir` does not
                # contain any unrelated content.
                purge_dst_dir=False,
                exclude_from_purge=None,
                log_file_name='install.log',
            )


# Main window application
class MainWindow(QMainWindow):


    class UpdateChecker(QtCore.QRunnable):
        # Thread that peridoically checks for updates and emits a signal if an update is available
        class Signals(QtCore.QObject):
            
            update_available = Signal(str)

        def __init__(self, client, ask_user_to_update_fn) -> None:
            super().__init__()
            self.signals = self.Signals()
            self.signals.update_available.connect(ask_user_to_update_fn)
            self.client = client
            self._is_running = True

        def run(self) -> None:
            while self._is_running:
                print("checking for updates...")

                client = Client(
                    app_name=settings.APP_NAME,
                    app_install_dir=settings.INSTALL_DIR,
                    current_version=settings.APP_VERSION,
                    metadata_dir=settings.METADATA_DIR,
                    metadata_base_url=settings.METADATA_BASE_URL,
                    target_dir=settings.TARGET_DIR,
                    target_base_url=settings.TARGET_BASE_URL,
                    refresh_required=False,
                )
                update_available = client.check_for_updates()
                if update_available:
                    print("update available")
                    self.signals.update_available.emit(str(update_available.version))
                    return 
                print("no update available")
                
                # depending on the time, a simple time.sleep(100000) will run this process for 100000 seconds after the main window is closed
                # With the for loop, the check for _is_running is done every second, so the process will stop in a range of 1 second after the window is closed
                for i in range(5) : # change to 60 for 1 minute, 300 for 5 minutes, etc.
                    if not self._is_running:
                        return
                    time.sleep(1)

        def stop(self):
            self._is_running = False


    def __init__(self, pre_release_channel: str = None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.pre_release_channel = pre_release_channel

        self.hw_label = QLabel("Hello World !!", alignment=Qt.AlignCenter)
        
        client = Client(
            app_name=settings.APP_NAME,
            app_install_dir=settings.INSTALL_DIR,
            current_version=settings.APP_VERSION,
            metadata_dir=settings.METADATA_DIR,
            metadata_base_url=settings.METADATA_BASE_URL,
            target_dir=settings.TARGET_DIR,
            target_base_url=settings.TARGET_BASE_URL,
            refresh_required=False,
        )

        self.update_checker = self.UpdateChecker(client, self.show_update_popup)
        self.threadpool = QThreadPool()
        self.threadpool.start(self.update_checker)

        #update_available = client.check_for_updates(pre=pre_release_channel)
        
        self.layout = QVBoxLayout()

        self.layout.addWidget(self.hw_label)
        
        self.hw_label.setText("Hello World !! No update available")

        self.central_widget = QWidget()
        self.central_widget.setLayout(self.layout)
        self.setCentralWidget(self.central_widget)
        self.resize(640, 480)

    @Slot(str)
    def show_update_popup(self, version: str):
        #self.movie_label = QLabel("update...", alignment=Qt.AlignCenter)
        #self.movie = QtGui.QMovie(os.path.join(images_folder,'update.gif'))
        #self.movie.setScaledSize(QSize(350, 200))
        #self.movie_label.setMovie(self.movie)
        #self.layout.addWidget(self.movie_label)
        #self.movie.start()
        #self.movie_label.show()

        # create a popup window

        self.popup = QDialog(self)
        self.popup.setWindowTitle("Update Available")
        self.popup_layout = QVBoxLayout()
        
        update_label = QLabel(f"A new update is available!\n Current version: {__version__}\n New version: {version}\n  Update now?", alignment=Qt.AlignCenter)
        self.popup_layout.addWidget(update_label)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.popup_layout.addWidget(self.button_box)
        self.popup.resize(300, 200)
        
        self.button_box.accepted.connect(self.start_update_procedure)
        self.button_box.rejected.connect(self.popup.reject)
        self.popup.setLayout(self.popup_layout)
        self.popup.show()

    def show_update_progress_dialog(self):
        self.progress_dialog = QProgressDialog("Downloading update...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Update Progress")
        self.progress_dialog.setWindowModality(Qt.NonModal)
        self.progress_dialog.canceled.connect(self.progress_dialog.close)
        self.progress_dialog.show()

    def progress_hook(self, bytes_downloaded: int, bytes_expected: int):
        if bytes_expected > 0:
            self.progress_dialog.setValue(int(float(bytes_downloaded) / float(bytes_expected) * 100.0))

    def hide_window_and_start_update(self, client, skip_confirmation = False):
        self.setVisible(False)
        _install_update(client, skip_confirmation=skip_confirmation)

    def start_update_procedure(self):
        # close the popup and update the app
        self.popup.close()
        self.show_update_progress_dialog()
        # only hide the main window for now, the app is exited at the end of the update() function
        #self.setVisible(False)
        dl_success, client = download_update(pre=self.pre_release_channel, progress_hook=self.progress_hook)

        if dl_success:

            self.progress_dialog.close()
            update_label = QLabel("The application needs to be restarted to install the update. Restart now ?", alignment=Qt.AlignCenter)

            self.install_update_popup = QDialog(self)
            self.install_update_popup.setWindowTitle("Install Update Now ?")
            self.install_update_popup_layout = QVBoxLayout()
            self.install_update_popup_layout.addWidget(update_label)
            QBtn = QDialogButtonBox.Yes | QDialogButtonBox.No
            self.install_update_popup_button_box = QDialogButtonBox(QBtn)

            # when the user clicks on the "Yes" button, the update is installed and the app is restarted
            self.install_update_popup_button_box.accepted.connect(lambda: self.hide_window_and_start_update(client, skip_confirmation=True))

            self.install_update_popup_button_box.rejected.connect(self.install_update_popup.reject)
            self.install_update_popup_layout.addWidget(self.install_update_popup_button_box)
            self.install_update_popup.setLayout(self.install_update_popup_layout)
            self.install_update_popup.show()
            

    
    # override closeEvent to stop the update checker thread
    def closeEvent(self, event):
        self.setVisible(False)
        event.ignore()
        self.update_checker.stop()
        self.threadpool.waitForDone()
        sys.exit(0)



def main(cmd_args):
    # extract options from command line args
    pre_release_channel = cmd_args[0] if cmd_args else None  # 'a', 'b', or 'rc'

    # The app must ensure dirs exist
    for dir_path in [settings.INSTALL_DIR, settings.METADATA_DIR, settings.TARGET_DIR]:
        dir_path.mkdir(exist_ok=True, parents=True)

    # The app must be shipped with a trusted "root.json" metadata file,
    # which is created using the tufup.repo tools. The app must ensure
    # this file can be found in the specified metadata_dir. The root metadata
    # file lists all trusted keys and TUF roles.
    if not settings.TRUSTED_ROOT_DST.exists():
        shutil.copy(src=settings.TRUSTED_ROOT_SRC, dst=settings.TRUSTED_ROOT_DST)
        logger.info('Trusted root metadata copied to cache.')


    # Launch the app
    app = QApplication(sys.argv)
    window = MainWindow(pre_release_channel=pre_release_channel)
    window.show()
    app.exec_()

    print(f'Ending {settings.APP_NAME} {settings.APP_VERSION}...')

