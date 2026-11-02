"""Shared UI helpers: background calls, icons, small widgets, dialogs."""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QLabel, QListWidget,
                               QMessageBox, QStyle, QVBoxLayout, QWidget, QApplication)


class _Relay(QObject):
    done = Signal(object, object)


_alive = set()


def run_async(fn, callback, *args):
    """Run fn(*args) in a thread and call callback(result, error) on the UI thread."""
    relay = _Relay()
    _alive.add(relay)

    def finished(result, error):
        _alive.discard(relay)
        callback(result, error)

    relay.done.connect(finished, Qt.QueuedConnection)

    def work():
        try:
            relay.done.emit(fn(*args), None)
        except Exception as e:  # surfaced to the callback, never crashes the app
            relay.done.emit(None, e)

    threading.Thread(target=work, daemon=True).start()


_FALLBACK = {
    "view-refresh": QStyle.SP_BrowserReload,
    "edit-delete": QStyle.SP_TrashIcon,
    "dialog-warning": QStyle.SP_MessageBoxWarning,
    "dialog-information": QStyle.SP_MessageBoxInformation,
    "document-save": QStyle.SP_DialogSaveButton,
    "go-down": QStyle.SP_ArrowDown,
    "media-playback-start": QStyle.SP_MediaPlay,
}


def icon(name, fallback="application-x-executable"):
    """Theme icon by name (file paths work too), with sensible fallbacks."""
    if name and name.startswith("/"):
        ic = QIcon(name)
        if not ic.isNull():
            return ic
    if name:
        ic = QIcon.fromTheme(name)
        if not ic.isNull():
            return ic
    ic = QIcon.fromTheme(fallback)
    if not ic.isNull():
        return ic
    sp = _FALLBACK.get(name, QStyle.SP_FileIcon)
    return QApplication.style().standardIcon(sp)


def pixmap(name, size=48, fallback="package-x-generic"):
    return icon(name, fallback).pixmap(size, size)


def card():
    f = QFrame()
    f.setObjectName("card")
    return f


def title_label(text, size=18):
    lbl = QLabel(text)
    lbl.setObjectName("title")
    f = lbl.font()
    f.setPointSize(size)
    f.setBold(True)
    lbl.setFont(f)
    lbl.setWordWrap(True)
    return lbl


def muted_label(text=""):
    lbl = QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


def info(parent, title, text):
    QMessageBox.information(parent, title, text)


def warn(parent, title, text):
    QMessageBox.warning(parent, title, text)


def confirm_list(parent, title, text, items, ok_text="Continue", danger=False, footer=""):
    """Confirmation dialog with a scrollable list. Returns True if accepted."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(460)
    lay = QVBoxLayout(dlg)
    msg = QLabel(text)
    msg.setWordWrap(True)
    lay.addWidget(msg)
    if items:
        lst = QListWidget()
        lst.addItems(items)
        lst.setMaximumHeight(min(260, 26 * len(items) + 12))
        lay.addWidget(lst)
    if footer:
        f = muted_label(footer)
        lay.addWidget(f)
    buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
    ok = buttons.addButton(ok_text, QDialogButtonBox.AcceptRole)
    ok.setObjectName("danger" if danger else "primary")
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    lay.addWidget(buttons)
    return dlg.exec() == QDialog.Accepted


def busy_cursor(on):
    if on:
        QApplication.setOverrideCursor(Qt.WaitCursor)
    else:
        QApplication.restoreOverrideCursor()


def spacer():
    w = QWidget()
    w.setSizePolicy(w.sizePolicy().horizontalPolicy(), w.sizePolicy().verticalPolicy())
    return w


__all__ = ["run_async", "icon", "pixmap", "card", "title_label", "muted_label", "info", "warn",
           "confirm_list", "busy_cursor", "QPixmap"]
