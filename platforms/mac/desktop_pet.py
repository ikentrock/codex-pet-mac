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
  Right-click    Context menu
"""

import sys, os, io, shutil, zipfile

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
    NSApplication, NSWindow, NSView, NSTimer, NSColor, NSImage, NSImageView,
    NSImageScaleAxesIndependently, NSEvent,
    NSScreen, NSMenu, NSMenuItem,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
    NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSApplicationActivationPolicyAccessory,
)
from Foundation import NSObject, NSMakeRect, NSMakePoint, NSMakeSize

from core.bundle   import list_pets as _list_pets, load_pet_pil, pet_display_name, parse_cli
from core.state    import PetState
from core.settings import load as load_settings, save as save_settings
from core.constants import TILE_W, TILE_H

PETS_DIR     = os.path.expanduser("~/DeskPets")
PETS_DIR_ALT = os.path.expanduser("~/.deskpet/pets")

_SCALES = [("S  (×0.25)", 0.25), ("M  (×0.50)", 0.50), ("L  (×0.75)", 0.75)]
_PERSONALITIES = [("Friendly", "friendly"), ("Focused", "focused"), ("Playful", "playful")]


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


# ── Default pet auto-install ──────────────────────────────────────────────────

_SCRIPT = os.path.abspath(__file__)

def _install_default_pet():
    """Seed ~/DeskPets/ from the repo's pets/ directory on first run."""
    if list_pets():
        return
    repo_pets = os.path.normpath(
        os.path.join(os.path.dirname(_SCRIPT), "..", "..", "pets")
    )
    if not os.path.isdir(repo_pets):
        return
    os.makedirs(PETS_DIR, exist_ok=True)
    for f in os.listdir(repo_pets):
        if f.endswith("-pet.zip"):
            dst = os.path.join(PETS_DIR, f)
            if not os.path.exists(dst):
                shutil.copy2(os.path.join(repo_pets, f), dst)


# ── Autostart (LaunchAgent) ───────────────────────────────────────────────────

LAUNCHAGENT_DIR  = os.path.expanduser("~/Library/LaunchAgents")
LAUNCHAGENT_FILE = os.path.join(LAUNCHAGENT_DIR, "com.ikentrock.deskpet.plist")


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


# ── View (event handling only — rendering via NSImageView) ────────────────────

