#!/usr/bin/env python3
"""
DeskPet Mac — macOS desktop companion runtime.
Loads any .codex-pet.zip from ~/DeskPets/ and animates the sprite on your desktop.

Usage:
  desktop_pet.py [pet.codex-pet.zip] [--scale 0.5]
  (no argument = first pet found in ~/DeskPets/)

Controls:
  Left-click     Trigger waving animation
  Left-drag      Pick up and move the pet (plays jumping animation)
  Right-click    Context menu: change pet · toggle movement · quit
"""

import sys, os, io, zipfile

# Locate the shared core package: prefer the installed copy, fall back to repo.
_share = os.path.expanduser("~/.local/share/deskpet")
_repo  = os.path.join(os.path.dirname(__file__), "..", "..")
for _p in (_share, _repo):
    if os.path.isdir(os.path.join(_p, "core")):
        sys.path.insert(0, os.path.abspath(_p))
        break

from PIL import Image
import objc
from AppKit import (
    NSApplication, NSWindow, NSView, NSTimer, NSColor, NSImage, NSEvent,
    NSScreen, NSMenu, NSMenuItem,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
    NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSApplicationActivationPolicyAccessory,
    NSCompositingOperationSourceOver,
    NSRectFill, NSZeroRect,
)
from Foundation import NSObject, NSMakeRect, NSMakePoint

from core.bundle import list_pets as _list_pets, load_pet_pil, pet_display_name, parse_cli
from core.state import PetState
from core.constants import TILE_W, TILE_H

PETS_DIR     = os.path.expanduser("~/DeskPets")
PETS_DIR_ALT = os.path.expanduser("~/.deskpet/pets")


def list_pets() -> list[str]:
    return _list_pets(PETS_DIR, PETS_DIR_ALT)


# ── Image conversion ──────────────────────────────────────────────────────────

def _pil_to_nsimage(img: Image.Image) -> NSImage:
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, "PNG")
    raw    = buf.getvalue()
    nsdata = objc.lookUpClass("NSData").dataWithBytes_length_(raw, len(raw))
    return NSImage.alloc().initWithData_(nsdata)


def _load_pet(zip_path: str, scale: float):
    name, pil_frames, anims = load_pet_pil(zip_path, scale)
    frames = [[_pil_to_nsimage(tile) for tile in row] for row in pil_frames]
    return name, frames, anims


# ── Autostart (LaunchAgent) ───────────────────────────────────────────────────

LAUNCHAGENT_DIR  = os.path.expanduser("~/Library/LaunchAgents")
LAUNCHAGENT_FILE = os.path.join(LAUNCHAGENT_DIR, "com.ikentrock.deskpet.plist")
_SCRIPT = os.path.abspath(__file__)


def _autostart_enabled() -> bool:
    return os.path.isfile(LAUNCHAGENT_FILE)


def _write_autostart(zip_path: str, scale: float):
    os.makedirs(LAUNCHAGENT_DIR, exist_ok=True)
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>Label</key><string>com.ikentrock.deskpet</string>\n'
        '  <key>ProgramArguments</key><array>\n'
        f'    <string>{sys.executable}</string>\n'
        f'    <string>{_SCRIPT}</string>\n'
        f'    <string>{zip_path}</string>\n'
        '    <string>--scale</string>\n'
        f'    <string>{scale}</string>\n'
        '  </array>\n'
        '  <key>RunAtLoad</key><true/>\n'
        '  <key>KeepAlive</key><false/>\n'
        '</dict></plist>\n'
    )
    with open(LAUNCHAGENT_FILE, "w") as f:
        f.write(plist)


def _remove_autostart():
    try:
        os.remove(LAUNCHAGENT_FILE)
    except FileNotFoundError:
        pass


# ── ObjC bridge helpers ───────────────────────────────────────────────────────

class _TimerTarget(NSObject):
    def initWithCallback_(self, callback):
        self = objc.super(_TimerTarget, self).init()
        if self is None:
            return None
        self._cb = callback
        return self

    def tick_(self, _timer):
        self._cb()


class _MenuHandler(NSObject):
    def initWithCallbacks_(self, callbacks: dict):
        self = objc.super(_MenuHandler, self).init()
        if self is None:
            return None
        self._callbacks = callbacks
        return self

    def doAction_(self, sender):
        cb = self._callbacks.get(sender.tag())
        if cb:
            cb()


# ── View ──────────────────────────────────────────────────────────────────────

class PetView(NSView):

    def initWithPet_(self, pet):
        self = objc.super(PetView, self).initWithFrame_(
            NSMakeRect(0, 0, pet._ps.tw, pet._ps.th)
        )
        if self is None:
            return None
        self._pet          = pet
        self._dragging     = False
        self._drag_mouse_x = 0.0
        self._drag_mouse_y = 0.0
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0
        return self

    def isOpaque(self):
        return False

    def acceptsFirstMouse_(self, _event):
        return True

    def drawRect_(self, _rect):
        ps  = self._pet._ps
        NSColor.clearColor().set()
        NSRectFill(self.bounds())
        row = self._pet._anims[ps.anim][0]
        img = self._pet._frames[row][ps.fidx]
        img.drawInRect_fromRect_operation_fraction_(
            self.bounds(), NSZeroRect, NSCompositingOperationSourceOver, 1.0
        )

    def mouseDown_(self, _event):
        ps = self._pet._ps
        loc = NSEvent.mouseLocation()
        self._drag_mouse_x = loc.x
        self._drag_mouse_y = loc.y
        self._drag_start_x = ps.x
        self._drag_start_y = ps.y
        self._dragging = False

    def mouseUp_(self, _event):
        self._dragging = False
        self._pet._ps.on_release()

    def mouseDragged_(self, _event):
        if not self._dragging:
            self._dragging = True
            self._pet._ps.on_drag_start()
        loc = NSEvent.mouseLocation()
        dx  = loc.x - self._drag_mouse_x
        dy  = loc.y - self._drag_mouse_y
        ps  = self._pet._ps
        ps.on_drag(self._drag_start_x + dx, self._drag_start_y + dy)
        self._pet._window.setFrameOrigin_(NSMakePoint(ps.x, ps.y))

    def rightMouseDown_(self, event):
        self._pet._show_menu(event)


