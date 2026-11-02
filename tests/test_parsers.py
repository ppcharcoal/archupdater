import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from archupdater import flatpak, news, pacman, timeshift, util  # noqa: E402

QI = """Name            : firefox
Version         : 158.0-1
Description     : Fast, Private & Safe Web Browser
Architecture    : x86_64
Required By     : None
Installed Size  : 260.45 MiB
Install Date    : Fri 16 Oct 2026 18:30:01 CEST
Install Reason  : Explicitly installed

Name            : glib2
Version         : 2.86.0-1
Description     : Low level core library
Required By     : at-spi2-core  dconf  firefox  gtk3
                  gtk4  libnotify
Installed Size  : 18.20 MiB
Install Reason  : Installed as a dependency for another package
"""

SS = """extra/firefox 158.0-1 [installed]
    Fast, Private & Safe Web Browser
extra/firefox-i18n-pl 158.0-1
    Polish language pack for Firefox
core/gcc 15.2.1-1 (base-devel) [installed: 15.2.0-1]
    The GNU Compiler Collection
"""

TS_LIST = """Device : /dev/sda1
UUID   : ad2a06f2-8a3e-4872-a38a-be0d3315daed
Path   : /run/timeshift/12345/backup
Mode   : RSYNC
Status : OK
3 snapshots, 870.1 GB free

Num     Name                 Tags  Description
------------------------------------------------------------------------------
0    >  2026-10-16_20-26-01  O     Clean working setup
1    >  2026-10-21_16-10-22  O     {timeshift-autosnap} {created before upgrade}
2    >  2026-10-30_09-30-00  O D
"""

PACLOG = """[2026-10-20T10:00:00+0200] [PACMAN] Running 'pacman -Syu'
[2026-10-20T10:00:00+0200] [PACMAN] starting full system upgrade
[2026-10-30T09:12:33+0100] [PACMAN] starting full system upgrade
[2026-10-30T09:15:00+0100] [ALPM] upgraded firefox (157.0-1 -> 158.0-1)
"""


class Parsers(unittest.TestCase):
    def test_qi(self):
        pkgs = pacman.parse_qi(QI)
        self.assertEqual(len(pkgs), 2)
        self.assertEqual(pkgs[0]["Name"], "firefox")
        self.assertTrue(pkgs[0]["Install Reason"].startswith("Explicitly"))
        self.assertEqual(util.parse_size(pkgs[0]["Installed Size"]), int(260.45 * 1024 ** 2))
        self.assertIn("libnotify", pacman._words(pkgs[1]["Required By"]))
        self.assertEqual(pacman._words(pkgs[0]["Required By"]), [])

    def test_search(self):
        r = pacman.parse_search(SS)
        self.assertEqual([x["name"] for x in r], ["firefox", "firefox-i18n-pl", "gcc"])
        self.assertTrue(r[0]["installed"])
        self.assertFalse(r[1]["installed"])
        self.assertTrue(r[2]["installed"])
        self.assertEqual(r[2]["repo"], "core")
        self.assertIn("Polish", r[1]["description"])

    def test_updates(self):
        out = "linux 7.2.9.arch1-1 -> 7.2.10.arch1-1\n:: warning\nyay 13.0.1-1 -> 13.0.2-1\n"
        self.assertEqual(pacman.parse_updates(out), [("linux", "7.2.9.arch1-1", "7.2.10.arch1-1"),
                                                     ("yay", "13.0.1-1", "13.0.2-1")])

    def test_removal_error(self):
        err = ("checking dependencies...\nerror: failed to prepare transaction (could not satisfy dependencies)\n"
               ":: removing glib2 breaks dependency 'glib2' required by gtk3\n"
               ":: removing glib2 breaks dependency 'glib2>=2.80' required by firefox\n")
        self.assertEqual(pacman.parse_removal_error(err), ["firefox", "gtk3"])

    def test_timeshift_list(self):
        snaps = timeshift.parse_list(TS_LIST)
        self.assertEqual([s.name for s in snaps],
                         ["2026-10-30_09-30-00", "2026-10-21_16-10-22", "2026-10-16_20-26-01"])
        self.assertEqual(snaps[2].comment, "Clean working setup")
        self.assertEqual(snaps[2].tags, "O")
        self.assertEqual(snaps[0].tags, "O D")
        self.assertEqual(timeshift.describe_tags("O D"), "manual, daily")

    def test_last_upgrade(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(PACLOG)
        try:
            dt = news.last_upgrade(f.name)
            self.assertEqual((dt.year, dt.month, dt.day, dt.hour), (2026, 10, 30, 9))
        finally:
            os.unlink(f.name)

    def test_flatpak_rows(self):
        rows = flatpak._rows("org.gimp.GIMP\tGIMP\t3.0\t300 MB\tflathub\tsystem\n\n", 6)
        self.assertEqual(rows[0][:2], ["org.gimp.GIMP", "GIMP"])
        self.assertEqual(util.parse_size(rows[0][3]), 300 * 1000 ** 2)

    def test_sizes(self):
        self.assertEqual(util.human_size(0), "")
        self.assertEqual(util.human_size(2048), "2.0 KB")
        self.assertEqual(util.parse_size("1,5 GiB"), int(1.5 * 1024 ** 3))

    def test_root_cmd_uses_helper(self):
        cmd = pacman.install_cmd(["foo"])
        self.assertEqual(cmd[0], "pkexec")
        self.assertTrue(cmd[1].endswith("archupdater-root"))
        self.assertEqual(cmd[2:], ["pacman", "-S", "--needed", "--noconfirm", "foo"])


if __name__ == "__main__":
    unittest.main()
