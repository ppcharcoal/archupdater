"""AppImage install / list / update / uninstall with a fake AppImage."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from archupdater import appimage  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32

# A shell script that behaves like an AppImage's --appimage-extract.
FAKE = r"""#!/bin/sh
if [ "$1" = "--appimage-extract" ]; then
  mkdir -p squashfs-root
  case "$2" in
    *.desktop) printf '[Desktop Entry]\nName=Root\nIcon=root\nComment=Chat app\nCategories=Network;\n' > squashfs-root/root.desktop ;;
    root.png) printf '\211PNG\r\n\032\n00000000' > squashfs-root/root.png ;;
  esac
  exit 0
fi
echo running
"""


class AppImageTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.orig = (appimage.HOME, appimage.APPS_DIR, appimage.DESKTOP_DIR, appimage.ICON_DIR)
        appimage.HOME = self.home
        appimage.APPS_DIR = os.path.join(self.home, "Applications")
        appimage.DESKTOP_DIR = os.path.join(self.home, ".local/share/applications")
        appimage.ICON_DIR = os.path.join(self.home, ".local/share/icons")
        os.makedirs(os.path.join(self.home, "Downloads"))
        self.src = os.path.join(self.home, "Downloads", "Root.AppImage")
        with open(self.src, "w") as f:
            f.write(FAKE)

    def tearDown(self):
        appimage.HOME, appimage.APPS_DIR, appimage.DESKTOP_DIR, appimage.ICON_DIR = self.orig
        shutil.rmtree(self.home, ignore_errors=True)

    def test_full_cycle(self):
        ok, msg = appimage.install(self.src, "", move_to_apps=True, log=lambda m: None)
        self.assertTrue(ok, msg)
        apps = appimage.installed()
        self.assertEqual(len(apps), 1)
        a = apps[0]
        self.assertEqual(a["name"], "Root")
        self.assertTrue(a["managed"])
        self.assertEqual(a["path"], os.path.join(appimage.APPS_DIR, "Root.AppImage"))
        self.assertTrue(os.access(a["path"], os.X_OK))
        self.assertTrue(a["icon"].endswith(".png") and os.path.exists(a["icon"]))
        self.assertFalse(os.path.exists(self.src))  # moved

        newer = os.path.join(self.home, "Downloads", "Root-2.AppImage")
        with open(newer, "w") as f:
            f.write(FAKE + "# v2\n")
        ok, msg = appimage.replace(a, newer, log=lambda m: None)
        self.assertTrue(ok, msg)
        a2 = appimage.installed()[0]
        self.assertTrue(a2["path"].endswith("Root-2.AppImage"))
        self.assertFalse(os.path.exists(a["path"]))

        ok, msg = appimage.uninstall(a2, delete_file=True, log=lambda m: None)
        self.assertTrue(ok, msg)
        self.assertEqual(appimage.installed(), [])
        self.assertFalse(os.path.exists(a2["icon"]))

    def test_detects_hand_made_entry(self):
        folder = os.path.join(self.home, "Root")
        os.makedirs(folder)
        path = os.path.join(folder, "Root.AppImage")
        shutil.copy(self.src, path)
        os.makedirs(appimage.DESKTOP_DIR)
        with open(os.path.join(appimage.DESKTOP_DIR, "root-app.desktop"), "w") as f:
            f.write(f"[Desktop Entry]\nType=Application\nName=Root\nExec={path} %U\nIcon=root\n")
        apps = appimage.installed()
        self.assertEqual([a["name"] for a in apps], ["Root"])
        self.assertFalse(apps[0]["managed"])
        appimage.uninstall(apps[0], delete_file=True, log=lambda m: None)
        self.assertFalse(os.path.exists(path))
        self.assertFalse(os.path.exists(folder))  # empty folder cleaned up

    def test_unlisted_file_in_applications(self):
        os.makedirs(appimage.APPS_DIR)
        shutil.copy(self.src, os.path.join(appimage.APPS_DIR, "Tool.AppImage"))
        apps = appimage.installed()
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["desktop"], "")


if __name__ == "__main__":
    unittest.main()
