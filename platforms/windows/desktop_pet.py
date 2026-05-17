#!/usr/bin/env python3
"""
DeskPet for Windows 11.

Loads any .codex-pet.zip from ~/pets/ or ~/.deskpet/pets/ and animates it in a
transparent, always-on-top desktop window.
"""

from __future__ import annotations

import ctypes, os, sys

# Locate the shared core package: prefer the installed copy, fall back to repo.
_share = os.path.expanduser("~/.local/share/deskpet")
_repo  = os.path.join(os.path.dirname(__file__), "..", "..")
for _p in (_share, _repo):
    if os.path.isdir(os.path.join(_p, "core")):
        sys.path.insert(0, os.path.abspath(_p))
        break

from pathlib import Path
from PIL import Image
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from core.bundle import list_pets as _list_pets, load_pet_pil, pet_display_name, parse_cli
from core.state import PetState
from core.constants import TILE_W, TILE_H

PETS_DIR     = Path.home() / "pets"
PETS_DIR_ALT = Path.home() / ".deskpet" / "pets"
TICK_MS      = 16

ES_CONTINUOUS       = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002
ES_SYSTEM_REQUIRED  = 0x00000001


def list_pets() -> list[Path]:
    return [Path(p) for p in _list_pets(str(PETS_DIR), str(PETS_DIR_ALT))]


# ── Image conversion ──────────────────────────────────────────────────────────

def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    raw  = rgba.tobytes("raw", "RGBA")
    qi   = QImage(raw, rgba.width, rgba.height, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(qi)


def _load_pet(zip_path: Path, scale: float):
    name, pil_frames, anims = load_pet_pil(str(zip_path), scale)
    frames = [[_pil_to_pixmap(tile) for tile in row] for row in pil_frames]
    return name, frames, anims


# ── Screen-awake ──────────────────────────────────────────────────────────────

def set_keep_awake(enabled: bool) -> None:
    flags = ES_CONTINUOUS
    if enabled:
        flags |= ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


# ── Autostart (Startup folder) ────────────────────────────────────────────────

def _startup_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base    = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "DeskPet.bat"


def autostart_enabled() -> bool:
    return _startup_path().is_file()


def write_autostart(zip_path: Path, scale: float) -> None:
    startup = _startup_path()
    startup.parent.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    python = Path(sys.executable).resolve()
    startup.write_text(
        "@echo off\r\n"
        f'start "" "{python}" "{script}" "{zip_path.resolve()}" --scale {scale}\r\n',
        encoding="utf-8",
    )


def remove_autostart() -> None:
    try:
        _startup_path().unlink()
    except FileNotFoundError:
        pass


# ── Widget ────────────────────────────────────────────────────────────────────

class DesktopPet(QWidget):

    def __init__(self, zip_path: Path, scale: float = 0.5):
        super().__init__()
        self._scale        = scale
        self._zip_path     = zip_path
        self._keep_awake   = False
        self._dragging     = False
        self._drag_started = False
        self._drag_mouse   = QPoint()
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0

        tw, th = int(TILE_W * scale), int(TILE_H * scale)
        self._name, self._frames, self._anims = _load_pet(zip_path, scale)

        screen = QApplication.primaryScreen().availableGeometry()
        self._ps = PetState(
            sx=screen.x(), sy=screen.y(),
            sw=screen.width(), sh=screen.height(),
            tw=tw, th=th,
        )

        self.setFixedSize(tw, th)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.Tool | Qt.NoDropShadowWindowHint
        )
        self.move(int(self._ps.x), int(self._ps.y))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    def paintEvent(self, _event):
        from PySide6.QtGui import QPainter
        ps      = self._ps
        row     = self._anims[ps.anim][0]
        pixmap  = self._frames[row][ps.fidx]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, ps.tw, ps.th, pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging     = True
            self._drag_started = False
            self._drag_mouse   = event.globalPosition().toPoint()
            self._drag_start_x = float(self._ps.x)
            self._drag_start_y = float(self._ps.y)
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        if not self._drag_started:
            self._drag_started = True
            self._ps.on_drag_start()
        delta = event.globalPosition().toPoint() - self._drag_mouse
        self._ps.on_drag(self._drag_start_x + delta.x(), self._drag_start_y + delta.y())
        self.move(int(self._ps.x), int(self._ps.y))
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._ps.on_release()
            event.accept()

    def closeEvent(self, event):
        set_keep_awake(False)
        super().closeEvent(event)

    def _show_menu(self, global_pos: QPoint) -> None:
        menu      = QMenu(self)
        pet_group = QActionGroup(menu)
        pet_group.setExclusive(True)
        for path in list_pets():
            action = QAction(pet_display_name(str(path)), menu)
            action.setCheckable(True)
            action.setChecked(path == self._zip_path)
            action.triggered.connect(lambda _checked=False, p=path: self._switch_pet(p))
            pet_group.addAction(action)
            menu.addAction(action)

        menu.addSeparator()

        movement = QAction("Enable movement", menu)
        movement.setCheckable(True)
        movement.setChecked(self._ps.moving)
        movement.triggered.connect(lambda checked: self._ps.set_moving(checked))
        menu.addAction(movement)

        startup = QAction("Run on startup", menu)
        startup.setCheckable(True)
        startup.setChecked(autostart_enabled())
        startup.triggered.connect(self._toggle_autostart)
        menu.addAction(startup)

        awake = QAction("Keep screen awake", menu)
        awake.setCheckable(True)
        awake.setChecked(self._keep_awake)
        awake.triggered.connect(self._apply_keep_awake)
        menu.addAction(awake)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        menu.exec(global_pos)

    def _switch_pet(self, zip_path: Path) -> None:
        self._zip_path = zip_path
        self._name, self._frames, self._anims = _load_pet(zip_path, self._scale)
        self._ps.enter("idle")
        self.update()

    def _toggle_autostart(self, enabled: bool) -> None:
        if enabled:
            write_autostart(self._zip_path, self._scale)
        else:
            remove_autostart()

    def _apply_keep_awake(self, enabled: bool) -> None:
        self._keep_awake = enabled
        set_keep_awake(enabled)

    def _tick(self) -> None:
        position_changed = self._ps.tick(TICK_MS / 1000.0, self._anims)
        if position_changed:
            self.move(int(self._ps.x), int(self._ps.y))
        self.update()


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    zip_str, scale = parse_cli(argv or sys.argv[1:])

    PETS_DIR.mkdir(parents=True, exist_ok=True)
    PETS_DIR_ALT.mkdir(parents=True, exist_ok=True)

    if zip_str:
        zip_path = Path(zip_str).expanduser().resolve()
        if not zip_path.exists():
            print(f"File not found: {zip_path}", file=sys.stderr)
            return 1
    else:
        pets = list_pets()
        if not pets:
            print(
                f"No .codex-pet.zip files found in {PETS_DIR}. "
                "Drop .codex-pet.zip pet bundles into ~/pets/.",
                file=sys.stderr,
            )
            return 1
        zip_path = pets[0]

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)
    pet = DesktopPet(zip_path, scale)
    pet.show()
    pet.raise_()
    pet.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
