"""AppImages: install (copy + launcher entry + icon), list, update, uninstall.

An installed AppImage is a .desktop file in ~/.local/share/applications whose
Exec points at an .AppImage file. That also finds AppImages that were set up
by hand. Ones installed by ArchUpdater are marked with X-ArchUpdater-AppImage.
"""

import glob
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile

from .util import HOME, read_desktop_entry, run

APPS_DIR = os.path.join(HOME, "Applications")
DESKTOP_DIR = os.path.join(HOME, ".local", "share", "applications")
ICON_DIR = os.path.join(HOME, ".local", "share", "icons")
MARKER = "X-ArchUpdater-AppImage"


def fuse2_installed():
    """Most AppImages need libfuse2 to start."""
    for path in ("/usr/lib/libfuse.so.2", "/usr/lib64/libfuse.so.2", "/usr/lib/x86_64-linux-gnu/libfuse.so.2"):
        if os.path.exists(path):
            return True
    return bool(glob.glob("/usr/lib/libfuse.so.2*"))


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "appimage"


def _appimage_in_exec(exec_line):
    try:
        parts = shlex.split(exec_line)
    except ValueError:
        parts = exec_line.split()
    for p in parts:
        if p.lower().endswith(".appimage"):
            return os.path.expanduser(p)
    return ""


def installed():
    """Installed AppImages as a list of dicts."""
    apps, seen = [], set()
    for desktop in sorted(glob.glob(os.path.join(DESKTOP_DIR, "*.desktop"))):
        entry = read_desktop_entry(desktop)
        path = _appimage_in_exec(entry.get("Exec", ""))
        if not path:
            continue
        seen.add(os.path.realpath(path))
        apps.append(_info(path, desktop, entry))
    # AppImages sitting in ~/Applications without a launcher entry
    for path in sorted(glob.glob(os.path.join(APPS_DIR, "*.AppImage")) + glob.glob(os.path.join(APPS_DIR, "*.appimage"))):
        if os.path.realpath(path) not in seen:
            apps.append(_info(path, "", {}))
    return apps


def _info(path, desktop, entry):
    name = entry.get("Name") or os.path.basename(path).rsplit(".", 1)[0]
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    return {
        "id": desktop or path,
        "name": name,
        "path": path,
        "desktop": desktop,
        "icon": entry.get("Icon", ""),
        "exists": os.path.exists(path),
        "managed": entry.get(MARKER, "").lower() == "true",
        "size": size,
        "comment": entry.get("Comment", ""),
    }


# ---- reading an AppImage ------------------------------------------------------

def _extract(appimage, pattern, workdir):
    """Run the AppImage's own extractor for files matching pattern."""
    try:
        subprocess.run([appimage, "--appimage-extract", pattern], cwd=workdir, capture_output=True,
                       timeout=90, env=dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="0"))
    except Exception:
        pass
    return os.path.join(workdir, "squashfs-root")


def inspect(appimage):
    """Name, comment, categories and an icon file from inside an AppImage.

    Returns (info dict, temp dir to delete afterwards).
    """
    _make_executable(appimage)
    tmp = tempfile.mkdtemp(prefix="archupdater-appimage-")
    root = _extract(appimage, "*.desktop", tmp)
    entry = {}
    for d in glob.glob(os.path.join(root, "*.desktop")):
        entry = read_desktop_entry(d)
        break
    icon_name = entry.get("Icon", "")
    icon_file = ""
    candidates = []
    if icon_name:
        for ext in ("png", "svg"):
            _extract(appimage, f"{icon_name}.{ext}", tmp)
            candidates.append(os.path.join(root, f"{icon_name}.{ext}"))
    _extract(appimage, ".DirIcon", tmp)
    diricon = os.path.join(root, ".DirIcon")
    if os.path.islink(diricon):
        target = os.readlink(diricon)
        _extract(appimage, target, tmp)
        candidates.append(os.path.join(root, target))
    candidates.append(diricon)
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 0:
            icon_file = c
            break
    info = {
        "name": entry.get("Name", "") or os.path.basename(appimage).rsplit(".", 1)[0],
        "comment": entry.get("Comment", ""),
        "categories": entry.get("Categories", ""),
        "icon_file": icon_file,
        "wm_class": entry.get("StartupWMClass", ""),
    }
    return info, tmp


def _make_executable(path):
    try:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def _icon_ext(path):
    with open(path, "rb") as f:
        head = f.read(512)
    if head.startswith(b"\x89PNG"):
        return "png"
    if b"<svg" in head or head.lstrip().startswith(b"<?xml"):
        return "svg"
    return "png"


