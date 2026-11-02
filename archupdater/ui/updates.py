"""Updates: check, read Arch news, run the full safe system update."""

import datetime
import subprocess

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSizePolicy, QSplitter,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import aur, flatpak, news, pacman, system, timeshift
from ..util import have, save_settings
from .common import card, icon, muted_label, run_async, title_label, warn
from .tasks import Step, run_task


def check_all():
    repo, repo_err = pacman.repo_updates()
    aur_ups, aur_err = aur.updates()
    fp, fp_err = flatpak.updates()
    errors = [e for e in (repo_err, aur_err, fp_err) if e]
    return repo, aur_ups, fp, errors


class UpdatesPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.settings = main.settings
        self.news_items = []
        self.checking = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(title_label("Updates", 20))
        head.addStretch(1)
        self.check_btn = QPushButton(icon("view-refresh"), "Check for updates")
        self.check_btn.clicked.connect(self.check)
        head.addWidget(self.check_btn)
        lay.addLayout(head)
        self.summary = muted_label("")
        lay.addWidget(self.summary)

        self.reboot_card = card()
        self.reboot_card.setObjectName("banner")
        rl = QHBoxLayout(self.reboot_card)
        self.reboot_text = QLabel()
        self.reboot_text.setWordWrap(True)
        rl.addWidget(self.reboot_text, 1)
        rb = QPushButton(icon("system-reboot"), "Reboot now")
        rb.setObjectName("primary")
        rb.clicked.connect(self.reboot)
        rl.addWidget(rb)
        self.reboot_card.hide()
        lay.addWidget(self.reboot_card)

        split = QSplitter(Qt.Horizontal)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Installed", "New", "Source"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        ll.addWidget(self.tree, 1)
        sel = QHBoxLayout()
        self.sel_note = muted_label("Official packages are always updated together with the system.")
        sel.addWidget(self.sel_note, 1)
        self.sel_btn = QPushButton("Update selected")
        self.sel_btn.setEnabled(False)
        self.sel_btn.clicked.connect(self.update_selected)
        sel.addWidget(self.sel_btn)
        ll.addLayout(sel)
        split.addWidget(left)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)

        news_card = card()
        nl = QVBoxLayout(news_card)
        nl.setContentsMargins(14, 12, 14, 12)
        nl.addWidget(title_label("Arch news", 13))
        self.news_note = muted_label("Loading…")
        nl.addWidget(self.news_note)
        self.news_list = QListWidget()
        self.news_list.setObjectName("plainlist")
        self.news_list.itemActivated.connect(self._open_news)
        self.news_list.itemClicked.connect(self._open_news)
        self.news_list.setMaximumHeight(120)
        nl.addWidget(self.news_list)
        news_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        rlay.addWidget(news_card)

        opts = card()
        ol = QGridLayout(opts)
        ol.setContentsMargins(14, 12, 14, 12)
        ol.addWidget(title_label("When updating", 13), 0, 0, 1, 2)
        self.opt = {}
        rows = [
            ("backup_configs", "Back up my configs first"),
            ("refresh_mirrors", "Refresh mirrors if they're over a day old"),
            ("snapshot_before_update", self._snapshot_label()),
            ("update_flatpak", "Update Flatpak apps"),
            ("remove_orphans", "Remove packages nothing uses anymore"),
            ("clean_cache", "Delete old downloaded package files"),
            ("check_hyprland", "Check the Hyprland config afterwards"),
        ]
        for i, (key, text) in enumerate(rows, start=1):
            cb = QCheckBox(text)
            cb.setChecked(bool(self.settings.get(key)))
            cb.toggled.connect(lambda v, k=key: self._set(k, v))
            self.opt[key] = cb
            ol.addWidget(cb, i, 0, 1, 2)
        if not system.reflector_available():
            self.opt["refresh_mirrors"].setEnabled(False)
            self.opt["refresh_mirrors"].setToolTip("reflector is not set up")
        if not flatpak.available():
            self.opt["update_flatpak"].setEnabled(False)
        if not have("Hyprland"):
            self.opt["check_hyprland"].setEnabled(False)
        if not have("paccache"):
            self.opt["clean_cache"].setEnabled(False)
        self.backup_lbl = muted_label("")
        ol.addWidget(self.backup_lbl, len(rows) + 1, 0)
        ch = QPushButton("Change…")
        ch.clicked.connect(self._choose_backup_dir)
        ol.addWidget(ch, len(rows) + 1, 1, Qt.AlignRight)
        ol.setColumnStretch(0, 1)
        self._update_backup_label()
        opts.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        rlay.addWidget(opts)
        rlay.addStretch(1)

        self.go_btn = QPushButton(icon("system-software-update"), "  Update everything")
        self.go_btn.setObjectName("big")
        self.go_btn.clicked.connect(self.update_everything)
        rlay.addWidget(self.go_btn)
        split.addWidget(right)
        split.setSizes([560, 440])
        lay.addWidget(split, 1)

        self._last = news.last_upgrade()
        self._show_last()
        run_async(news.fetch, self._news_loaded)
        self._show_reboot(system.reboot_reasons())

    # ---- settings ---------------------------------------------------------------

    def _snapshot_label(self):
        if not timeshift.available():
            return "Create a Timeshift snapshot first (Timeshift not installed)"
        if timeshift.autosnap_installed():
            keep = timeshift.autosnap_keep()
            extra = f", keeps the last {keep}" if keep else ""
            return f"Timeshift snapshot (taken automatically by timeshift-autosnap{extra})"
        return "Create a Timeshift snapshot first"

    def _set(self, key, value):
        self.settings[key] = value
        save_settings(self.settings)

    def _update_backup_label(self):
        self.backup_lbl.setText(f"Config backups go to: {system.backup_dir(self.settings)}")

    def _choose_backup_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Folder for config backups", system.backup_dir(self.settings))
        if d:
            self._set("backup_dir", d)
            self._update_backup_label()

    # ---- news ---------------------------------------------------------------------

    def _show_last(self):
        if self._last:
            days = (datetime.datetime.now(datetime.timezone.utc) - self._last).days
            when = "today" if days == 0 else ("yesterday" if days == 1 else f"{days} days ago")
            self.last_text = f"Last full update: {when} ({self._last:%d %b %Y, %H:%M})."
        else:
            self.last_text = "No full update recorded yet."
        self.summary.setText(self.last_text)

    def _news_loaded(self, result, error):
        items, err = result if result else ([], str(error))
        self.news_items = items
        self.news_list.clear()
        if err:
            self.news_note.setText(err)
            return
        new = self.new_news()
        self.news_note.setText(f"{len(new)} new since your last update - read before updating."
                               if new else "Nothing new since your last update.")
        for it in items:
            date = it["date"].strftime("%d %b %Y") if it["date"] else ""
            fresh = it in new
            li = QListWidgetItem(("●  " if fresh else "    ") + f"{date}   {it['title']}")
            li.setData(Qt.UserRole, it["link"])
            li.setToolTip("Click to open in your browser")
            if fresh:
                f = li.font()
                f.setBold(True)
                li.setFont(f)
            self.news_list.addItem(li)

    def new_news(self):
        if not self._last:
            return []
        return [n for n in self.news_items if n["date"] and n["date"] > self._last]

    def _open_news(self, item):
        link = item.data(Qt.UserRole)
        if link:
            QDesktopServices.openUrl(QUrl(link))

    # ---- checking -------------------------------------------------------------------

    def check(self):
        if self.checking:
            return
        self.checking = True
        self.check_btn.setEnabled(False)
        self.summary.setText("Checking for updates…")
        run_async(check_all, self._checked)

    def _checked(self, result, error):
        self.checking = False
        self.check_btn.setEnabled(True)
        if error or result is None:
            self.summary.setText(f"Check failed: {error}")
            return
        repo, aur_ups, fp, errors = result
        self.tree.clear()
        updates = {}
        for name, old, new in repo:
            self._add_row(name, old, new, "Official", ("pkg", name))
            updates[("pkg", name)] = new
        for name, old, new in aur_ups:
            self._add_row(name, old, new, "AUR", ("pkg", name))
            updates[("pkg", name)] = new
        for f in fp:
            self._add_row(f["name"], "", f["version"], "Flatpak", ("flatpak", f["id"]))
            updates[("flatpak", f["id"])] = f["version"] or "new version"
        self.main.set_updates(updates)
        total = len(updates)
        text = f"{total} update{'s' if total != 1 else ''} available." if total else "Everything is up to date."
        text += "  " + self.last_text
        if errors:
            text += "\n⚠ " + " · ".join(errors)
        self.summary.setText(text)

    def _add_row(self, name, old, new, source, ref):
        it = QTreeWidgetItem([name, old, new, source])
        it.setData(0, Qt.UserRole, ref)
        it.setData(1, Qt.UserRole, source)
        self.tree.addTopLevelItem(it)

    def _selection_changed(self):
        items = self.tree.selectedItems()
        ok = bool(items) and all(i.data(1, Qt.UserRole) in ("AUR", "Flatpak") for i in items)
        self.sel_btn.setEnabled(ok)

    def update_selected(self):
        items = self.tree.selectedItems()
        aur_names = [i.data(0, Qt.UserRole)[1] for i in items if i.data(1, Qt.UserRole) == "AUR"]
        fp_ids = [i.data(0, Qt.UserRole)[1] for i in items if i.data(1, Qt.UserRole) == "Flatpak"]
        steps = []
        if aur_names:
            steps.append(Step(f"Updating {len(aur_names)} AUR package(s)", aur.update_cmd(aur_names),
                              terminal="yay -S " + " ".join(aur_names)))
        for fid in fp_ids:
            steps.append(Step(f"Updating {fid}", flatpak.update_cmd(fid)))
        if steps:
            run_task(self, "Update selected", steps)
            self.main.after_change()

    # ---- the full update ---------------------------------------------------------------

    def _build_steps(self):
        s = self.settings
        steps = []
        steps.append(Step("Back up your configs", func=lambda log: system.backup_configs(s, log), optional=True,
                          skip="" if s.get("backup_configs") else "turned off"))

        age = system.mirrors_age_hours()
        mirror_skip = ""
        if not s.get("refresh_mirrors") or not system.reflector_available():
            mirror_skip = "turned off" if system.reflector_available() else "reflector not set up"
        elif age is not None and age < float(s.get("mirror_max_age_hours", 24)):
            mirror_skip = f"already fresh ({age:.0f} h old)"
        steps.append(Step("Refresh mirrors", system.refresh_mirrors_cmd(), optional=True, skip=mirror_skip))

        if timeshift.available() and timeshift.autosnap_installed():
            steps.append(Step("System snapshot", skip="taken automatically during the update"))
        elif timeshift.available() and s.get("snapshot_before_update"):
            steps.append(Step("Create a Timeshift snapshot", timeshift.create_cmd("Before system update")))
        else:
            steps.append(Step("System snapshot", skip="turned off" if timeshift.available() else "Timeshift not installed"))

        if aur.helper_available():
            steps.append(Step("Update packages (official + AUR)", aur.full_upgrade_cmd(), terminal="yay -Syu"))
        else:
            steps.append(Step("Update packages", pacman.full_upgrade_cmd(), terminal="sudo pacman -Syu"))

        steps.append(Step("Update Flatpak apps", flatpak.update_cmd(), optional=True,
                          skip="" if (s.get("update_flatpak") and flatpak.available()) else "turned off"))

        def orphans_cmd():
            names = [n for n in pacman.orphans() if n not in pacman.CRITICAL]
            return pacman.remove_cmd(names) if names else None
        steps.append(Step("Remove unused packages", orphans_cmd, optional=True,
                          skip="" if s.get("remove_orphans") else "turned off", skip_text="none found"))
        steps.append(Step("Delete old package files", pacman.clean_cache_cmd(), optional=True,
                          skip="" if (s.get("clean_cache") and have("paccache")) else "turned off"))

        def hypr(log):
            res = system.hyprland_check()
            if res is None:
                return True, "not installed"
            ok, msg = res
            log(msg)
            return ok, "" if ok else "problems found - see the log"
        steps.append(Step("Check the Hyprland config", func=hypr, optional=True,
                          skip="" if (s.get("check_hyprland") and have("Hyprland")) else "turned off"))
        return steps

    def update_everything(self):
        fresh = self.new_news()
        if fresh:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Read the Arch news first")
            box.setText(f"There {'is' if len(fresh) == 1 else 'are'} {len(fresh)} Arch news "
                        f"post{'s' if len(fresh) != 1 else ''} since your last update. They sometimes "
                        "describe a manual step that's needed before updating:")
            box.setInformativeText("\n".join("• " + n["title"] for n in fresh))
            open_b = box.addButton("Open the news", QMessageBox.ActionRole)
            box.addButton("Update anyway", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked == open_b:
                for n in fresh:
                    QDesktopServices.openUrl(QUrl(n["link"]))
                return
            if box.standardButton(clicked) == QMessageBox.Cancel:
                return
        ok, _ = run_task(self, "System update", self._build_steps(),
                         intro="You may be asked for your password. Keep the PC on until this finishes.")
        self._last = news.last_upgrade()
        self._show_last()
        self._news_loaded((self.news_items, ""), None)
        self._show_reboot(system.reboot_reasons())
        self.main.after_change()
        self.check()

    def _show_reboot(self, reasons):
        if reasons:
            self.reboot_text.setText("<b>Restart needed.</b> " + " ".join(reasons))
            self.reboot_card.show()
        else:
            self.reboot_card.hide()

    def reboot(self):
        if QMessageBox.question(self, "Reboot", "Restart the PC now? Save your work first.") == QMessageBox.Yes:
            subprocess.Popen(["systemctl", "reboot"])
