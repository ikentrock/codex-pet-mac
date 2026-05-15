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

import sys, os, io, json, math, random, time, tempfile, zipfile, shutil, subprocess
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

PETS_DIR     = os.path.expanduser("~/DeskPets")
PETS_DIR_ALT = os.path.expanduser("~/.deskpet/pets")
TILE_W, TILE_H = 192, 208
COLS, ROWS     = 8, 9

ANIM_DEFS = {
    "idle":      (0, 6),
    "run_right": (1, 10),
    "run_left":  (2, 10),
    "waving":    (3, 8),
    "jumping":   (4, 10),
    "failed":    (5, 3),
    "waiting":   (6, 10),
    "running":   (7, 6),
    "review":    (8, 8),
}

WALK_SPEED  = 2.0
SLEEP_AFTER = 60.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def list_pets() -> list[str]:
    found = {}
    for d in (PETS_DIR, PETS_DIR_ALT):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".codex-pet.zip"):
                    found.setdefault(f, os.path.join(d, f))
    return sorted(found.values(), key=os.path.basename)


def _count_frames(sheet: Image.Image, row: int) -> int:
    count = 0
    for col in range(COLS):
        tile = sheet.crop((col * TILE_W, row * TILE_H,
                           (col + 1) * TILE_W, (row + 1) * TILE_H))
        if tile.getchannel("A").getextrema()[1] > 10:
            count = col + 1
        else:
            break
    return max(count, 1)


def _pil_to_nsimage(img: Image.Image) -> NSImage:
    img = img.convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    raw = buf.getvalue()
    nsdata = objc.lookUpClass("NSData").dataWithBytes_length_(raw, len(raw))
    return NSImage.alloc().initWithData_(nsdata)


def _load_pet(zip_path: str, scale: float):
    """Return (display_name, frames[row][frame], anims{name:(row,nf,fps)})."""
    tmp = tempfile.mkdtemp()
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        with open(os.path.join(tmp, "pet.json")) as f:
            meta = json.load(f)
        name  = meta.get("displayName", os.path.basename(zip_path))
        sheet = Image.open(
            os.path.join(tmp, meta.get("spritesheetPath", "spritesheet.webp"))
        ).convert("RGBA")
        tw, th     = int(TILE_W * scale), int(TILE_H * scale)
        row_frames = [_count_frames(sheet, r) for r in range(ROWS)]
        anims = {
            aname: (row, row_frames[row], fps)
            for aname, (row, fps) in ANIM_DEFS.items()
        }
        frames: list[list[NSImage]] = []
        for row in range(ROWS):
            row_imgs = []
            for col in range(row_frames[row]):
                tile = sheet.crop((col * TILE_W, row * TILE_H,
                                   (col + 1) * TILE_W, (row + 1) * TILE_H))
                if scale != 1.0:
                    tile = tile.resize((tw, th), Image.LANCZOS)
                row_imgs.append(_pil_to_nsimage(tile))
            frames.append(row_imgs)
        return name, frames, anims
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    """Bridges NSTimer → Python callable."""

    def initWithCallback_(self, callback):
        self = objc.super(_TimerTarget, self).init()
        if self is None:
            return None
        self._cb = callback
        return self

    def tick_(self, _timer):
        self._cb()