class PetView(NSView):

    def initWithPet_(self, pet):
        tw, th = pet._ps.tw, pet._ps.th
        self = objc.super(PetView, self).initWithFrame_(NSMakeRect(0, 0, tw, th))
        if self is None:
            return None
        self._pet          = pet
        self._dragging     = False
        self._drag_mouse_x = 0.0
        self._drag_mouse_y = 0.0
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0

        # NSImageView for correct RGBA compositing on macOS 14+
        self._imgv = NSImageView.alloc().initWithFrame_(self.bounds())
        self._imgv.setWantsLayer_(True)
        self._imgv.setImageScaling_(NSImageScaleAxesIndependently)
        self.addSubview_(self._imgv)
        return self

    def isOpaque(self):
        return False

    def acceptsFirstMouse_(self, _event):
        return True

    def resizeToTW_TH_(self, tw, th):
        frame = NSMakeRect(0, 0, tw, th)
        self.setFrame_(frame)
        self._imgv.setFrame_(frame)

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

    # ── Pet / scale / personality ─────────────────────────────────────────────

    def _load(self, zip_path: str):
        self._zip_path = zip_path
        self._name, self._frames, self._anims = _load_pet(zip_path, self._scale)

    def _switch_pet(self, zip_path: str):
        self._load(zip_path)
        self._ps.enter("idle")
        self._save_settings()

    def _apply_scale(self, scale: float):
        if abs(scale - self._scale) < 0.01:
            return
        self._scale = scale
        tw, th = int(TILE_W * scale), int(TILE_H * scale)
        self._name, self._frames, self._anims = _load_pet(self._zip_path, scale)
        self._ps.resize(tw, th)
        # Resize window and image view in one step
        self._window.setFrame_display_(
            NSMakeRect(self._ps.x, self._ps.y, tw, th), True
        )
        self._view.resizeToTW_TH_(tw, th)
        self._save_settings()
        if _autostart_enabled():
            _write_autostart(self._zip_path, scale)

    def _apply_personality(self, name: str):
        self._ps.set_personality(name)
        self._save_settings()

    def _save_settings(self):
        save_settings({
            "pet_path":          self._zip_path,
            "pet_scale":         self._scale,
            "movement_enabled":  self._ps.moving,
            "personality_style": self._ps.personality,
        })

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_menu(self, event):
        menu      = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        callbacks = {}
        tag       = [0]

        def item(title, cb, checked=False, into=None):
            m = into or menu
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, "doAction:", "")
            it.setTag_(tag[0])
            it.setState_(1 if checked else 0)
            callbacks[tag[0]] = cb
            tag[0] += 1
            m.addItem_(it)

        def submenu(title, build_fn):
            parent = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, None, "")
            sub = NSMenu.alloc().initWithTitle_(title)
            sub.setAutoenablesItems_(False)
            build_fn(sub)
            parent.setSubmenu_(sub)
            menu.addItem_(parent)

        # ── Switch Pet submenu ────────────────────────────────────────────────
        def build_pets(sub):
            for path in list_pets():
                name = pet_display_name(path)
                p    = path
                item(("● " if path == self._zip_path else "  ") + name,
                     lambda pp=p: self._switch_pet(pp),
                     checked=(path == self._zip_path), into=sub)
        submenu("Switch Pet ▸", build_pets)

        # ── Size submenu ──────────────────────────────────────────────────────
        def build_sizes(sub):
            for label, s in _SCALES:
                sc = s
                item(label, lambda ss=sc: self._apply_scale(ss),
                     checked=abs(self._scale - s) < 0.01, into=sub)
        submenu("Size ▸", build_sizes)

        # ── Personality submenu ───────────────────────────────────────────────
        def build_personalities(sub):
            for label, p in _PERSONALITIES:
                pn = p
                item(label, lambda pp=pn: self._apply_personality(pp),
                     checked=(self._ps.personality == p), into=sub)
        submenu("Personality ▸", build_personalities)

        menu.addItem_(NSMenuItem.separatorItem())

        item("Enable movement",
             lambda: (self._ps.set_moving(not self._ps.moving), self._save_settings()),
             checked=self._ps.moving)
        item("Run on startup",
             lambda: _write_autostart(self._zip_path, self._scale)
                     if not _autostart_enabled() else _remove_autostart(),
             checked=_autostart_enabled())
        item("Keep screen awake",
             lambda: self._apply_keep_awake(self._caffeinate is None),
             checked=self._caffeinate is not None)

        menu.addItem_(NSMenuItem.separatorItem())
        item("Quit", lambda: NSApplication.sharedApplication().terminate_(None))

        # Attach handler to every item (recurse into submenus)
        handler = _MenuHandler.alloc().initWithCallbacks_(callbacks)
        def attach(m):
            for i in range(m.numberOfItems()):
                it = m.itemAtIndex_(i)
                if not it.isSeparatorItem():
                    it.setTarget_(handler)
                    if it.hasSubmenu():
                        attach(it.submenu())
        attach(menu)

        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self._view)

    # ── Screen-awake ──────────────────────────────────────────────────────────

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

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self):
        dt  = 1.0 / 60.0
        loc = NSEvent.mouseLocation()
        self._ps.update_cursor(loc.x, loc.y)

        position_changed = self._ps.tick(dt, self._anims)
        if position_changed:
            self._window.setFrameOrigin_(NSMakePoint(self._ps.x, self._ps.y))

        row = self._anims[self._ps.anim][0]
        self._view._imgv.setImage_(self._frames[row][self._ps.fidx])


# ── App delegate ──────────────────────────────────────────────────────────────

class AppDelegate(NSObject):

    def initWithZip_scale_settings_(self, zip_path, scale, settings):
        self = objc.super(AppDelegate, self).init()
        if self is None:
            return None
        self._zip_path = zip_path
        self._scale    = scale
        self._settings = settings
        self._pet      = None
        return self

    def applicationDidFinishLaunching_(self, _note):
        pet = DesktopPet(self._zip_path, self._scale)
        pet._ps.set_moving(self._settings.get("movement_enabled", False))
        pet._ps.set_personality(self._settings.get("personality_style", "friendly"))
        self._pet = pet

    def applicationWillTerminate_(self, _note):
        if self._pet:
            self._pet.cleanup()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    settings   = load_settings()
    zip_path, scale_arg = parse_cli(sys.argv[1:])
    scale = scale_arg if "--scale" in sys.argv else settings["pet_scale"]

    _install_default_pet()

    if not zip_path:
        saved = settings.get("pet_path")
        if saved and os.path.exists(saved):
            zip_path = saved
        else:
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

    delegate = AppDelegate.alloc().initWithZip_scale_settings_(zip_path, scale, settings)
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
