"""Task runner: executes a list of steps, shows progress and a live log.

A step is either a command (run with QProcess, output streamed into the log)
or a Python function (run in a thread). Root commands go through pkexec, so
polkit shows its normal password prompt.
"""

import shlex
import subprocess
import threading

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Qt, Signal
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..util import find_terminal, strip_ansi


class Step:
    """One unit of work.

    cmd: list[str], or a callable returning list[str] / None (None = skip),
         evaluated right before the step runs.
    func: callable(log) -> bool, run in a background thread.
    skip: a reason string to show the step as skipped without running it.
    optional: failure is shown as a warning and the task continues.
    terminal: shell command offered as "Try in a terminal" if the step fails.
    """

    def __init__(self, label, cmd=None, func=None, optional=False, skip="", terminal="", skip_text=""):
        self.label = label
        self.cmd = cmd
        self.func = func
        self.optional = optional
        self.skip = skip
        self.terminal = terminal
        self.skip_text = skip_text or "Nothing to do"
        self.status = "pending"   # pending, running, ok, warn, failed, skipped
        self.note = ""


_MARK = {"pending": "○", "running": "●", "ok": "✓", "warn": "!", "failed": "✗", "skipped": "–"}


class _FuncRelay(QObject):
    line = Signal(str)
    done = Signal(bool, str)


