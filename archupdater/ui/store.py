"""App store: search official repos, the AUR and Flathub, install with one click."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import aur, flatpak, pacman
from .common import card, confirm_list, icon, muted_label, pixmap, run_async, title_label, warn
from .tasks import Step, run_task

# A few well-known apps shown before you search (all on Flathub).
FEATURED = [
    ("com.spotify.Client", "Spotify", "Music streaming"),
    ("com.visualstudio.code", "Visual Studio Code", "Code editor"),
    ("org.gimp.GIMP", "GIMP", "Image editor"),
    ("org.kde.krita", "Krita", "Digital painting"),
    ("org.blender.Blender", "Blender", "3D creation suite"),
    ("org.libreoffice.LibreOffice", "LibreOffice", "Office suite"),
    ("md.obsidian.Obsidian", "Obsidian", "Notes and knowledge base"),
    ("com.heroicgameslauncher.hgl", "Heroic Games Launcher", "Epic, GOG and Amazon games"),
    ("net.lutris.Lutris", "Lutris", "Game manager"),
    ("com.usebottles.bottles", "Bottles", "Run Windows software"),
    ("net.davidotek.pupgui2", "ProtonUp-Qt", "Install GE-Proton and other tools"),
    ("net.blockbench.Blockbench", "Blockbench", "Low-poly 3D model editor"),
    ("com.obsproject.Studio", "OBS Studio", "Recording and streaming"),
    ("org.qbittorrent.qBittorrent", "qBittorrent", "Torrent client"),
]

SOURCES = {"repo": "Official", "aur": "AUR", "flathub": "Flathub"}


class _Item(QTreeWidgetItem):
    def __lt__(self, other):
        return (self.data(0, Qt.UserRole + 1) or 0) < (other.data(0, Qt.UserRole + 1) or 0)


def _score(name, query, source, popularity=0.0):
    n, q = name.lower(), query.lower()
    s = 10
    if n == q:
        s = 100
    elif n.startswith(q):
        s = 60
    elif q in n:
        s = 40
    s += {"flathub": 5, "repo": 4, "aur": 0}[source]
    if source == "aur":
        s += min(popularity, 10)
    return s


class StorePage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.results = []
        self.generation = 0
        self.pending = 0
        self.current = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(12)
        lay.addWidget(title_label("Get apps", 20))

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search apps and packages (e.g. spotify, gimp, discord)…")
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.do_search)
        self.search.textChanged.connect(lambda t: self.show_featured() if not t.strip() else None)
        bar.addWidget(self.search, 1)
        go = QPushButton(icon("edit-find"), "Search")
        go.setObjectName("primary")
        go.clicked.connect(self.do_search)
        bar.addWidget(go)
        img = QPushButton(icon("list-add"), "Install AppImage…")
        img.setToolTip("Install a downloaded .AppImage file")
        img.clicked.connect(lambda: self.main.programs.install_appimage())
        bar.addWidget(img)
        lay.addLayout(bar)

        chips = QHBoxLayout()
        self.use_repo = QCheckBox("Official repos")
        self.use_aur = QCheckBox("AUR")
        self.use_flathub = QCheckBox("Flathub")
        for c in (self.use_repo, self.use_aur, self.use_flathub):
            c.setChecked(True)
            c.toggled.connect(self.render)
            chips.addWidget(c)
        chips.addSpacing(16)
        self.status = muted_label("")
        self.status.setWordWrap(False)
        chips.addWidget(self.status, 1)
        lay.addLayout(chips)

        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Source", "Version", "Description"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        self.tree.currentItemChanged.connect(self.show_details)
        self.tree.itemDoubleClicked.connect(lambda *_: self.install_current())
        split.addWidget(self.tree)

        self.details = card()
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(18, 18, 18, 18)
        top = QHBoxLayout()
        self.d_icon = QLabel()
        self.d_icon.setFixedSize(64, 64)
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
        dl.addLayout(self.d_form)
        self.d_note = muted_label("")
        dl.addWidget(self.d_note)
        dl.addStretch(1)
        btns = QHBoxLayout()
        self.web_btn = QPushButton(icon("internet-web-browser"), "Website")
        self.web_btn.clicked.connect(self.open_web)
        btns.addWidget(self.web_btn)
        btns.addStretch(1)
        self.install_btn = QPushButton(icon("system-software-install"), "Install")
        self.install_btn.setObjectName("primary")
        self.install_btn.clicked.connect(self.install_current)
        btns.addWidget(self.install_btn)
        dl.addLayout(btns)
        split.addWidget(self.details)
        split.setSizes([640, 360])
        lay.addWidget(split, 1)

        self.show_featured()

    # ---- listing ------------------------------------------------------------------

    def is_installed(self, r):
        if r["source"] == "flathub":
            return r["id"] in self.main.flatpak_ids
        return r["name"] in self.main.installed

    def show_featured(self):
        self.generation += 1
        self.results = []
        if flatpak.available():
            for app_id, name, desc in FEATURED:
                self.results.append({"source": "flathub", "id": app_id, "name": name, "description": desc,
                                     "version": "", "score": 0, "featured": True})
            self.status.setText("Popular apps - or search above")
        else:
            self.status.setText("Search above (Flatpak isn't installed, so Flathub picks are hidden)")
        self.render()

    def do_search(self):
        q = self.search.text().strip()
        if len(q) < 2:
            return self.show_featured()
        self.generation += 1
        gen = self.generation
        self.results = []
        self.render()
        self.pending = 0
        errors = []

        def add(source):
            def cb(result, error):
                if gen != self.generation:
                    return
                self.pending -= 1
                items, err = result if result else ([], str(error) if error else "")
                if err:
                    errors.append(err)
                for r in items:
                    r["source"] = source
                    r.setdefault("id", r["name"])
                    r["score"] = _score(r["name"], q, source, r.get("popularity", 0))
                    self.results.append(r)
                self.render()
                if self.pending == 0:
                    msg = f"{len(self.results)} results"
                    if errors:
                        msg += " · " + "; ".join(errors)
                    self.status.setText(msg)
            return cb

        self.pending += 1
        run_async(lambda: (pacman.search(q), ""), add("repo"))
        self.pending += 1
        run_async(lambda: aur.search(q), add("aur"))
        if flatpak.available():
            self.pending += 1
            run_async(lambda: (flatpak.search(q), ""), add("flathub"))
        self.status.setText("Searching…")

    def render(self):
        wanted = {"repo": self.use_repo.isChecked(), "aur": self.use_aur.isChecked(),
                  "flathub": self.use_flathub.isChecked()}
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        for r in self.results:
            if not wanted.get(r["source"], True):
                continue
            name = r["name"]
            it = _Item([name + ("   ✓ installed" if self.is_installed(r) else ""),
                        SOURCES[r["source"]], r.get("version", ""), r.get("description", "")])
            it.setData(0, Qt.UserRole, r)
            it.setData(0, Qt.UserRole + 1, r.get("score", 0))
            if r["source"] == "flathub":
                it.setIcon(0, icon(flatpak.icon_path(r["id"]) or r["id"], "application-x-executable"))
            else:
                it.setIcon(0, icon("package-x-generic"))
            if r.get("out_of_date"):
                it.setToolTip(0, "Marked out of date on the AUR")
            self.tree.addTopLevelItem(it)
        if any(r.get("featured") for r in self.results):
            pass  # keep featured order
        else:
            self.tree.setSortingEnabled(True)
            self.tree.sortByColumn(0, Qt.DescendingOrder)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        else:
            self._clear_details()

    # ---- details ------------------------------------------------------------------

    def _clear_details(self):
        self.current = None
        self.d_icon.clear()
        self.d_title.setText("")
        self.d_sub.setText("")
        self.d_desc.setText("")
        self.d_note.setText("")
        while self.d_form.rowCount():
            self.d_form.removeRow(0)
        self.install_btn.hide()
        self.web_btn.hide()

    def show_details(self, item, _prev=None):
        if item is None:
            return self._clear_details()
        r = item.data(0, Qt.UserRole)
        self.current = r
        while self.d_form.rowCount():
            self.d_form.removeRow(0)
        src = r["source"]
        if src == "flathub":
            self.d_icon.setPixmap(pixmap(flatpak.icon_path(r["id"]) or r["id"], 56, "application-x-executable"))
            self.d_sub.setText(f"{r['id']} · Flathub")
            self.d_note.setText("Runs sandboxed as a Flatpak and updates with the rest of your system.")
        elif src == "repo":
            self.d_icon.setPixmap(pixmap("package-x-generic", 56))
            self.d_sub.setText(f"{r.get('repo', '')} · Official Arch repositories")
            self.d_note.setText("Official package, built and checked by Arch.")
        else:
            self.d_icon.setPixmap(pixmap("package-x-generic", 56))
            self.d_sub.setText("AUR (Arch User Repository)")
            self.d_form.addRow("Votes:", QLabel(str(r.get("votes", 0))))
            self.d_form.addRow("Popularity:", QLabel(f"{r.get('popularity', 0):.2f}"))
            self.d_form.addRow("Maintainer:", QLabel(r.get("maintainer", "")))
            note = "Made by the community, not by Arch. It is built on your PC when you install it."
            if r.get("out_of_date"):
                note += "\n⚠ Marked out of date - it may not build or may be old."
            self.d_note.setText(note)
        self.d_title.setText(r["name"])
        self.d_desc.setText(r.get("description", ""))
        if r.get("version"):
            self.d_form.insertRow(0, "Version:", QLabel(r["version"]))
        installed = self.is_installed(r)
        self.install_btn.setText("Installed" if installed else "Install")
        self.install_btn.setEnabled(not installed)
        self.install_btn.show()
        self.web_btn.setVisible(True)

    def open_web(self):
        r = self.current
        if not r:
            return
        if r["source"] == "flathub":
            url = f"https://flathub.org/apps/{r['id']}"
        elif r["source"] == "aur":
            url = f"https://aur.archlinux.org/packages/{r['name']}"
        else:
            url = f"https://archlinux.org/packages/?q={r['name']}"
        QDesktopServices.openUrl(QUrl(url))

    # ---- install --------------------------------------------------------------------

    def install_current(self):
        r = self.current
        if not r or self.is_installed(r):
            return
        src, name = r["source"], r["name"]
        if src == "flathub":
            steps = [Step(f"Installing {name} from Flathub", flatpak.install_cmd(r["id"]),
                          terminal=f"flatpak install flathub {r['id']}")]
        elif src == "repo":
            steps = [Step(f"Installing {name}", pacman.install_cmd([name]),
                          terminal=f"sudo pacman -S {name}")]
        else:
            if not aur.helper_available():
                return warn(self, "yay is missing",
                            "Installing from the AUR needs yay. Install it first (see the README).")
            footer = "AUR packages are made by other users. Only install ones you trust."
            if r.get("out_of_date"):
                footer += "\nThis one is marked out of date."
            if not confirm_list(self, "Install from the AUR",
                                f"Build and install <b>{name}</b> from the AUR?", [], ok_text="Install",
                                footer=footer):
                return
            steps = [Step(f"Building and installing {name}", aur.install_cmd([name]),
                          terminal=f"yay -S {name}")]
        ok, _ = run_task(self, f"Install {name}", steps)
        self.main.after_change()

    def refresh_marks(self):
        cur = self.current
        self.render()
        if cur:
            for i in range(self.tree.topLevelItemCount()):
                it = self.tree.topLevelItem(i)
                if it.data(0, Qt.UserRole) is cur:
                    self.tree.setCurrentItem(it)
                    break