class _MenuHandler(NSObject):
    """Dispatches NSMenuItem actions by tag."""

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
            NSMakeRect(0, 0, pet._tw, pet._th)
        )
        if self is None:
            return None
        self._pet         = pet
        self._dragging    = False
        self._drag_mouse_x = 0.0
        self._drag_mouse_y = 0.0
        self._drag_window_x = 0.0
        self._drag_window_y = 0.0
        return self

    def isOpaque(self):
        return False

    def acceptsFirstMouse_(self, _event):
        return True

    def drawRect_(self, _rect):
        pet = self._pet
        NSColor.clearColor().set()
        NSRectFill(self.bounds())
        row = pet._anims[pet._anim][0]
        img = pet._frames[row][pet._fidx]
        img.drawInRect_fromRect_operation_fraction_(
            self.bounds(), NSZeroRect, NSCompositingOperationSourceOver, 1.0
        )

    # ── Input ─────────────────────────────────────────────────────────────────

    def mouseDown_(self, _event):
        loc = NSEvent.mouseLocation()
        pet = self._pet
        self._drag_mouse_x = loc.x
        self._drag_mouse_y = loc.y
        self._drag_window_x = pet._x
        self._drag_window_y = pet._y
        self._dragging = False

    def mouseUp_(self, _event):
        self._dragging           = False
        self._pet._is_dragging   = False
        self._pet._last_interact = time.monotonic()
        self._pet._enter("action")

    def mouseDragged_(self, event):
        if not self._dragging:
            self._dragging         = True
            self._pet._is_dragging = True
            self._pet._anim        = "jumping"
            self._pet._fidx        = 0
            self._pet._ftimer      = 0.0

        pet   = self._pet
        loc   = NSEvent.mouseLocation()
        dx    = loc.x - self._drag_mouse_x
        dy    = loc.y - self._drag_mouse_y
        new_x = max(pet._sx, min(pet._sx + pet._sw - pet._tw, self._drag_window_x + dx))
        new_y = max(pet._sy, min(pet._sy + pet._sh - pet._th, self._drag_window_y + dy))
        pet._x, pet._y = new_x, new_y
        pet._window.setFrameOrigin_(NSMakePoint(new_x, new_y))

    def rightMouseDown_(self, event):
        self._pet._show_menu(event)


# ── Desktop pet ───────────────────────────────────────────────────────────────