# ── Desktop pet ───────────────────────────────────────────────────────────────

class DesktopPet:

    def __init__(self, zip_path: str, scale: float = 0.5):
        self._scale      = scale
        self._zip_path   = zip_path
        self._caffeinate = None

        sf = NSScreen.mainScreen().visibleFrame()
        sx, sy = sf.origin.x, sf.origin.y
        sw, sh = sf.size.width, sf.size.height
        tw, th = int(TILE_W * scale), int(TILE_H * scale)

        self._name, self._frames, self._anims = _load_pet(zip_path, scale)

        # macOS uses a bottom-left origin; start_y = sy+80 puts the pet near
        # the bottom of the visible area (above the Dock).
        self._ps = PetState(
            sx=sx, sy=sy, sw=sw, sh=sh, tw=tw, th=th,
            start_x=float(sx + sw - tw - 120),
            start_y=float(sy + 80),
        )

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(self._ps.x, self._ps.y, tw, th),
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorStationary      |
            NSWindowCollectionBehaviorIgnoresCycle
        )
        self._window.setIgnoresMouseEvents_(False)

        self._view = PetView.alloc().initWithPet_(self)
        self._window.setContentView_(self._view)
        self._window.makeKeyAndOrderFront_(None)

        self._timer_target = _TimerTarget.alloc().initWithCallback_(self._tick)
        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self._timer_target, "tick:", None, True
        )

    def _load(self, zip_path: str):
        self._zip_path = zip_path
        self._name, self._frames, self._anims = _load_pet(zip_path, self._scale)

    def _switch_pet(self, zip_path: str):
        self._load(zip_path)
        self._ps.enter("idle")
        self._view.setNeedsDisplay_(True)

    def _show_menu(self, event):
        menu      = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        callbacks = {}
        next_tag  = [0]

        def add(title, cb, checked=False):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, "doAction:", ""
            )
            item.setTag_(next_tag[0])
            item.setState_(1 if checked else 0)
            callbacks[next_tag[0]] = cb
            next_tag[0] += 1
            menu.addItem_(item)

        for path in list_pets():
            name = pet_display_name(path)
            p    = path
            add(("● " if path == self._zip_path else "  ") + name,
                lambda pp=p: self._switch_pet(pp),
                checked=(path == self._zip_path))

        menu.addItem_(NSMenuItem.separatorItem())
        add("Enable movement",
            lambda: self._ps.set_moving(not self._ps.moving),
            checked=self._ps.moving)
        add("Run on startup",
            lambda: _write_autostart(self._zip_path, self._scale)
                    if not _autostart_enabled() else _remove_autostart(),
            checked=_autostart_enabled())
        add("Keep screen awake",
            lambda: self._apply_keep_awake(self._caffeinate is None),
            checked=self._caffeinate is not None)
        menu.addItem_(NSMenuItem.separatorItem())
        add("Quit", lambda: NSApplication.sharedApplication().terminate_(None))

        handler = _MenuHandler.alloc().initWithCallbacks_(callbacks)
        for i in range(menu.numberOfItems()):
            item = menu.itemAtIndex_(i)
            if not item.isSeparatorItem():
                item.setTarget_(handler)

        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self._view)

    def _apply_keep_awake(self, val: bool):
        import subprocess
        if val and self._caffeinate is None:
            self._caffeinate = subprocess.Popen(["caffeinate", "-d"])
        elif not val and self._caffeinate is not None:
            self._caffeinate.terminate()
            self._caffeinate = None

    def cleanup(self):
        self._timer.invalidate()
        if self._caffeinate:
            self._caffeinate.terminate()

    def _tick(self):
        dt = 1.0 / 60.0
        position_changed = self._ps.tick(dt, self._anims)
        if position_changed:
            self._window.setFrameOrigin_(NSMakePoint(self._ps.x, self._ps.y))
        self._view.setNeedsDisplay_(True)


# ── App delegate ──────────────────────────────────────────────────────────────

class AppDelegate(NSObject):

    def initWithZip_scale_(self, zip_path: str, scale: float):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self._zip_path = zip_path
        self._scale    = scale
        self._pet      = None
        return self

    def applicationDidFinishLaunching_(self, _note):
        self._pet = DesktopPet(self._zip_path, self._scale)

    def applicationWillTerminate_(self, _note):
        if self._pet:
            self._pet.cleanup()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    zip_path, scale = parse_cli(sys.argv[1:])

    if not zip_path:
        pets = list_pets()
        if not pets:
            print(f"No .codex-pet.zip files found in {PETS_DIR}")
            print("Drop any .codex-pet.zip pet bundle into ~/DeskPets/")
            sys.exit(1)
        zip_path = pets[0]

    if not os.path.exists(zip_path):
        print(f"File not found: {zip_path}")
        sys.exit(1)

    os.makedirs(PETS_DIR, exist_ok=True)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    delegate = AppDelegate.alloc().initWithZip_scale_(zip_path, scale)
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
