#!/usr/bin/env python3
"""
DeskPet for Windows 11.

Loads any .codex-pet.zip from ~/pets/ or ~/.deskpet/pets/ and animates it in a
transparent, always-on-top desktop window.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCursor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget


PETS_DIR = Path.home() / "pets"
PETS_DIR_ALT = Path.home() / ".deskpet" / "pets"
TILE_W, TILE_H = 192, 208
COLS, ROWS = 8, 9

ANIM_DEFS = {
    "idle": (0, 6),
    "run_right": (1, 10),
    "run_left": (2, 10),
    "waving": (3, 8),
    "jumping": (4, 10),
    "failed": (5, 3),
    "waiting": (6, 10),
    "running": (7, 6),
    "review": (8, 8),
}

WALK_SPEED = 2.0
SLEEP_AFTER = 60.0
TICK_MS = 16

ES_CONTINUOUS = 0x80000000
ES_DISPLAY_REQUIRED = 0x00000002
ES_SYSTEM_REQUIRED = 0x00000001


@dataclass(frozen=True)
class LoadedPet:
    name: str
    frames: list[list[QPixmap]]
    anims: dict[str, tuple[int, int, int]]


def list_pets() -> list[Path]:
    found: dict[str, Path] = {}
    for directory in (PETS_DIR, PETS_DIR_ALT):
        if directory.is_dir():
            for path in directory.glob("*.codex-pet.zip"):
                found.setdefault(path.name, path)
    return sorted(found.values(), key=lambda path: path.name.lower())


def pet_display_name(zip_path: Path) -> str:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            meta = json.loads(archive.read("pet.json"))
            return meta.get("displayName") or zip_path.name.replace(".codex-pet.zip", "")
    except Exception:
        return zip_path.name.replace(".codex-pet.zip", "")


def _count_frames(sheet: Image.Image, row: int) -> int:
    count = 0
    for col in range(COLS):
        tile = sheet.crop(
            (col * TILE_W, row * TILE_H, (col + 1) * TILE_W, (row + 1) * TILE_H)
        )
        if tile.getchannel("A").getextrema()[1] > 10:
            count = col + 1
        else:
            break
    return max(count, 1)


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    raw = rgba.tobytes("raw", "RGBA")
    qimage = QImage(raw, rgba.width, rgba.height, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


def load_pet(zip_path: Path, scale: float) -> LoadedPet:
    tmp = Path(tempfile.mkdtemp(prefix="deskpet-"))
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(tmp)

        meta_path = tmp / "pet.json"
        with meta_path.open("r", encoding="utf-8") as handle:
            meta = json.load(handle)

        name = meta.get("displayName") or zip_path.name
        sheet_path = tmp / meta.get("spritesheetPath", "spritesheet.webp")
        sheet = Image.open(sheet_path).convert("RGBA")
        tile_w, tile_h = int(TILE_W * scale), int(TILE_H * scale)

        row_frames = [_count_frames(sheet, row) for row in range(ROWS)]
        anims = {
            anim_name: (row, row_frames[row], fps)
            for anim_name, (row, fps) in ANIM_DEFS.items()
        }

        frames: list[list[QPixmap]] = []
        for row in range(ROWS):
            row_images: list[QPixmap] = []
            for col in range(row_frames[row]):
                tile = sheet.crop(
                    (
                        col * TILE_W,
                        row * TILE_H,
                        (col + 1) * TILE_W,
                        (row + 1) * TILE_H,
                    )
                )
                if scale != 1.0:
                    tile = tile.resize((tile_w, tile_h), Image.LANCZOS)
                row_images.append(_pil_to_pixmap(tile))
            frames.append(row_images)

        return LoadedPet(name=name, frames=frames, anims=anims)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def set_keep_awake(enabled: bool) -> None:
    flags = ES_CONTINUOUS
    if enabled:
        flags |= ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


def startup_shortcut_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "DeskPet.bat"
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "DeskPet.bat"


def autostart_enabled() -> bool:
    return startup_shortcut_path().is_file()


def write_autostart(zip_path: Path, scale: float) -> None:
    startup = startup_shortcut_path()
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
        startup_shortcut_path().unlink()
    except FileNotFoundError:
        pass


class DesktopPet(QWidget):
    def __init__(self, zip_path: Path, scale: float = 0.5):
        super().__init__()
        self._scale = scale
        self._zip_path = zip_path
        self._moving = False
        self._keep_awake = False
        self._dragging = False
        self._drag_started = False
        self._drag_mouse = QPoint()
        self._drag_pos = QPoint()

        self._tw = int(TILE_W * scale)
        self._th = int(TILE_H * scale)
        self._loaded = load_pet(zip_path, scale)

        self._anim = "idle"
        self._fidx = 0
        self._ftimer = 0.0
        self._state = "idle"
        self._stimer = random.uniform(4.0, 8.0)
        self._target_x = 0.0
        self._target_y = 0.0
        self._last_interact = time.monotonic()

        self.setFixedSize(self._tw, self._th)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
        )

        screen = QApplication.primaryScreen().availableGeometry()
        start_x = screen.x() + screen.width() - self._tw - 120
        start_y = screen.y() + screen.height() - self._th - 80
        self.move(max(screen.x(), start_x), max(screen.y(), start_y))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    def paintEvent(self, _event):
        from PySide6.QtGui import QPainter

        row = self._loaded.anims[self._anim][0]
        pixmap = self._loaded.frames[row][self._fidx]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self._tw, self._th, pixmap)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_started = False
            self._drag_mouse = event.globalPosition().toPoint()
            self._drag_pos = self.pos()
            event.accept()
        elif event.button() == Qt.RightButton:
            self._show_menu(event.globalPosition().toPoint())
            event.accept()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return

        if not self._drag_started:
            self._drag_started = True
            self._anim = "jumping"
            self._fidx = 0
            self._ftimer = 0.0

        delta = event.globalPosition().toPoint() - self._drag_mouse
        target = self._drag_pos + delta
        bounded = self._bounded_point(float(target.x()), float(target.y()))
        self.move(int(bounded.x()), int(bounded.y()))
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._last_interact = time.monotonic()
            self._enter("action")
            event.accept()

    def closeEvent(self, event):
        set_keep_awake(False)
        super().closeEvent(event)

    def _show_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)

        pet_group = QActionGroup(menu)
        pet_group.setExclusive(True)
        for path in list_pets():
            action = QAction(pet_display_name(path), menu)
            action.setCheckable(True)
            action.setChecked(path == self._zip_path)
            action.triggered.connect(lambda _checked=False, p=path: self._switch_pet(p))
            pet_group.addAction(action)
            menu.addAction(action)

        menu.addSeparator()

        movement = QAction("Enable movement", menu)
        movement.setCheckable(True)
        movement.setChecked(self._moving)
        movement.triggered.connect(lambda checked: self._apply_moving(checked))
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
        self._loaded = load_pet(zip_path, self._scale)
        self._enter("idle")
        self.update()

    def _apply_moving(self, enabled: bool) -> None:
        self._moving = enabled
        if enabled:
            self._enter("walking")
        elif self._state == "walking":
            self._enter("idle")

    def _toggle_autostart(self, enabled: bool) -> None:
        if enabled:
            write_autostart(self._zip_path, self._scale)
        else:
            remove_autostart()

    def _apply_keep_awake(self, enabled: bool) -> None:
        self._keep_awake = enabled
        set_keep_awake(enabled)

    def _enter(self, state: str) -> None:
        self._state = state
        self._fidx = 0
        self._ftimer = 0.0

        if state == "idle":
            self._anim = "idle"
            self._stimer = random.uniform(4.0, 10.0)
        elif state == "walking":
            screen = QApplication.primaryScreen().availableGeometry()
            margin = 80
            min_x = screen.x() + margin
            max_x = screen.x() + screen.width() - self._tw - margin
            min_y = screen.y() + margin
            max_y = screen.y() + screen.height() - self._th - margin
            self._target_x = random.uniform(min_x, max(min_x, max_x))
            self._target_y = random.uniform(min_y, max(min_y, max_y))
            dx = self._target_x - self.x()
            self._anim = "run_right" if dx >= 0 else "run_left"
            self._stimer = 999.0
        elif state == "sleeping":
            self._anim = "failed"
            self._stimer = random.uniform(10.0, 20.0)
        elif state == "action":
            self._anim = "waving"
            self._stimer = 2.0
        elif state == "jump":
            self._anim = "jumping"
            self._stimer = 1.5
        elif state == "special":
            self._anim = "review"
            self._stimer = 2.5

    def _pick_next(self) -> None:
        if time.monotonic() - self._last_interact > SLEEP_AFTER:
            self._enter("sleeping")
            return

        r = random.random()
        if self._moving:
            if r < 0.55:
                self._enter("walking")
            elif r < 0.90:
                self._enter("idle")
            elif r < 0.95:
                self._enter("action")
            elif r < 0.98:
                self._enter("jump")
            else:
                self._enter("special")
        else:
            if r < 0.90:
                self._enter("idle")
            elif r < 0.96:
                self._enter("action")
            elif r < 0.98:
                self._enter("jump")
            else:
                self._enter("special")

    def _tick(self) -> None:
        dt = TICK_MS / 1000.0
        _, frame_count, fps = self._loaded.anims[self._anim]
        self._ftimer += dt
        if self._ftimer >= 1.0 / fps:
            self._ftimer = 0.0
            self._fidx = (self._fidx + 1) % frame_count

        if self._dragging:
            self.update()
            return

        self._stimer -= dt
        if self._state == "walking":
            dx = self._target_x - self.x()
            dy = self._target_y - self.y()
            dist = math.hypot(dx, dy)
            if dist < WALK_SPEED * 2:
                self._enter("idle")
            else:
                expected = "run_right" if dx >= 0 else "run_left"
                if self._anim != expected:
                    self._anim = expected
                    self._fidx = 0
                    self._ftimer = 0.0
                point = self._bounded_point(
                    self.x() + dx / dist * WALK_SPEED,
                    self.y() + dy / dist * WALK_SPEED,
                )
                self.move(int(point.x()), int(point.y()))
        elif self._stimer <= 0:
            self._pick_next()

        self.update()

    def _bounded_point(self, x: float, y: float) -> QPoint:
        screen = QApplication.primaryScreen().availableGeometry()
        bounded_x = max(screen.x(), min(screen.x() + screen.width() - self._tw, x))
        bounded_y = max(screen.y(), min(screen.y() + screen.height() - self._th, y))
        return QPoint(int(bounded_x), int(bounded_y))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a DeskPet on Windows 11.")
    parser.add_argument("pet", nargs="?", help="Path to a .codex-pet.zip file")
    parser.add_argument("--scale", type=float, default=0.5, help="Pet scale. Default: 0.5")
    return parser.parse_args(argv)


def choose_pet(path_arg: str | None) -> Path:
    if path_arg:
        path = Path(path_arg).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path

    pets = list_pets()
    if not pets:
        raise FileNotFoundError(
            f"No .codex-pet.zip files found in {PETS_DIR}. "
            "Drop .codex-pet.zip pet bundles into ~/pets/."
        )
    return pets[0]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    PETS_DIR.mkdir(parents=True, exist_ok=True)
    PETS_DIR_ALT.mkdir(parents=True, exist_ok=True)

    try:
        zip_path = choose_pet(args.pet)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)
    pet = DesktopPet(zip_path, args.scale)
    pet.show()
    pet.raise_()
    pet.activateWindow()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