class DesktopPet:

    def __init__(self, zip_path: str, scale: float = 0.5):
        self._scale      = scale
        self._zip_path   = zip_path
        self._moving     = False
        self._is_dragging = False
        self._caffeinate  = None  # subprocess for caffeinate -d

        # Screen (visibleFrame excludes Dock + menu bar)
        sf = NSScreen.mainScreen().visibleFrame()
        self._sx = sf.origin.x
        self._sy = sf.origin.y
        self._sw = sf.size.width
        self._sh = sf.size.height

        self._tw = int(TILE_W * scale)
        self._th = int(TILE_H * scale)

        self._name, self._frames, self._anims = _load_pet(zip_path, scale)

        # Start at bottom-right
        self._x = float(self._sx + self._sw - self._tw - 120)
        self._y = float(self._sy + 80)

        # Animation state
        self._anim   = "idle"
        self._fidx   = 0
        self._ftimer = 0.0
        self._state  = "idle"
        self._stimer = random.uniform(4.0, 8.0)
        self._target_x    = self._x
        self._target_y    = self._y
        self._last_interact = time.monotonic()

        # Window
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(self._x, self._y, self._tw, self._th),
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

        # 60 fps timer
        self._timer_target = _TimerTarget.alloc().initWithCallback_(self._tick)
        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0 / 60.0, self._timer_target, "tick:", None, True
        )

    # ── Pet switching ─────────────────────────────────────────────────────────

    def _load(self, zip_path: str):
        self._zip_path = zip_path
        self._name, self._frames, self._anims = _load_pet(zip_path, self._scale)

    def _switch_pet(self, zip_path: str):
        self._load(zip_path)
        self._anim   = "idle"
        self._fidx   = 0
        self._ftimer = 0.0
        self._state  = "idle"
        self._stimer = random.uniform(4.0, 8.0)
        self._view.setNeedsDisplay_(True)

    # ── Context menu ──────────────────────────────────────────────────────────

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
            try:
                with zipfile.ZipFile(path) as z:
                    name = json.loads(z.read("pet.json")).get(
                        "displayName",
                        os.path.basename(path).replace(".codex-pet.zip", "")
                    )
            except Exception:
                name = os.path.basename(path).replace(".codex-pet.zip", "")
            p = path
            add(("● " if path == self._zip_path else "  ") + name,
                lambda pp=p: self._switch_pet(pp),
                checked=(path == self._zip_path))

        menu.addItem_(NSMenuItem.separatorItem())
        add("Enable movement",
            lambda: self._apply_moving(not self._moving),
            checked=self._moving)
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

        # NSMenu handles its own dismissal natively on macOS
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self._view)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _apply_moving(self, val: bool):
        self._moving = val
        if val:
            self._enter("walking")
        elif self._state == "walking":
            self._enter("idle")

    def _apply_keep_awake(self, val: bool):
        if val and self._caffeinate is None:
            self._caffeinate = subprocess.Popen(["caffeinate", "-d"])
        elif not val and self._caffeinate is not None:
            self._caffeinate.terminate()
            self._caffeinate = None

    def cleanup(self):
        self._timer.invalidate()
        if self._caffeinate:
            self._caffeinate.terminate()

    # ── State machine ─────────────────────────────────────────────────────────

    def _enter(self, state: str):
        self._state  = state
        self._fidx   = 0
        self._ftimer = 0.0

        if state == "idle":
            self._anim   = "idle"
            self._stimer = random.uniform(4.0, 10.0)

        elif state == "walking":
            margin = 80
            self._target_x = random.uniform(
                self._sx + margin, self._sx + self._sw - self._tw - margin)
            self._target_y = random.uniform(
                self._sy + margin, self._sy + self._sh - self._th - margin)
            dx = self._target_x - self._x
            self._anim   = "run_right" if dx >= 0 else "run_left"
            self._stimer = 999.0

        elif state == "sleeping":
            self._anim   = "failed"
            self._stimer = random.uniform(10.0, 20.0)

        elif state == "action":
            self._anim   = "waving"
            self._stimer = 2.0

        elif state == "jump":
            self._anim   = "jumping"
            self._stimer = 1.5

        elif state == "special":
            self._anim   = "review"
            self._stimer = 2.5

    def _pick_next(self):
        if time.monotonic() - self._last_interact > SLEEP_AFTER:
            self._enter("sleeping")
            return
        r = random.random()
        if self._moving:
            if   r < 0.55: self._enter("walking")
            elif r < 0.90: self._enter("idle")
            elif r < 0.95: self._enter("action")
            elif r < 0.98: self._enter("jump")
            else:          self._enter("special")
        else:
            if   r < 0.90: self._enter("idle")
            elif r < 0.96: self._enter("action")
            elif r < 0.98: self._enter("jump")
            else:          self._enter("special")

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self):
        dt = 1.0 / 60.0

        _, nf, fps = self._anims[self._anim]
        self._ftimer += dt
        if self._ftimer >= 1.0 / fps:
            self._ftimer = 0.0
            self._fidx   = (self._fidx + 1) % nf

        if self._is_dragging:
            self._view.setNeedsDisplay_(True)
            return

        self._stimer -= dt

        if self._state == "walking":
            dx   = self._target_x - self._x
            dy   = self._target_y - self._y
            dist = math.hypot(dx, dy)
            if dist < WALK_SPEED * 2:
                self._enter("idle")
            else:
                expected = "run_right" if dx >= 0 else "run_left"
                if self._anim != expected:
                    self._anim   = expected
                    self._fidx   = 0
                    self._ftimer = 0.0
                self._x += dx / dist * WALK_SPEED
                self._y += dy / dist * WALK_SPEED
                self._x = max(self._sx, min(self._sx + self._sw - self._tw, self._x))
                self._y = max(self._sy, min(self._sy + self._sh - self._th, self._y))
                self._window.setFrameOrigin_(NSMakePoint(self._x, self._y))
        elif self._stimer <= 0:
            self._pick_next()

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
    args  = sys.argv[1:]
    scale = 0.5
    if "--scale" in args:
        try:
            scale = float(args[args.index("--scale") + 1])
        except (IndexError, ValueError):
            pass

    zip_path = next(
        (os.path.abspath(a) for a in args if a.endswith(".zip") and not a.startswith("--")),
        None,
    )
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
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # no Dock icon

    delegate = AppDelegate.alloc().initWithZip_scale_(zip_path, scale)
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