class TaskDialog(QDialog):
    def __init__(self, parent, title, steps, intro=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 480)
        self.steps = [s for s in steps if s is not None]
        self.ok = False
        self.index = -1
        self.proc = None
        self._partial = ""
        self._failed_step = None
        self._cancelled = False
        self.results = {}

        lay = QVBoxLayout(self)
        head = QLabel(title)
        f = head.font()
        f.setPointSize(15)
        f.setBold(True)
        head.setFont(f)
        lay.addWidget(head)
        if intro:
            i = QLabel(intro)
            i.setWordWrap(True)
            i.setObjectName("muted")
            lay.addWidget(i)

        self.step_labels = []
        steps_box = QWidget()
        sl = QVBoxLayout(steps_box)
        sl.setContentsMargins(0, 4, 0, 4)
        sl.setSpacing(4)
        for s in self.steps:
            lbl = QLabel()
            lbl.setWordWrap(True)
            sl.addWidget(lbl)
            self.step_labels.append(lbl)
        lay.addWidget(steps_box)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setMaximumHeight(6)
        lay.addWidget(self.bar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(8000)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(9)
        self.log.setFont(mono)
        self.log.setObjectName("log")
        lay.addWidget(self.log, 1)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        btns = QHBoxLayout()
        self.toggle_log = QPushButton("Hide details")
        self.toggle_log.clicked.connect(self._toggle_log)
        btns.addWidget(self.toggle_log)
        btns.addStretch(1)
        self.term_btn = QPushButton("Try in a terminal")
        self.term_btn.clicked.connect(self._open_terminal)
        self.term_btn.hide()
        btns.addWidget(self.term_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        btns.addWidget(self.cancel_btn)
        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("primary")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        btns.addWidget(self.close_btn)
        lay.addLayout(btns)

        self._render_steps()

    # ---- public -------------------------------------------------------------

    def run(self):
        """Start and block until the user closes the dialog. Returns success."""
        self._next()
        self.exec()
        return self.ok

    # ---- step handling --------------------------------------------------------

    def _render_steps(self):
        for s, lbl in zip(self.steps, self.step_labels):
            text = f"<b>{_MARK[s.status]}</b>&nbsp;&nbsp;{s.label}"
            if s.note:
                text += f"<span style='opacity:0.7'> — {s.note}</span>"
            lbl.setText(text)
            lbl.setProperty("state", s.status)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _write(self, text):
        data = self._partial + strip_ansi(text)
        lines = data.split("\n")
        self._partial = lines.pop()
        if not lines:
            return
        cleaned = []
        for line in lines:
            if "\r" in line:
                parts = [p for p in line.split("\r") if p.strip()]
                line = parts[-1] if parts else ""
            cleaned.append(line)
        cur = self.log.textCursor()
        cur.movePosition(QTextCursor.End)
        cur.insertText("\n".join(cleaned) + "\n")
        self.log.setTextCursor(cur)
        self.log.ensureCursorVisible()

    def _flush(self):
        if self._partial:
            tail = self._partial.split("\r")[-1]
            self._partial = ""
            self._write(tail + "\n")

    def _next(self):
        self.index += 1
        if self._cancelled:
            return self._finish(False, "Cancelled.")
        if self.index >= len(self.steps):
            failed_optional = [s for s in self.steps if s.status == "warn"]
            msg = "Done." if not failed_optional else "Done, with warnings - see the steps marked “!”."
            return self._finish(True, msg)
        step = self.steps[self.index]
        if step.skip:
            step.status, step.note = "skipped", step.skip
            self._render_steps()
            return self._next()
        step.status = "running"
        self._render_steps()
        self._write(f"\n==> {step.label}\n")

        if step.func is not None:
            return self._run_func(step)

        cmd = step.cmd() if callable(step.cmd) else step.cmd
        if not cmd:
            step.status, step.note = "skipped", step.skip_text
            self._render_steps()
            return self._next()
        self._run_cmd(cmd)

    def _run_cmd(self, cmd):
        self._write("$ " + " ".join(shlex.quote(c) for c in cmd) + "\n")
        proc = QProcess(self)
        self.proc = proc
        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "dumb")
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: self._write(bytes(proc.readAllStandardOutput().data()).decode("utf-8", "replace")))
        proc.finished.connect(self._cmd_finished)
        proc.errorOccurred.connect(self._cmd_error)
        proc.start(cmd[0], cmd[1:])

    def _cmd_error(self, err):
        if err == QProcess.FailedToStart and self.proc is not None:
            self.proc = None
            self._write("Could not start the command (is it installed?)\n")
            self._step_done(False, "could not start")

    def _cmd_finished(self, code, exit_status):
        self._flush()
        if self.proc is None:
            return
        self.proc = None
        if exit_status != QProcess.NormalExit:
            return self._step_done(False, "stopped")
        if code == 0:
            return self._step_done(True)
        note = f"exit code {code}"
        if code == 126:
            note = "password prompt was cancelled"
        elif code == 127:
            note = "not authorized (wrong password or no polkit agent)"
        self._step_done(False, note)

    def _run_func(self, step):
        relay = _FuncRelay()
        relay.line.connect(lambda t: self._write(t + "\n"), Qt.QueuedConnection)
        relay.done.connect(lambda ok, note: self._step_done(ok, note), Qt.QueuedConnection)
        self._relay = relay

        def work():
            try:
                result = step.func(relay.line.emit)
                if isinstance(result, tuple):
                    ok, note = result
                else:
                    ok, note = bool(result), ""
            except Exception as e:
                ok, note = False, str(e)
            relay.done.emit(ok, note or "")

        threading.Thread(target=work, daemon=True).start()

    def _step_done(self, ok, note=""):
        step = self.steps[self.index]
        if ok:
            step.status = "ok"
            step.note = note
        elif step.optional:
            step.status = "warn"
            step.note = note
        else:
            step.status = "failed"
            step.note = note
            self._failed_step = step
            self._render_steps()
            return self._finish(False, f"“{step.label}” failed ({note}). Nothing after it was run.")
        self._render_steps()
        self._next()

    def _finish(self, ok, message):
        self.ok = ok
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.status.setText(message)
        self.status.setProperty("state", "ok" if ok else "failed")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.cancel_btn.setEnabled(False)
        self.close_btn.setEnabled(True)
        self.close_btn.setFocus()
        if not ok and self._failed_step is not None and self._failed_step.terminal and find_terminal():
            self.term_btn.show()

    # ---- buttons --------------------------------------------------------------

    def _toggle_log(self):
        vis = not self.log.isVisible()
        self.log.setVisible(vis)
        self.toggle_log.setText("Hide details" if vis else "Show details")

    def _open_terminal(self):
        term = find_terminal()
        cmd = self._failed_step.terminal
        script = f"{cmd}; echo; read -rp 'Press Enter to close…'"
        subprocess.Popen([term, "-e", "bash", "-c", script], start_new_session=True)

    def _cancel(self):
        if QMessageBox.question(self, "Cancel", "Stop the current operation?\n\n"
                                "Stopping pacman in the middle of installing can leave packages half-updated. "
                                "Only cancel if it is stuck.") != QMessageBox.Yes:
            return
        self._cancelled = True
        if self.proc is not None:
            self.proc.terminate()
            if not self.proc.waitForFinished(3000):
                self.proc.kill()

    def reject(self):
        # Esc / window close: only allowed when finished.
        if self.close_btn.isEnabled():
            super().reject()


def run_task(parent, title, steps, intro=""):
    """Convenience: show a TaskDialog and return (ok, dialog)."""
    dlg = TaskDialog(parent, title, steps, intro)
    ok = dlg.run()
    return ok, dlg
