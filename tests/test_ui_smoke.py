"""Start the main window off-screen and make sure every page builds."""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 not installed")
class Smoke(unittest.TestCase):
    def test_window(self):
        from archupdater.ui.main import MainWindow
        from archupdater.ui.style import QSS
        from archupdater.ui.tasks import Step, TaskDialog

        app = QApplication.instance() or QApplication([])
        app.setStyleSheet(QSS)
        win = MainWindow()
        win.show()
        for key in ("store", "updates", "snapshots", "programs"):
            win.show_page(key)
            app.processEvents()
        # the full-update step list builds without errors
        steps = win.updates_page._build_steps()
        self.assertTrue(any("Update packages" in s.label for s in steps))
        # a task with a function step and a command step runs to completion
        dlg = TaskDialog(win, "test", [Step("func", func=lambda log: (log("hi") or True)),
                                       Step("cmd", ["true"]),
                                       Step("skip", skip="because")])
        dlg._next()
        for _ in range(200):
            app.processEvents()
            if dlg.close_btn.isEnabled():
                break
            import time
            time.sleep(0.02)
        self.assertTrue(dlg.ok, dlg.status.text())
        win.close()


if __name__ == "__main__":
    unittest.main()
