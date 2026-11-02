"""Arch Linux news (warnings about manual steps before updating)."""

import datetime
import email.utils
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

FEED = "https://archlinux.org/feeds/news/"
PACMAN_LOG = "/var/log/pacman.log"


def fetch(limit=6, timeout=15):
    """Latest news items. Returns (items, error). Item: title, link, date."""
    try:
        req = urllib.request.Request(FEED, headers={"User-Agent": "archupdater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
    except Exception as e:
        return [], f"Could not load Arch news ({e.__class__.__name__})"
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        date = None
        raw = item.findtext("pubDate")
        if raw:
            try:
                date = email.utils.parsedate_to_datetime(raw)
            except Exception:
                date = None
        items.append({"title": title, "link": link, "date": date})
        if len(items) >= limit:
            break
    return items, ""


_TS_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4})\] \[PACMAN\] starting full system upgrade")


def last_upgrade(path=PACMAN_LOG):
    """Time of the last full system upgrade according to pacman.log, or None."""
    if not os.path.exists(path):
        return None
    last = None
    try:
        with open(path, errors="replace") as f:
            for line in f:
                m = _TS_RE.match(line)
                if m:
                    last = m.group(1)
    except OSError:
        return None
    if not last:
        return None
    try:
        return datetime.datetime.strptime(last, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
