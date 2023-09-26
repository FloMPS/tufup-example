import logging
import time
import sys
import os
import shutil

from tufup.client import Client
from tufup.client import install_update 
from myapp import settings
from PySide6 import QtCore
from PySide6.QtCore import  Qt, QThreadPool, Signal, Slot, QSettings, QDateTime
from PySide6.QtWidgets import QMainWindow, QMenu, QPushButton, QLabel, QVBoxLayout, QDialog, QDialogButtonBox, QProgressDialog
from PySide6.QtGui import QAction
from myapp.settings import APP_VERSION


images_folder=os.path.join(os.path.dirname(__file__),'images')

logger = logging.getLogger(__name__)


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

class RemindUpdateButton(QPushButton):
    def __init__(self, parent=None, callback: callable = None):
        super().__init__("Remind me later...", parent)
        self.clicked.connect(self.show_remind_later_options)
        self.menu = QMenu(self)
        self.callback = callback
    def show_remind_later_options(self):
        in_15_seconds = QAction("In 15 seconds", self)
        in_15_seconds.triggered.connect(lambda: self.set_remind_later(15))
        self.menu.addAction(in_15_seconds)
        in_1_hour = QAction("In 1 hour", self)
        in_1_hour.triggered.connect(lambda: self.set_remind_later(1 * 60 * 60))
        self.menu.addAction(in_1_hour)
        tomorrow = QAction("Tomorrow", self)
        tomorrow.triggered.connect(lambda: self.set_remind_later(24 * 60 * 60))
        self.menu.addAction(tomorrow)
        in_1_week = QAction("In 1 week", self)
        in_1_week.triggered.connect(lambda: self.set_remind_later(7 * 24 * 60 * 60))
        self.menu.addAction(in_1_week)
        never = QAction("Never", self)
        never.triggered.connect(lambda: self.set_remind_later(-1))
        self.menu.addAction(never)
        self.menu.exec_(self.mapToGlobal(self.rect().bottomLeft()))
        if self.callback:
            self.callback()

    def set_remind_later(self, seconds: int):
        settings_ = QSettings("MyCompany", "MyApp")
        if seconds == -1:
            settings_.setValue("remind_later", -1)
        else:
            remind_time = QDateTime.currentDateTime().addSecs(seconds)
            settings_.setValue("remind_later", remind_time)

class UpdateChecker(QtCore.QRunnable):
    # Thread that peridoically checks for updates and emits a signal if an update is available
    class Signals(QtCore.QObject):
        
        update_available = Signal(str)

    def __init__(self, ask_user_to_update_fn) -> None:
        super().__init__()
        self.signals = self.Signals()
        self.signals.update_available.connect(ask_user_to_update_fn)
        self.is_update_popup_shown = False
        self._is_running = True

    def run(self) -> None:
        while self._is_running:
            settings_ = QSettings("MyCompany", "MyApp")
            #TODO Remove this
            #settings_.remove("remind_later")

            remind_later = settings_.value("remind_later", QDateTime.fromSecsSinceEpoch(0))
            if remind_later == -1:
                print("never remind")
                return
            elif self.is_update_popup_shown:
                #update popup is already shown, do nothing until it is closed
                print("update popup shown")
                pass
            elif QDateTime.currentDateTime() < remind_later:
                print("remind later, dont check for updates")
            else:
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
                #update_available = type("", (object,),{"version":"1.3.4"}) 
                update_available = client.check_for_updates()
                if update_available:
                    print("update available")
                    self.is_update_popup_shown = True
                    self.signals.update_available.emit(str(update_available.version))
                print("no update available")
            
            # A simple time.sleep(5) will run this process for 5 seconds after the main window is closed
            # With the for loop, the check for _is_running is done every second, so the process will stop in a range of 1 second after the window is closed
            for i in range(5) : # change to 60 for 1 minute, 300 for 5 minutes, etc.
                if not self._is_running:
                    return
                time.sleep(1)

    def stop(self):
        self._is_running = False

class AutoUpdateApdapter():
    def __init__(self, main_window: QMainWindow, pre_release_channel: str = None):
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

        self.main_window = main_window
        self.update_checker = UpdateChecker(self.show_update_popup)
        self.threadpool = QThreadPool()
        self.threadpool.start(self.update_checker)
        self.pre_release_channel = pre_release_channel
        self.main_window.closeEvent = self.closeEvent
        #update_available = client.check_for_updates(pre=pre_release_channel)
    
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

        self.popup = QDialog(self.main_window)
        self.popup.setWindowTitle("Update Available")
        self.popup_layout = QVBoxLayout()
        
        update_label = QLabel(f"A new update is available!\n Current version: {APP_VERSION}\n New version: {version}\n  Update now?", alignment=Qt.AlignCenter)
        self.popup_layout.addWidget(update_label)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self.popup)
        self.remind_later_button = RemindUpdateButton(self.popup, self.notify_update_popup_closed)
        self.button_box.addButton(self.remind_later_button, QDialogButtonBox.ActionRole)
        self.popup_layout.addWidget(self.button_box)
        self.popup.resize(300, 200)
        
        self.remind_later_button.clicked.connect(self.popup.reject)
        self.button_box.accepted.connect(self.start_update_procedure)
        self.button_box.rejected.connect(self.popup.reject)
        self.popup.setLayout(self.popup_layout)
        self.popup.show()
    
    def notify_update_popup_closed(self):
        self.update_checker.is_update_popup_shown = False

    def show_update_progress_dialog(self):
        self.progress_dialog = QProgressDialog("Downloading update...", "Cancel", 0, 100, self.main_window)
        self.progress_dialog.setWindowTitle("Update Progress")
        self.progress_dialog.setWindowModality(Qt.NonModal)
        self.progress_dialog.canceled.connect(self.progress_dialog.close)
        self.progress_dialog.show()

    def progress_hook(self, bytes_downloaded: int, bytes_expected: int):
        if bytes_expected > 0:
            self.progress_dialog.setValue(int(float(bytes_downloaded) / float(bytes_expected) * 100.0))

    def hide_window_and_start_update(self, client, skip_confirmation = False):
        self.main_window.setVisible(False)
        self.install_update_popup.setVisible(False)
        _install_update(client, skip_confirmation=skip_confirmation)
        self.main_window.close()                

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

            self.install_update_popup = QDialog(self.main_window)
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
        self.main_window.setVisible(False)
        event.ignore()
        self.update_checker.stop()
        self.threadpool.waitForDone()
        sys.exit(0)