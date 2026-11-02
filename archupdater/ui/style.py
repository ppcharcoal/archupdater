"""Stylesheet. Colors come from the system palette (qt6ct / KDE color scheme),
so the app follows your theme, including wallpaper-based accent colors."""

QSS = """
QMainWindow, QDialog { background: palette(window); }
QWidget#page { background: palette(window); }

QListWidget#sidebar {
    background: palette(base);
    border: none;
    padding: 10px 8px;
    outline: 0;
}
QListWidget#sidebar::item {
    padding: 10px 12px;
    margin: 2px 0;
    border-radius: 10px;
}
QListWidget#sidebar::item:hover { background: palette(alternate-base); }
QListWidget#sidebar::item:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}

QFrame#card, QFrame#banner {
    background: palette(base);
    border-radius: 14px;
}
QFrame#banner { border: 2px solid palette(highlight); }

QLabel#muted { color: palette(placeholder-text); }
QLabel#accent { color: palette(highlight); font-weight: bold; }
QLabel[state="ok"] { color: palette(text); }
QLabel[state="failed"] { color: #e5534b; font-weight: bold; }
QLabel[state="warn"] { color: #d29922; }
QLabel[state="skipped"], QLabel[state="pending"] { color: palette(placeholder-text); }
QLabel[state="running"] { color: palette(highlight); font-weight: bold; }

QLineEdit {
    padding: 8px 12px;
    border-radius: 10px;
    border: 1px solid palette(mid);
    background: palette(base);
}
QLineEdit:focus { border: 1px solid palette(highlight); }

QPushButton {
    padding: 7px 16px;
    border-radius: 9px;
    border: 1px solid palette(mid);
    background: palette(button);
}
QPushButton:hover { border: 1px solid palette(highlight); }
QPushButton:disabled { color: palette(placeholder-text); }
QPushButton#primary, QPushButton#big {
    background: palette(highlight);
    color: palette(highlighted-text);
    border: none;
    font-weight: bold;
}
QPushButton#big { padding: 14px; border-radius: 12px; font-size: 15px; }
QPushButton#primary:disabled, QPushButton#big:disabled {
    background: palette(mid);
    color: palette(placeholder-text);
}
QPushButton#danger { border: 1px solid #e5534b; }
QPushButton#danger:hover { background: #e5534b; color: white; }

QComboBox {
    padding: 7px 12px;
    border-radius: 9px;
    border: 1px solid palette(mid);
    background: palette(button);
}

QTreeWidget, QListWidget#plainlist {
    background: palette(base);
    border: none;
    border-radius: 12px;
    padding: 4px;
    outline: 0;
}
QTreeWidget::item { padding: 5px 4px; }
QTreeWidget::item:selected, QListWidget#plainlist::item:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}
QHeaderView::section {
    background: palette(base);
    border: none;
    padding: 6px 4px;
    font-weight: bold;
}
QPlainTextEdit#log {
    background: palette(base);
    border: none;
    border-radius: 10px;
    padding: 6px;
}
QProgressBar { border: none; border-radius: 3px; background: palette(mid); }
QProgressBar::chunk { border-radius: 3px; background: palette(highlight); }
QSplitter::handle { background: transparent; width: 10px; }
"""
