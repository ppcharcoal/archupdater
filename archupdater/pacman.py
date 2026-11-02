"""Installed packages, updates and search for the official repositories (pacman)."""

import os
import re
from dataclasses import dataclass, field

from .util import have, parse_size, read_desktop_entry, root_cmd, run

# Packages the app refuses to remove: removing them would leave the system
# unbootable or without a desktop. They can still be removed from a terminal.
CRITICAL = {
    "base", "base-devel", "linux", "linux-lts", "linux-zen", "linux-firmware", "linux-headers",
    "linux-lts-headers", "pacman", "pacman-contrib", "systemd", "glibc", "sudo", "bash", "filesystem",
    "mkinitcpio", "intel-ucode", "amd-ucode", "efibootmgr", "networkmanager", "wpa_supplicant",
    "hyprland", "uwsm", "sddm", "xdg-desktop-portal-hyprland", "polkit", "polkit-kde-agent",
    "nvidia", "nvidia-open", "nvidia-open-dkms", "nvidia-dkms", "nvidia-utils", "lib32-nvidia-utils",
    "pipewire", "wireplumber", "pipewire-pulse", "python", "pyside6", "archupdater", "yay",
    "flatpak", "timeshift", "timeshift-autosnap", "zram-generator", "qt6-wayland", "kitty",
}


@dataclass
class Package:
    name: str
    version: str = ""
    description: str = ""
    size: int = 0
    explicit: bool = False
    required_by: list = field(default_factory=list)
    source: str = "repo"          # "repo" or "aur" (anything not in a sync repo)
    install_date: str = ""
    app_name: str = ""            # from its .desktop file, if it is a program
    icon: str = ""
    desktop_id: str = ""


def parse_qi(text):
    """Parse `pacman -Qi` output (LC_ALL=C) into a list of dicts."""
    pkgs, cur, last_key = [], {}, None
    for line in text.splitlines():
        if not line.strip():
            if cur:
                pkgs.append(cur)
            cur, last_key = {}, None
            continue
        m = re.match(r"^([A-Za-z][A-Za-z ]*?)\s*:\s?(.*)$", line)
        if m and not line.startswith(" "):
            last_key = m.group(1).strip()
            cur[last_key] = m.group(2).strip()
        elif last_key:  # continuation line (long dependency lists wrap)
            cur[last_key] = (cur[last_key] + " " + line.strip()).strip()
    if cur:
        pkgs.append(cur)
    return pkgs


def _words(value):
    if not value or value == "None":
        return []
    return value.split()


def installed_packages():
    """All installed pacman packages as {name: Package}."""
    if not have("pacman"):
        return {}
    code, out, _ = run(["pacman", "-Qi"], timeout=120)
    if code != 0:
        return {}
    _, foreign_out, _ = run(["pacman", "-Qmq"])
    foreign = set(foreign_out.split())
    result = {}
    for d in parse_qi(out):
        name = d.get("Name")
        if not name:
            continue
        result[name] = Package(
            name=name,
            version=d.get("Version", ""),
            description=d.get("Description", ""),
            size=parse_size(d.get("Installed Size", "")),
            explicit=d.get("Install Reason", "").startswith("Explicitly"),
            required_by=_words(d.get("Required By")),
            source="aur" if name in foreign else "repo",
            install_date=d.get("Install Date", ""),
        )
    _attach_desktop_entries(result)
    return result


def _attach_desktop_entries(pkgs):
    """Mark packages that ship a visible .desktop launcher as programs."""
    code, out, _ = run(["pacman", "-Ql"], timeout=120)
    if code != 0:
        return
    for line in out.splitlines():
        if "/usr/share/applications/" not in line or not line.endswith(".desktop"):
            continue
        name, _, path = line.partition(" ")
        pkg = pkgs.get(name)
        if pkg is None or pkg.app_name:
            continue
        entry = read_desktop_entry(path)
        if not entry or entry.get("NoDisplay", "").lower() == "true" or entry.get("Type", "Application") != "Application":
            continue
        if entry.get("Hidden", "").lower() == "true":
            continue
        pkg.app_name = entry.get("Name", name)
        pkg.icon = entry.get("Icon", "")
        pkg.desktop_id = os.path.basename(path)


def orphans():
    """Packages installed as dependencies that nothing needs anymore."""
    code, out, _ = run(["pacman", "-Qdtq"])
    return out.split() if code == 0 else []


def parse_removal_error(stderr):
    """Names of packages that would break, from a failed `pacman -Rnsp`."""
    needed = set()
    for m in re.finditer(r"required by (\S+)", stderr):
        needed.add(m.group(1))
    return sorted(needed)


def removal_preview(names):
    """What `pacman -Rns names` would remove.

    Returns (ok, [(name, version)], blocking_packages, message).
    The package and its dependencies that nothing else needs are included.
    """
    code, out, err = run(["pacman", "-Rnsp", "--print-format", "%n %v", *names])
    if code != 0:
        return False, [], parse_removal_error(err), err.strip()
    items = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and not line.startswith(("::", "warning", "checking")):
            items.append((parts[0], parts[1]))
    return True, items, [], ""


def parse_updates(text):
    """'name old -> new' lines (checkupdates / yay -Qua) -> list of tuples."""
    updates = []
    for line in text.splitlines():
        m = re.match(r"^(\S+)\s+(\S+)\s+->\s+(\S+)", line.strip())
        if m:
            updates.append((m.group(1), m.group(2), m.group(3)))
    return updates


def repo_updates():
    """Pending official-repo updates, checked without touching the real database.

    Returns (updates, error_message).
    """
    if not have("checkupdates"):
        return [], "checkupdates not found (install pacman-contrib)"
    code, out, err = run(["checkupdates", "--nocolor"], timeout=240)
    if code == 2:  # no updates
        return [], ""
    if code != 0:
        return [], (err.strip() or "Could not check for updates")
    return parse_updates(out), ""


_SS_RE = re.compile(r"^(\S+)/(\S+) (\S+)(?: \(([^)]*)\))?(?: \[installed(?:: (\S+))?\])?\s*$")


def parse_search(text):
    results, cur = [], None
    for line in text.splitlines():
        if line.startswith("    ") and cur is not None:
            cur["description"] = (cur["description"] + " " + line.strip()).strip()
            continue
        m = _SS_RE.match(line)
        if m:
            cur = {"repo": m.group(1), "name": m.group(2), "version": m.group(3),
                   "installed": "[installed" in line, "description": ""}
            results.append(cur)
    return results


def search(query):
    if not have("pacman") or not query.strip():
        return []
    terms = [re.escape(t) for t in query.split()]
    code, out, _ = run(["pacman", "-Ss", *terms], timeout=60)
    return parse_search(out) if code == 0 else []


# ---- commands (run through the task runner) ---------------------------------

def install_cmd(names):
    return root_cmd("pacman", "-S", "--needed", "--noconfirm", *names)


def remove_cmd(names):
    return root_cmd("pacman", "-Rns", "--noconfirm", *names)


def full_upgrade_cmd():
    return root_cmd("pacman", "-Syu", "--noconfirm")


def clean_cache_cmd():
    return root_cmd("paccache")
