"""Timeshift snapshots: list, create, delete, restore."""

import datetime
import glob
import json
import os
import re
from dataclasses import dataclass

from .util import have, root_cmd, run

CONFIG = "/etc/timeshift/timeshift.json"
AUTOSNAP_CONF = "/etc/timeshift-autosnap.conf"


@dataclass
class Snapshot:
    name: str          # e.g. 2026-10-16_20-26-01
    created: str = ""  # human readable
    comment: str = ""
    tags: str = ""


def available():
    return have("timeshift")


def autosnap_installed():
    return os.path.exists("/usr/bin/timeshift-autosnap") or os.path.exists(AUTOSNAP_CONF)


def autosnap_keep():
    try:
        with open(AUTOSNAP_CONF) as f:
            for line in f:
                m = re.match(r"^\s*maxSnapshots\s*=\s*(\d+)", line)
                if m:
                    return int(m.group(1))
    except OSError:
        pass
    return None


def _config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except Exception:
        return {}


def mode():
    cfg = _config()
    if not cfg:
        return ""
    return "btrfs" if str(cfg.get("btrfs_mode", "false")).lower() == "true" else "rsync"


def _pretty_name(name):
    try:
        dt = datetime.datetime.strptime(name, "%Y-%m-%d_%H-%M-%S")
        return dt.strftime("%a %d %b %Y, %H:%M")
    except ValueError:
        return name


def list_readonly():
    """List rsync snapshots straight from the backup disk (no password needed).

    Returns a list, or None when that isn't possible (btrfs mode, disk not
    mounted, or no permission) - then the caller can ask for a password.
    """
    cfg = _config()
    if not cfg or mode() != "rsync":
        return None
    uuid = cfg.get("backup_device_uuid", "")
    if not uuid:
        return None
    code, out, _ = run(["findmnt", "-rno", "TARGET", "-S", f"UUID={uuid}"])
    targets = out.split() if code == 0 else []
    for target in targets:
        base = os.path.join(target, "timeshift", "snapshots")
        if not os.path.isdir(base) or not os.access(base, os.R_OK | os.X_OK):
            continue
        snaps = []
        for info in sorted(glob.glob(os.path.join(base, "*", "info.json")), reverse=True):
            name = os.path.basename(os.path.dirname(info))
            comment, tags = "", ""
            try:
                with open(info) as f:
                    data = json.load(f)
                comment = data.get("comments", "")
                tags = data.get("tags", "")
            except Exception:
                pass
            snaps.append(Snapshot(name=name, created=_pretty_name(name), comment=comment, tags=tags))
        return snaps
    return None


def parse_list(text):
    """Parse `timeshift --list` output."""
    snaps = []
    for line in text.splitlines():
        m = re.match(r"^\s*\d+\s+>\s+(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(2)
        tm = re.match(r"^([ODWMHB](?:\s?[ODWMHB])*)?\s*(.*)$", rest)
        tags = (tm.group(1) or "").strip() if tm else ""
        comment = (tm.group(2) if tm else rest).strip()
        snaps.append(Snapshot(name=m.group(1), created=_pretty_name(m.group(1)), comment=comment, tags=tags))
    snaps.sort(key=lambda s: s.name, reverse=True)
    return snaps


TAG_NAMES = {"O": "manual", "B": "boot", "H": "hourly", "D": "daily", "W": "weekly", "M": "monthly"}


def describe_tags(tags):
    names = [TAG_NAMES.get(t, t) for t in tags.split() if t]
    return ", ".join(names)


# ---- commands ----------------------------------------------------------------

def list_cmd():
    return root_cmd("timeshift", "--list")


def create_cmd(comment):
    return root_cmd("timeshift", "--create", "--comments", comment or "ArchUpdater", "--tags", "O")


def delete_cmd(name):
    return root_cmd("timeshift", "--delete", "--snapshot", name)


def restore_cmd(name):
    # systemd-boot systems have no GRUB to reinstall, so skip that step.
    skip_grub = [] if os.path.exists("/boot/grub/grub.cfg") else ["--skip-grub"]
    return root_cmd("timeshift", "--restore", "--snapshot", name, *skip_grub, "--yes")
