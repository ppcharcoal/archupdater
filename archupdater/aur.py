"""AUR search (official RPC API) and AUR installs/updates through yay."""

import json
import urllib.parse
import urllib.request

from .pacman import parse_updates
from .util import have, helper, run

RPC = "https://aur.archlinux.org/rpc/v5/search/{query}?by=name-desc"


def helper_available():
    return have("yay")


def search(query, limit=60, timeout=15):
    """Search the AUR. Returns (results, error_message)."""
    q = query.strip()
    if len(q) < 2:
        return [], ""
    url = RPC.format(query=urllib.parse.quote(q))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "archupdater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:
        return [], f"AUR is unreachable right now ({e.__class__.__name__})"
    if data.get("type") == "error":
        return [], data.get("error", "AUR search failed")
    results = []
    for r in data.get("results", []):
        results.append({
            "name": r.get("Name", ""),
            "version": r.get("Version", ""),
            "description": r.get("Description") or "",
            "votes": r.get("NumVotes", 0) or 0,
            "popularity": float(r.get("Popularity", 0) or 0),
            "out_of_date": bool(r.get("OutOfDate")),
            "url": r.get("URL") or "",
            "maintainer": r.get("Maintainer") or "orphaned",
        })
    results.sort(key=lambda r: r["popularity"], reverse=True)
    return results[:limit], ""


def updates():
    """Pending AUR updates. Returns (updates, error_message)."""
    if not helper_available():
        return [], ""
    code, out, err = run(["yay", "-Qua"], timeout=120)
    ups = parse_updates(out)
    if code not in (0, 1) and not ups:
        return [], (err.strip().splitlines() or ["AUR check failed"])[-1]
    return ups, ""


def _yay(*args):
    # yay must not run as root; it asks for root (via our polkit shim) only to
    # call pacman. --noconfirm skips its interactive menus.
    return ["yay", *args, "--noconfirm", "--sudo", helper("archupdater-sudo")]


def install_cmd(names):
    return _yay("-S", "--needed", *names)


def update_cmd(names):
    return _yay("-S", *names)


def full_upgrade_cmd():
    """Repo + AUR upgrade in one go."""
    return _yay("-Syu")
