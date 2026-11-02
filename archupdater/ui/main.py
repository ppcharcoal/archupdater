"""Main window: sidebar + pages."""

import sys

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow,
                               QStackedWidget, QWidget)

from .. import APP_ID, VERSION
from ..util import load_settings
from .common import icon
from .programs import ProgramsPage
from .snapshots import SnapshotsPage
from .store import StorePage
from .style import QSS
from .updates import UpdatesPage

PAGES = [
    ("programs", "Installed", "applications-other"),
    ("store", "Get apps", "system-software-install"),
    ("updates", "Updates", "system-software-update"),
    ("snapshots", "Snapshots", "document-save"),
]


class MainWindow(QMainWindow):
    def __init__(self, start_page="programs"):
        super().__init__()
        self.setWindowTitle(f"ArchUpdater {VERSION}")
        self.resize(1180, 760)
        self.settings = load_settings()
        self.installed = {}
        self.flatpak_ids = set()
        self.updates = {}

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        self.sidebar.setIconSize(QSize(22, 22))
        lay.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.programs = ProgramsPage(self)
        self.store = StorePage(self)
        self.updates_page = UpdatesPage(self)
        self.snapshots = SnapshotsPage(self)
        self.pages = {"programs": self.programs, "store": self.store,
                      "updates": self.updates_page, "snapshots": self.snapshots}
        self.items = {}
        for key, text, ic in PAGES:
            it = QListWidgetItem(icon(ic), text)
            it.setData(Qt.UserRole, key)
            self.sidebar.addItem(it)
            self.items[key] = it
            self.pages[key].setObjectName("page")
            self.stack.addWidget(self.pages[key])
        self.sidebar.currentRowChanged.connect(self._page_changed)

        self.show_page(start_page if start_page in self.pages else "programs")
        self.programs.load()
        QTimer.singleShot(600, self.updates_page.check)

    # ---- navigation -------------------------------------------------------------

    def show_page(self, key):
        self.sidebar.setCurrentRow(list(self.pages).index(key))

    def _page_changed(self, row):
        key = self.sidebar.item(row).data(Qt.UserRole)
        self.stack.setCurrentWidget(self.pages[key])
        if key == "snapshots":
            self.snapshots.ensure_loaded()

    # ---- shared state -------------------------------------------------------------

    def update_for(self, ref):
        return self.updates.get(tuple(ref)) if ref else None

    def set_updates(self, updates):
        self.updates = updates
        n = len(updates)
        self.items["updates"].setText(f"Updates  ({n})" if n else "Updates")
        self.programs.populate()

    def installed_changed(self):
        self.store.refresh_marks()

    def after_change(self):
        """Called after anything was installed/removed/updated."""
        self.programs.load()


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    start = "programs"
    for i, a in enumerate(argv):
        if a == "--page" and i + 1 < len(argv):
            start = argv[i + 1]
        elif a in ("--updates", "--update"):
            start = "updates"
        elif a == "--store":
            start = "store"
        elif a in ("--version", "-V"):
            print(f"archupdater {VERSION}")
            return 0
    QApplication.setDesktopFileName(APP_ID)
    app = QApplication(argv)
    app.setApplicationName("ArchUpdater")
    app.setWindowIcon(QIcon.fromTheme(APP_ID, icon("system-software-update")))
    app.setStyleSheet(QSS)
    win = MainWindow(start)
    win.show()
    return app.exec()