def _update_db():
    if shutil.which("update-desktop-database"):
        run(["update-desktop-database", DESKTOP_DIR], timeout=30)


# ---- install / update / uninstall -------------------------------------------------

def install(source, name, move_to_apps=True, log=print):
    """Install an AppImage. Returns (ok, message)."""
    if not os.path.isfile(source):
        return False, "File not found."
    log(f"Reading {os.path.basename(source)}…")
    info, tmp = inspect(source)
    try:
        name = (name or info["name"]).strip()
        ident = slug(name)
        if move_to_apps:
            os.makedirs(APPS_DIR, exist_ok=True)
            dest = os.path.join(APPS_DIR, os.path.basename(source))
            if os.path.realpath(dest) != os.path.realpath(source):
                log(f"Moving it to {APPS_DIR}")
                shutil.move(source, dest)
        else:
            dest = os.path.abspath(source)
        _make_executable(dest)

        icon_value = "application-x-executable"
        if info["icon_file"]:
            os.makedirs(ICON_DIR, exist_ok=True)
            icon_path = os.path.join(ICON_DIR, f"appimage-{ident}.{_icon_ext(info['icon_file'])}")
            shutil.copyfile(info["icon_file"], icon_path)
            icon_value = icon_path
            log("Icon extracted.")
        else:
            log("No icon found inside the AppImage - using a generic one.")

        os.makedirs(DESKTOP_DIR, exist_ok=True)
        desktop = os.path.join(DESKTOP_DIR, f"appimage-{ident}.desktop")
        lines = [
            "[Desktop Entry]",
            "Type=Application",
            f"Name={name}",
            f"Exec={shlex.quote(dest)} %U",
            f"Icon={icon_value}",
            "Terminal=false",
            f"{MARKER}=true",
        ]
        if info["comment"]:
            lines.append(f"Comment={info['comment']}")
        lines.append(f"Categories={info['categories'] or 'Utility;'}")
        if info["wm_class"]:
            lines.append(f"StartupWMClass={info['wm_class']}")
        with open(desktop, "w") as f:
            f.write("\n".join(lines) + "\n")
        _update_db()
        log(f"Added “{name}” to the app launcher.")
        if not fuse2_installed():
            log("Note: fuse2 isn't installed - most AppImages need it to start.")
        return True, ""
    except Exception as e:
        return False, str(e)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def replace(app, new_file, log=print):
    """Update: put a newer AppImage file in place of the old one."""
    old = app["path"]
    if not os.path.isfile(new_file):
        return False, "File not found."
    try:
        target_dir = os.path.dirname(old) or APPS_DIR
        dest = os.path.join(target_dir, os.path.basename(new_file))
        log(f"Replacing {os.path.basename(old)} with {os.path.basename(new_file)}")
        shutil.copyfile(new_file, dest + ".new")
        os.replace(dest + ".new", dest)
        _make_executable(dest)
        if os.path.realpath(dest) != os.path.realpath(old) and os.path.exists(old):
            os.remove(old)
        if app["desktop"] and os.path.realpath(dest) != os.path.realpath(old):
            with open(app["desktop"]) as f:
                text = f.read()
            text = re.sub(r"(?m)^Exec=.*$", f"Exec={shlex.quote(dest)} %U", text, count=1)
            with open(app["desktop"], "w") as f:
                f.write(text)
            _update_db()
        try:
            os.remove(new_file)
        except OSError:
            pass
        log("Done.")
        return True, ""
    except Exception as e:
        return False, str(e)


def uninstall(app, delete_file=True, log=print):
    """Remove the launcher entry, its icon and (optionally) the AppImage file."""
    try:
        if app["desktop"] and os.path.exists(app["desktop"]):
            os.remove(app["desktop"])
            log("Removed the launcher entry.")
        icon = app.get("icon", "")
        if icon.startswith(ICON_DIR) and os.path.exists(icon):
            os.remove(icon)
        if delete_file and app["path"] and os.path.exists(app["path"]):
            os.remove(app["path"])
            log(f"Deleted {app['path']}")
            folder = os.path.dirname(app["path"])
            if folder != APPS_DIR and folder.startswith(HOME + os.sep) and not os.listdir(folder):
                os.rmdir(folder)
        _update_db()
        return True, ""
    except Exception as e:
        return False, str(e)


def add_to_launcher(app, log=print):
    """Create a launcher entry for an AppImage that has none."""
    return install(app["path"], app["name"], move_to_apps=False, log=log)
