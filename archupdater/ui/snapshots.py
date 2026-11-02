"""Timeshift snapshots: view, create, delete and restore."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QInputDialog, QLineEdit, QMessageBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import pacman, timeshift
from .common import card, icon, muted_label, run_async, title_label, warn
from .tasks import Step, run_task


class SnapshotsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.loaded = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(title_label("Snapshots", 20))
        head.addStretch(1)
        self.refresh_btn = QPushButton(icon("view-refresh"), "Refresh")
        self.refresh_btn.clicked.connect(self.load)
        head.addWidget(self.refresh_btn)
        lay.addLayout(head)

        self.about = muted_label("")
        lay.addWidget(self.about)

        self.missing = card()
        ml = QHBoxLayout(self.missing)
        ml.addWidget(muted_label("Timeshift isn't installed. It saves restore points of your system so a "
                                 "bad update can be undone in minutes."), 1)
        inst = QPushButton(icon("system-software-install"), "Install Timeshift")
        inst.setObjectName("primary")
        inst.clicked.connect(self.install_timeshift)
        ml.addWidget(inst)
        lay.addWidget(self.missing)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Date", "Comment", "Type", "Name"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._sel)
        lay.addWidget(self.tree, 1)

        self.status = muted_label("")
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.pw_btn = QPushButton(icon("dialog-password"), "Show snapshots (needs password)")
        self.pw_btn.clicked.connect(self.load_with_password)
        self.pw_btn.hide()
        btns.addWidget(self.pw_btn)
        self.create_btn = QPushButton(icon("document-save"), "Create snapshot")
        self.create_btn.setObjectName("primary")
        self.create_btn.clicked.connect(self.create)
        btns.addWidget(self.create_btn)
        btns.addStretch(1)
        self.delete_btn = QPushButton(icon("edit-delete"), "Delete")
        self.delete_btn.clicked.connect(self.delete)
        btns.addWidget(self.delete_btn)
        self.restore_btn = QPushButton(icon("edit-undo"), "Restore…")
        self.restore_btn.setObjectName("danger")
        self.restore_btn.clicked.connect(self.restore)
        btns.addWidget(self.restore_btn)
        lay.addLayout(btns)
        self._sel()
        self._update_about()

    def _update_about(self):
        have_ts = timeshift.available()
        self.missing.setVisible(not have_ts)
        for w in (self.tree, self.create_btn, self.delete_btn, self.restore_btn, self.refresh_btn):
            w.setEnabled(have_ts)
        if not have_ts:
            self.about.setText("")
            return
        parts = [f"Timeshift mode: {timeshift.mode() or 'not set up yet'}."]
        if timeshift.autosnap_installed():
            keep = timeshift.autosnap_keep()
            parts.append("A snapshot is taken automatically before every update"
                         + (f" (the last {keep} are kept)." if keep else "."))
        parts.append("Snapshots cover the system, not your home folder.")
        self.about.setText(" ".join(parts))

    def _sel(self):
        has = bool(self.tree.selectedItems())
        self.delete_btn.setEnabled(has)
        self.restore_btn.setEnabled(has)

    # ---- loading ------------------------------------------------------------------

    def ensure_loaded(self):
        if not self.loaded:
            self.load()

    def load(self):
        self._update_about()
        if not timeshift.available():
            return
        self.status.setText("Loading…")
        run_async(timeshift.list_readonly, self._loaded)

    def _loaded(self, snaps, error):
        if snaps is None:
            self.loaded = False
            self.tree.clear()
            self.status.setText("Your snapshots can only be read with your password.")
            self.pw_btn.show()
            return
        self.loaded = True
        self.pw_btn.hide()
        self._fill(snaps)

    def load_with_password(self):
        from ..util import run
        self.status.setText("Waiting for your password…")
        self.pw_btn.setEnabled(False)
        run_async(lambda: run(timeshift.list_cmd(), timeout=180), self._pw_loaded)

    def _pw_loaded(self, result, error):
        self.pw_btn.setEnabled(True)
        code, out, err = result if result else (1, "", str(error))
        if code != 0:
            self.status.setText("Couldn't list snapshots.")
            return warn(self, "Couldn't list snapshots", (err or out).strip()[-800:] or "Cancelled.")
        self.loaded = True
        self.pw_btn.hide()
        self._fill(timeshift.parse_list(out))

    def _fill(self, snaps):
        self.tree.clear()
        for s in snaps:
            it = QTreeWidgetItem([s.created, s.comment, timeshift.describe_tags(s.tags), s.name])
            it.setData(0, Qt.UserRole, s.name)
            self.tree.addTopLevelItem(it)
        self.status.setText(f"{len(snaps)} snapshot{'s' if len(snaps) != 1 else ''}."
                            if snaps else "No snapshots yet.")

    def _selected(self):
        items = self.tree.selectedItems()
        return items[0].data(0, Qt.UserRole) if items else None

    # ---- actions --------------------------------------------------------------------

    def install_timeshift(self):
        run_task(self, "Install Timeshift", [Step("Installing Timeshift", pacman.install_cmd(["timeshift"]))])
        self.main.after_change()
        self._update_about()

    def create(self):
        comment, ok = QInputDialog.getText(self, "Create snapshot", "Comment (optional):",
                                           QLineEdit.Normal, "Manual snapshot")
        if not ok:
            return
        run_task(self, "Create snapshot", [Step("Creating snapshot (this can take a few minutes)",
                                                timeshift.create_cmd(comment.strip()))])
        self.load()

    def delete(self):
        name = self._selected()
        if not name:
            return
        if QMessageBox.question(self, "Delete snapshot", f"Delete snapshot {name}?") != QMessageBox.Yes:
            return
        run_task(self, "Delete snapshot", [Step(f"Deleting {name}", timeshift.delete_cmd(name))])
        self.load()

    def restore(self):
        name = self._selected()
        if not name:
            return
        text, ok = QInputDialog.getText(
            self, "Restore snapshot",
            f"This puts your system files back to how they were in snapshot {name}.\n\n"
            "• Programs and settings installed after that point are undone.\n"
            "• Your home folder (documents, game saves, browser data) is not touched.\n"
            "• The PC restarts when it's done. Save your work first.\n\n"
            "Type RESTORE to continue:")
        if not ok or text.strip().upper() != "RESTORE":
            return
        run_task(self, "Restore snapshot", [Step(f"Restoring {name}", timeshift.restore_cmd(name))],
                 intro="Don't turn the PC off. It will restart by itself when the restore is finished.")
