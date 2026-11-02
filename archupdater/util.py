"""Small helpers shared by the backend modules.

Everything here only uses the Python standard library, so the app keeps working
across Python updates. Commands that we parse are always run with LC_ALL=C so
their output format does not depend on the system language.
"""

import json
import os
import re
import shutil
import subprocess

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")), "archupdater")
DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.join(HOME, ".local", "share")), "archupdater")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Installed location of the privileged helpers (see PKGBUILD). When running from
# a git checkout, the copies next to the source are used instead.
_INSTALLED_LIB = "/usr/lib/archupdater"
_SOURCE_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "helpers")

C_ENV = dict(os.environ, LC_ALL="C", LANG="C", LANGUAGE="C")


def helper(name):
    """Absolute path of a helper script (installed copy preferred)."""
    installed = os.path.join(_INSTALLED_LIB, name)
    if os.path.exists(installed):
        return installed
    return os.path.join(_SOURCE_LIB, name)


def root_cmd(*args):
    """Command line that runs a whitelisted operation as root through polkit."""
    return ["pkexec", helper("archupdater-root"), *args]


def have(cmd):
    return shutil.which(cmd) is not None


def run(cmd, timeout=180, env=None, input_text=None):
    """Run a command and return (exit_code, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env if env is not None else C_ENV,
            input=input_text,
            errors="replace",
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: command not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]}: timed out"
    except Exception as e:  # pragma: no cover - defensive
        return 1, "", str(e)


_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4,
          "kB": 1000, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3, "TB": 1000 ** 4}


def parse_size(text):
    """'12.34 MiB' -> bytes (int). Unknown formats give 0."""
    m = re.match(r"\s*([\d.,]+)\s*([A-Za-z]+)", text or "")
    if not m:
        return 0
    try:
        value = float(m.group(1).replace(",", "."))
    except ValueError:
        return 0
    return int(value * _UNITS.get(m.group(2), 1))


def human_size(n):
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


DEFAULT_SETTINGS = {
    "backup_configs": True,
    "refresh_mirrors": True,
    "mirror_max_age_hours": 24,
    "snapshot_before_update": True,
    "update_flatpak": True,
    "remove_orphans": False,
    "clean_cache": False,
    "check_hyprland": True,
    "backup_dir": "",
    "backup_keep": 10,
    "backup_paths": [
        ".config/hypr", ".config/waybar", ".config/rofi", ".config/kitty", ".config/dunst",
        ".config/theme", ".config/qt6ct", ".config/uwsm", ".config/fastfetch",
        ".config/MangoHud", ".local/bin", ".zshrc", ".p10k.zsh", ".bashrc",
    ],
}


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
    except Exception:
        pass
    return settings


def save_settings(settings):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(settings, f, indent=2)
        os.replace(tmp, SETTINGS_FILE)
    except Exception:
        pass


def read_desktop_entry(path):
    """Return the [Desktop Entry] keys of a .desktop file as a dict."""
    entry, in_section = {}, False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line.startswith("["):
                    in_section = line == "[Desktop Entry]"
                    continue
                if in_section and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    entry.setdefault(k.strip(), v.strip())
    except OSError:
        pass
    return entry


def find_terminal():
    """A terminal emulator command that accepts '-e cmd...'."""
    candidates = [os.environ.get("TERMINAL", ""), "kitty", "konsole", "alacritty", "foot",
                  "wezterm", "gnome-terminal", "xfce4-terminal", "xterm"]
    for c in candidates:
        if c and have(c):
            return c
    return None


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def strip_ansi(text):
    return ANSI_RE.sub("", text)
