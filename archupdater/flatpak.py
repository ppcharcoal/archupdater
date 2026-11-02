"""Flatpak apps: list, updates, Flathub search, install/remove."""

import glob
import os

from .util import HOME, have, parse_size, run


def available():
    return have("flatpak")


def _rows(text, ncols):
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < ncols:
            parts += [""] * (ncols - len(parts))
        rows.append([p.strip() for p in parts[:ncols]])
    return rows


def installed_apps():
    """Installed Flatpak apps as a list of dicts."""
    if not available():
        return []
    code, out, _ = run(["flatpak", "list", "--app",
                        "--columns=application,name,version,size,origin,installation"])
    if code != 0:
        return []
    apps = []
    for app_id, name, version, size, origin, inst in _rows(out, 6):
        apps.append({"id": app_id, "name": name or app_id, "version": version,
                     "size": parse_size(size), "origin": origin, "installation": inst})
    return apps


def installed_ids():
    return {a["id"] for a in installed_apps()}


def updates():
    """Pending Flatpak updates (apps and runtimes). Returns (updates, error)."""
    if not available():
        return [], ""
    code, out, err = run(["flatpak", "remote-ls", "--updates", "--columns=application,version,name"],
                         timeout=120)
    if code != 0:
        return [], (err.strip() or "Flatpak update check failed")
    return [{"id": a, "version": v, "name": n or a} for a, v, n in _rows(out, 3)], ""


def search(query):
    """Search Flathub (uses Flatpak's local copy of the Flathub catalog)."""
    if not available() or len(query.strip()) < 2:
        return []
    code, out, _ = run(["flatpak", "search",
                        "--columns=application,name,description,version,remotes", query], timeout=60)
    if code != 0 or out.strip().startswith("No matches"):
        return []
    results = []
    for app_id, name, desc, version, remotes in _rows(out, 5):
        if "flathub" not in remotes.lower():
            continue
        results.append({"id": app_id, "name": name or app_id, "description": desc, "version": version})
    return results


def icon_path(app_id):
    """A local icon file for a Flathub app id, if Flatpak has one cached."""
    patterns = [
        f"/var/lib/flatpak/appstream/flathub/*/active/icons/128x128/{app_id}.png",
        f"{HOME}/.local/share/flatpak/appstream/flathub/*/active/icons/128x128/{app_id}.png",
        f"/var/lib/flatpak/exports/share/icons/hicolor/*/apps/{app_id}.png",
        f"/var/lib/flatpak/exports/share/icons/hicolor/scalable/apps/{app_id}.svg",
    ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            if os.path.exists(path):
                return path
    return ""


# ---- commands ----------------------------------------------------------------

def install_cmd(app_id):
    return ["flatpak", "install", "-y", "--noninteractive", "flathub", app_id]


def uninstall_cmd(app_id, delete_data=False):
    cmd = ["flatpak", "uninstall", "-y", "--noninteractive"]
    if delete_data:
        cmd.append("--delete-data")
    return cmd + [app_id]


def cleanup_cmd():
    return ["flatpak", "uninstall", "--unused", "-y", "--noninteractive"]


def update_cmd(app_id=None):
    cmd = ["flatpak", "update", "-y", "--noninteractive"]
    return cmd + [app_id] if app_id else cmd
