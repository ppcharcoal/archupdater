"""System-level checks and steps used by the full update."""

import datetime
import glob
import os
import platform
import tarfile
import time

from .util import HOME, DATA_DIR, have, root_cmd, run

MIRRORLIST = "/etc/pacman.d/mirrorlist"


# ---- mirrors -----------------------------------------------------------------

def reflector_available():
    return have("reflector") and (
        os.path.exists("/usr/lib/systemd/system/reflector.service")
        or os.path.exists("/etc/systemd/system/reflector.service")
    )


def mirrors_age_hours():
    try:
        return (time.time() - os.path.getmtime(MIRRORLIST)) / 3600
    except OSError:
        return None


def refresh_mirrors_cmd():
    return root_cmd("mirrors")


# ---- config backups -------------------------------------------------------------

def backup_dir(settings):
    custom = settings.get("backup_dir") or ""
    if custom:
        return os.path.expanduser(custom)
    if os.path.isdir("/mnt/data") and os.access("/mnt/data", os.W_OK):
        return "/mnt/data/backups"
    return os.path.join(DATA_DIR, "backups")


def backup_configs(settings, log):
    """Pack the configured dotfiles into a .tar.gz and keep the newest N."""
    dest = backup_dir(settings)
    try:
        os.makedirs(dest, exist_ok=True)
    except OSError as e:
        log(f"Could not create {dest}: {e}")
        return False
    paths = [p for p in settings.get("backup_paths", []) if os.path.exists(os.path.join(HOME, p))]
    if not paths:
        log("Nothing to back up.")
        return True
    name = os.path.join(dest, f"config-{datetime.datetime.now():%Y-%m-%d_%H%M}.tar.gz")
    try:
        with tarfile.open(name, "w:gz") as tar:
            for p in paths:
                tar.add(os.path.join(HOME, p), arcname=p)
    except Exception as e:
        log(f"Backup failed: {e}")
        return False
    keep = max(1, int(settings.get("backup_keep", 10) or 10))
    old = sorted(glob.glob(os.path.join(dest, "config-*.tar.gz")), reverse=True)[keep:]
    for f in old:
        try:
            os.remove(f)
        except OSError:
            pass
    log(f"Saved {os.path.basename(name)} to {dest} ({len(paths)} items, keeping the newest {keep}).")
    return True


# ---- after the update ---------------------------------------------------------

def hyprland_check():
    """(ok, message) from `Hyprland --verify-config`, or None if not relevant."""
    if not have("Hyprland"):
        return None
    code, out, err = run(["Hyprland", "--verify-config"], timeout=60)
    text = (out + err).strip().splitlines()
    last = text[-1].strip() if text else ""
    if "config ok" in last.lower():
        return True, "Hyprland config is OK."
    problems = []
    capture = False
    for line in text:
        if "Config parsing result" in line:
            capture = True
            continue
        if capture and line.strip():
            problems.append(line.strip())
    return False, "\n".join(problems[-15:]) or last or "Hyprland reported a config problem."


def _pkg_version(name):
    code, out, _ = run(["pacman", "-Q", name])
    if code != 0:
        return None
    parts = out.split()
    return parts[1] if len(parts) == 2 else None


def reboot_reasons():
    """Why a reboot is needed after an update (empty list = not needed)."""
    reasons = []
    release = platform.release()
    if release and not os.path.isdir(f"/usr/lib/modules/{release}"):
        reasons.append("The kernel was updated.")
    try:
        with open("/sys/module/nvidia/version") as f:
            loaded = f.read().strip()
    except OSError:
        loaded = None
    if loaded:
        installed = _pkg_version("nvidia-utils")
        if installed and installed.split("-")[0] != loaded:
            reasons.append(f"The NVIDIA driver was updated ({loaded} → {installed.split('-')[0]}).")
    return reasons
