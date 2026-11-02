"""Installed software: programs, all packages, AUR, Flatpak, unused packages."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import aur, flatpak, pacman
from ..util import human_size
from .common import busy_cursor, card, confirm_list, icon, info, muted_label, pixmap, run_async, title_label, warn
from .tasks import Step, run_task

FILTERS = [
    ("Programs", "programs"),
    ("Installed by you", "explicit"),
    ("All packages", "all"),
    ("Dependencies (libraries)", "deps"),
    ("AUR packages", "aur"),
    ("Flatpak apps", "flatpak"),
    ("Unused packages", "orphans"),
]

SOURCE_NAMES = {"repo": "Official", "aur": "AUR", "flatpak": "Flatpak"}


class _Item(QTreeWidgetItem):
    def __lt__(self, other):
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if col == 3:
            return (self.data(3, Qt.UserRole) or 0) < (other.data(3, Qt.UserRole) or 0)
        return self.text(col).lower() < other.text(col).lower()


def load_everything():
    pkgs = pacman.installed_packages()
    apps = flatpak.installed_apps()
    orph = set(pacman.orphans())
    return pkgs, apps, orph


class ProgramsPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.pkgs, self.flatpaks, self.orphans = {}, [], set()
        self.current = None  # ("pkg", name) / ("flatpak", id)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(title_label("Installed software", 20))
        head.addStretch(1)
        self.count = muted_label("")
        head.addWidget(self.count)
        lay.addLayout(head)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search installed software…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.populate)
        bar.addWidget(self.search, 1)
        self.filter = QComboBox()
        for text, key in FILTERS:
            self.filter.addItem(text, key)
        self.filter.currentIndexChanged.connect(self.populate)
        bar.addWidget(self.filter)
        self.clean_btn = QPushButton(icon("edit-clear-all"), "Remove all unused")
        self.clean_btn.clicked.connect(self.remove_orphans)
        self.clean_btn.hide()
        bar.addWidget(self.clean_btn)
        refresh = QPushButton(icon("view-refresh"), "")
        refresh.setToolTip("Reload the list")
        refresh.clicked.connect(self.load)
        bar.addWidget(refresh)
        lay.addLayout(bar)

        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Version", "Source", "Size"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.setAlternatingRowColors(True)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tree.currentItemChanged.connect(self.show_details)
        split.addWidget(self.tree)

        self.details = card()
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(18, 18, 18, 18)
        top = QHBoxLayout()
        self.d_icon = QLabel()
        self.d_icon.setFixedSize(56, 56)
        top.addWidget(self.d_icon)
        tl = QVBoxLayout()
        self.d_title = title_label("", 16)
        self.d_sub = muted_label("")
        tl.addWidget(self.d_title)
        tl.addWidget(self.d_sub)
        top.addLayout(tl, 1)
        dl.addLayout(top)
        self.d_desc = QLabel()
        self.d_desc.setWordWrap(True)
        dl.addWidget(self.d_desc)
        self.d_form = QFormLayout()
        self.d_form.setLabelAlignment(Qt.AlignRight)
        dl.addLayout(self.d_form)
        self.d_update = QLabel()
        self.d_update.setObjectName("accent")
        self.d_update.setWordWrap(True)
        dl.addWidget(self.d_update)
        dl.addStretch(1)
        btns = QHBoxLayout()
        self.update_btn = QPushButton(icon("system-software-update"), "Update")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self.update_current)
        btns.addWidget(self.update_btn)
        btns.addStretch(1)
        self.remove_btn = QPushButton(icon("edit-delete"), "Uninstall")
        self.remove_btn.setObjectName("danger")
        self.remove_btn.clicked.connect(self.uninstall_current)
        btns.addWidget(self.remove_btn)
        dl.addLayout(btns)
        split.addWidget(self.details)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([620, 380])
        lay.addWidget(split, 1)

        self._clear_details("Loading installed software…")

    # ---- data -----------------------------------------------------------------

    def load(self):
        self.count.setText("Loading…")
        run_async(load_everything, self._loaded)

    def _loaded(self, result, error):
        if error or result is None:
            self.count.setText(f"Could not load packages: {error}")
            return
        self.pkgs, self.flatpaks, self.orphans = result
        self.main.installed = self.pkgs
        self.main.flatpak_ids = {a["id"] for a in self.flatpaks}
        self.populate()
        self.main.installed_changed()

    def populate(self):
        key = self.filter.currentData()
        query = self.search.text().strip().lower()
        self.clean_btn.setVisible(key == "orphans" and bool(self.orphans))
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        rows = []
        if key != "flatpak":
            for p in self.pkgs.values():
                if key == "programs" and not p.app_name:
                    continue
                if key == "explicit" and not p.explicit:
                    continue
                if key == "deps" and p.explicit:
                    continue
                if key == "aur" and p.source != "aur":
                    continue
                if key == "orphans" and p.name not in self.orphans:
                    continue
                shown = p.app_name if (key == "programs" and p.app_name) else p.name
                hay = f"{p.name} {p.app_name} {p.description}".lower()
                if query and query not in hay:
                    continue
                rows.append((shown, p.version, SOURCE_NAMES.get(p.source, p.source), p.size,
                             ("pkg", p.name), p.icon if p.app_name else ""))
        if key in ("programs", "flatpak", "all"):
            for a in self.flatpaks:
                hay = f"{a['id']} {a['name']}".lower()
                if query and query not in hay:
                    continue
                rows.append((a["name"], a["version"], "Flatpak", a["size"], ("flatpak", a["id"]), a["id"]))
        for name, version, source, size, ref, ic in rows:
            it = _Item([name, version, source, human_size(size)])
            it.setData(0, Qt.UserRole, ref)
            it.setData(3, Qt.UserRole, size)
            if key in ("programs", "flatpak"):
                it.setIcon(0, icon(ic, "application-x-executable"))
            if self.main.update_for(ref):
                it.setText(1, f"{version}  ↑")
                it.setToolTip(1, "Update available")
            self.tree.addTopLevelItem(it)
        self.tree.setSortingEnabled(True)
        noun = {"programs": "programs", "flatpak": "apps"}.get(key, "packages")
        self.count.setText(f"{len(rows)} {noun}")
        if rows:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        else:
            self._clear_details("Nothing here." if not query else "No matches.")

    # ---- details panel --------------------------------------------------------

    def _clear_form(self):
        while self.d_form.rowCount():
            self.d_form.removeRow(0)

    def _clear_details(self, text):
        self.current = None
        self.d_icon.clear()
        self.d_title.setText("")
        self.d_sub.setText(text)
        self.d_desc.setText("")
        self.d_update.setText("")
        self._clear_form()
        self.update_btn.hide()
        self.remove_btn.hide()

    def show_details(self, item, _prev=None):
        if item is None:
            return self._clear_details("Select something on the left.")
        kind, key = item.data(0, Qt.UserRole)
        self.current = (kind, key)
        self._clear_form()
        upd = self.main.update_for((kind, key))
        if kind == "pkg":
            p = self.pkgs.get(key)
            if p is None:
                return
            self.d_icon.setPixmap(pixmap(p.icon or "package-x-generic", 48))
            self.d_title.setText(p.app_name or p.name)
            src = "Official repositories" if p.source == "repo" else "AUR / installed manually"
            self.d_sub.setText(f"{p.name} · {src}")
            self.d_desc.setText(p.description)
            self.d_form.addRow("Version:", QLabel(p.version))
            self.d_form.addRow("Size:", QLabel(human_size(p.size) or "–"))
            self.d_form.addRow("Installed:", QLabel(p.install_date or "–"))
            self.d_form.addRow("Why:", QLabel("You installed it" if p.explicit else "Needed by other software"))
            if p.required_by:
                needed = QLabel(", ".join(p.required_by[:12]) + (" …" if len(p.required_by) > 12 else ""))
                needed.setWordWrap(True)
                self.d_form.addRow("Needed by:", needed)
            if p.name in self.orphans:
                self.d_form.addRow("", muted_label("Nothing uses this anymore - safe to remove."))
        else:
            a = next((x for x in self.flatpaks if x["id"] == key), None)
            if a is None:
                return
            self.d_icon.setPixmap(pixmap(flatpak.icon_path(key) or key, 48, "application-x-executable"))
            self.d_title.setText(a["name"])
            self.d_sub.setText(f"{a['id']} · Flatpak ({a['origin']}, {a['installation']})")
            self.d_desc.setText("")
            self.d_form.addRow("Version:", QLabel(a["version"] or "–"))
            self.d_form.addRow("Size:", QLabel(human_size(a["size"]) or "–"))
        if upd:
            self.d_update.setText(f"Update available: {upd}")
            self.update_btn.setText("Update" if kind == "flatpak" or self._is_aur(key) else "Update system…")
            self.update_btn.show()
        else:
            self.d_update.setText("")
            self.update_btn.hide()
        self.remove_btn.show()

    def _is_aur(self, name):
        p = self.pkgs.get(name)
        return p is not None and p.source == "aur"

    # ---- actions ----------------------------------------------------------------

    def update_current(self):
        if not self.current:
            return
        kind, key = self.current
        if kind == "flatpak":
            steps = [Step(f"Updating {key}", flatpak.update_cmd(key))]
        elif self._is_aur(key):
            if not aur.helper_available():
                return warn(self, "yay is missing", "Updating AUR packages needs yay.")
            steps = [Step(f"Updating {key} from the AUR", aur.update_cmd([key]), terminal=f"yay -S {key}")]
        else:
            info(self, "Updated together with the system",
                 "Packages from the official repositories are always updated together with the whole system.\n\n"
                 "Updating just one of them (a partial update) can break other software on Arch, "
                 "so this opens the Updates page instead.")
            return self.main.show_page("updates")
        ok, _ = run_task(self, "Update", steps)
        self.main.after_change()

    def uninstall_current(self):
        if not self.current:
            return
        kind, key = self.current
        if kind == "flatpak":
            return self._uninstall_flatpak(key)
        self._uninstall_pkgs([key])

    def _uninstall_pkgs(self, names, title=None):
        blocked = [n for n in names if n in pacman.CRITICAL]
        if blocked:
            return warn(self, "Can't remove this here",
                        f"{', '.join(blocked)} is a core part of your system (boot, desktop, drivers or "
                        "this updater). Removing it could leave the PC unusable, so ArchUpdater won't do it.")
        busy_cursor(True)
        try:
            ok, items, needed_by, msg = pacman.removal_preview(names)
        finally:
            busy_cursor(False)
        if not ok:
            if needed_by:
                return warn(self, "Other software needs it",
                            f"{', '.join(names)} can't be removed because these packages depend on it:\n\n"
                            + "\n".join("• " + n for n in needed_by)
                            + "\n\nRemove those first (or keep it).")
            return warn(self, "Can't remove", msg or "pacman refused to remove it.")
        critical_hit = [n for n, _ in items if n in pacman.CRITICAL]
        if critical_hit:
            return warn(self, "Can't remove this here",
                        "Removing it would also remove core system packages:\n\n" + "\n".join(critical_hit))
        extra = [f"{n}  {v}" for n, v in items]
        others = len(items) - len(names)
        text = (f"This removes <b>{', '.join(names)}</b>"
                + (f" and <b>{others}</b> package(s) it brought along that nothing else uses:" if others > 0 else ":"))
        if not confirm_list(self, title or "Uninstall", text, extra, ok_text="Uninstall", danger=True,
                            footer="Your own files (documents, settings in your home folder) are not deleted."):
            return
        run_task(self, "Uninstall", [Step(f"Removing {len(items)} package(s)", pacman.remove_cmd(names))])
        self.main.after_change()

    def _uninstall_flatpak(self, app_id):
        dlg = QDialog(self)
        dlg.setWindowTitle("Uninstall")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"Uninstall <b>{app_id}</b>?"))
        data = QCheckBox("Also delete its data (settings, saves, logins)")
        lay.addWidget(data)
        runtimes = QCheckBox("Remove runtimes nothing uses anymore")
        runtimes.setChecked(True)
        lay.addWidget(runtimes)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        b = bb.addButton("Uninstall", QDialogButtonBox.AcceptRole)
        b.setObjectName("danger")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        if dlg.exec() != QDialog.Accepted:
            return
        steps = [Step(f"Removing {app_id}", flatpak.uninstall_cmd(app_id, data.isChecked()))]
        if runtimes.isChecked():
            steps.append(Step("Removing unused runtimes", flatpak.cleanup_cmd(), optional=True))
        run_task(self, "Uninstall", steps)
        self.main.after_change()

    def remove_orphans(self):
        names = sorted(n for n in self.orphans if n not in pacman.CRITICAL)
        if names:
            self._uninstall_pkgs(names, title="Remove unused packages")
