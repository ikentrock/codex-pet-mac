#!/usr/bin/env python3
"""
DeskPet — desktop companion for Ubuntu/GNOME.
Loads any .codex-pet.zip from ~/pets/ and animates the sprite on your desktop.

Usage:
  desktop_pet.py [pet.codex-pet.zip] [--scale 0.5]
  (no argument = first pet found in ~/pets/)

Controls:
  Left-click     Trigger action animation
  Left-drag      Pick up and move the pet (plays lift/drop animation)
  Right-click    Context menu: change pet · toggle movement · quit
"""

import sys, os, io, json, math, random, time, tempfile, zipfile, shutil
# Force X11 backend so window.move() works (Wayland ignores it)
os.environ.setdefault('GDK_BACKEND', 'x11')
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio
import cairo
from PIL import Image

PETS_DIR       = os.path.expanduser("~/pets")
PETS_DIR_ALT   = os.path.expanduser("~/.deskpet/pets")
TILE_W, TILE_H = 192, 208
COLS, ROWS     = 8, 9

# (spritesheet_row, fps) — frame counts are detected per-pet at load time
ANIM_DEFS = {
    "idle":       (0, 6),
    "run_right":  (1, 10),
    "run_left":   (2, 10),
    "waving":     (3, 8),
    "jumping":    (4, 10),
    "failed":     (5, 3),
    "waiting":    (6, 10),
    "running":    (7, 6),
    "review":     (8, 8),
}

WALK_SPEED  = 0.8   # px/tick at ~60 fps
SLEEP_AFTER = 60.0  # seconds idle before sleeping


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
        if max(px[3] for px in tile.getdata()) > 10:
            count = col + 1
        else:
            break
    return max(count, 1)


def _pil_to_pixbuf(img: Image.Image) -> GdkPixbuf.Pixbuf:
    img = img.convert("RGBA")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(buf.getvalue())
    loader.close()
    return loader.get_pixbuf()


def _pil_to_input_region(img: Image.Image) -> cairo.Region:
    """Build a cairo.Region covering pixels with alpha > 10 (run-length per row)."""
    w, h   = img.size
    data   = img.tobytes()   # RGBA bytes, row-major
    stride = w * 4
    region = cairo.Region()
    for y in range(h):
        x = 0
        while x < w:
            while x < w and data[y * stride + x * 4 + 3] <= 10:
                x += 1
            if x >= w:
                break
            start = x
            while x < w and data[y * stride + x * 4 + 3] > 10:
                x += 1
            region.union_rectangle(cairo.RectangleInt(start, y, x - start, 1))
    return region


def _load_pet(zip_path: str, scale: float):
    """Return (display_name, pixbufs[row][frame], regions[row][frame], anims)."""
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
        anims      = {
            aname: (row, row_frames[row], fps)
            for aname, (row, fps) in ANIM_DEFS.items()
        }
        pixbufs: list[list[GdkPixbuf.Pixbuf]] = []
        regions: list[list[cairo.Region]]      = []
        for row in range(ROWS):
            row_pbs  = []
            row_regs = []
            for col in range(row_frames[row]):
                tile = sheet.crop((col * TILE_W, row * TILE_H,
                                   (col + 1) * TILE_W, (row + 1) * TILE_H))
                if scale != 1.0:
                    tile = tile.resize((tw, th), Image.LANCZOS)
                row_pbs.append(_pil_to_pixbuf(tile))
                row_regs.append(_pil_to_input_region(tile))
            pixbufs.append(row_pbs)
            regions.append(row_regs)

        return name, pixbufs, regions, anims
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Autostart ─────────────────────────────────────────────────────────────────

AUTOSTART_FILE = os.path.expanduser("~/.config/autostart/deskpet.desktop")
_SCRIPT        = os.path.abspath(__file__)


def _autostart_enabled() -> bool:
    return os.path.isfile(AUTOSTART_FILE)


def _write_autostart(zip_path: str, scale: float):
    os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
    exec_cmd = f"python3 {_SCRIPT} {zip_path} --scale {scale}"
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=DeskPet\n"
        f"Exec={exec_cmd}\n"
        "Hidden=false\n"
        "NoDisplay=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )
    with open(AUTOSTART_FILE, "w") as f:
        f.write(content)


def _remove_autostart():
    try:
        os.remove(AUTOSTART_FILE)
    except FileNotFoundError:
        pass


# ── Screen-sleep inhibit (D-Bus) ──────────────────────────────────────────────

def _dbus_inhibit_sleep() -> int | None:
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
            "org.freedesktop.ScreenSaver",
            "/org/freedesktop/ScreenSaver",
            "org.freedesktop.ScreenSaver", None,
        )
        result = proxy.call_sync(
            "Inhibit",
            GLib.Variant("(ss)", ("deskpet", "Keep screen awake")),
            Gio.DBusCallFlags.NONE, -1, None,
        )
        return result.unpack()[0]
    except Exception:
        return None


def _dbus_uninhibit_sleep(cookie: int):
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
            "org.freedesktop.ScreenSaver",
            "/org/freedesktop/ScreenSaver",
            "org.freedesktop.ScreenSaver", None,
        )
        proxy.call_sync(
            "UnInhibit",
            GLib.Variant("(u)", (cookie,)),
            Gio.DBusCallFlags.NONE, -1, None,
        )
    except Exception:
        pass


# ── Widget ────────────────────────────────────────────────────────────────────

class DesktopPet(Gtk.Window):
    def __init__(self, zip_path: str, scale: float = 0.5):
        super().__init__(title="DesktopPet")
        self._scale    = scale
        self._moving   = False
        self._zip_path = zip_path

        # ── Window (created once) ─────────────────────────────────
        screen = self.get_screen()
        vis = screen.get_rgba_visual()
        if vis:
            self.set_visual(vis)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)

        display = screen.get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo     = monitor.get_geometry()
        self._sw, self._sh = geo.width, geo.height

        self._tw = int(TILE_W * scale)
        self._th = int(TILE_H * scale)
        self._load(zip_path)

        self._x = float(self._sw - self._tw - 120)
        self._y = float(self._sh - self._th - 80)
        self.set_default_size(self._tw, self._th)
        self.move(int(self._x), int(self._y))

        # ── Animation state ───────────────────────────────────────
        self._anim    = "idle"
        self._fidx    = 0
        self._ftimer  = 0.0
        self._state   = "idle"
        self._stimer  = random.uniform(4.0, 8.0)
        self._target_x = self._x
        self._target_y = self._y
        self._last_interact = time.monotonic()

        # ── Drag state ────────────────────────────────────────────
        self._dragging    = False
        self._last_drag_x = 0.0
        self._last_drag_y = 0.0

        # ── Sleep inhibit ─────────────────────────────────────────
        self._sleep_cookie = None

        # ── Events & draw directly on the window (no child widget) ───
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK   |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.BUTTON1_MOTION_MASK
        )
        self.connect("draw",                 self._on_draw)
        self.connect("button-press-event",   self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("motion-notify-event",  self._on_motion)
        self.connect("destroy",              self._on_destroy)

        GLib.timeout_add(16, self._tick)
        self.show_all()
        # Apply initial input shape after the window is realized
        GLib.idle_add(self._update_input_shape)

    # ── Pet loading ───────────────────────────────────────────────────────────

    def _load(self, zip_path: str):
        self._zip_path = zip_path
        self._name, self._pixbufs, self._regions, self._anims = _load_pet(zip_path, self._scale)

    def _update_input_shape(self):
        row = self._anims[self._anim][0]
        self.input_shape_combine_region(self._regions[row][self._fidx])

    def _switch_pet(self, zip_path: str):
        self._load(zip_path)
        self._anim   = "idle"
        self._fidx   = 0
        self._ftimer = 0.0
        self._state  = "idle"
        self._stimer = random.uniform(4.0, 8.0)
        self._update_input_shape()
        self.queue_draw()

    # ── Context menu ──────────────────────────────────────────────────────────

    _MENU_CSS = b"""
        window { background:#2b2d30; border:1px solid #555; }
        button { color:#dce0e8; padding:5px 20px; background:transparent;
                 border:none; border-radius:0; font-size:13px; }
        button:hover { background:#3574f0; color:#ffffff; }
        .sep { background:#4a4a4a; min-height:1px; margin:2px 0; }
    """

    def _show_menu(self, ev):
        # Transparent full-screen overlay: catches every click outside the menu
        overlay = Gtk.Window(Gtk.WindowType.POPUP)
        vis = Gdk.Screen.get_default().get_rgba_visual()
        if vis:
            overlay.set_visual(vis)
        overlay.set_app_paintable(True)
        overlay.connect("draw", lambda w, cr: (
            cr.set_operator(cairo.OPERATOR_SOURCE),
            cr.set_source_rgba(0, 0, 0, 0),
            cr.paint()
        ))
        overlay.resize(self._sw, self._sh)
        overlay.move(0, 0)
        overlay.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        overlay.show_all()

        # Menu popup (shown after overlay so it sits on top)
        popup = Gtk.Window(Gtk.WindowType.POPUP)
        popup.set_decorated(False)

        provider = Gtk.CssProvider()
        provider.load_from_data(self._MENU_CSS)
        def sp(w):
            w.get_style_context().add_provider(
                provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        popup.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        popup.add(box)

        def close():
            self._menu_close_fn = None
            overlay.destroy()
            popup.destroy()

        self._menu_close_fn = close
        overlay.connect("button-press-event", lambda *_: close() or True)

        def row(label, cb):
            b = Gtk.Button(label=label)
            b.set_relief(Gtk.ReliefStyle.NONE)
            sp(b)
            b.connect("clicked", lambda _: (close(), cb()))
            box.pack_start(b, False, False, 0)

        def sep():
            s = Gtk.Separator()
            s.get_style_context().add_class("sep")
            sp(s)
            box.pack_start(s, False, False, 0)

        # Pet list (flat, no submenu)
        for path in list_pets():
            try:
                with zipfile.ZipFile(path) as z:
                    name = json.loads(z.read("pet.json")).get(
                        "displayName",
                        os.path.basename(path).replace(".codex-pet.zip", "")
                    )
            except Exception:
                name = os.path.basename(path).replace(".codex-pet.zip", "")
            mark = "● " if path == self._zip_path else "  "
            p = path
            row(mark + name, lambda pp=p: self._switch_pet(pp))
        sep()

        move_mark = "☑  " if self._moving else "☐  "
        row(move_mark + "Enable movement", lambda: self._apply_moving(not self._moving))

        start_mark = "☑  " if _autostart_enabled() else "☐  "
        row(start_mark + "Run on startup",
            lambda: _write_autostart(self._zip_path, self._scale)
                    if not _autostart_enabled() else _remove_autostart())

        awake_mark = "☑  " if self._sleep_cookie is not None else "☐  "
        row(awake_mark + "Keep screen awake",
            lambda: self._apply_keep_awake(self._sleep_cookie is None))
        sep()
        row("Quit", Gtk.main_quit)

        popup.show_all()
        w, h = popup.get_size()
        x = min(int(ev.x_root), max(0, self._sw - w))
        y = min(int(ev.y_root), max(0, self._sh - h))
        popup.move(x, y)

        # Ensure menu is stacked above overlay
        def raise_popup():
            gdk_win = popup.get_window()
            if gdk_win:
                gdk_win.raise_()
            return False
        GLib.idle_add(raise_popup)

    def _apply_moving(self, val: bool):
        self._moving = val
        if val:
            self._enter("walking")
        elif self._state == "walking":
            self._enter("idle")

    def _apply_keep_awake(self, val: bool):
        if val and self._sleep_cookie is None:
            self._sleep_cookie = _dbus_inhibit_sleep()
        elif not val and self._sleep_cookie is not None:
            _dbus_uninhibit_sleep(self._sleep_cookie)
            self._sleep_cookie = None

    def _on_destroy(self, _):
        if self._sleep_cookie is not None:
            _dbus_uninhibit_sleep(self._sleep_cookie)
        Gtk.main_quit()

    # ── Input ─────────────────────────────────────────────────────────────────

    def _on_press(self, _, ev):
        if ev.button == 3:
            self._show_menu(ev)
            return True
        fn = getattr(self, '_menu_close_fn', None)
        if fn:
            fn()
            return True
        self._last_drag_x = ev.x_root
        self._last_drag_y = ev.y_root
        self._dragging = False

    def _on_release(self, _, ev):
        if ev.button != 1:
            return
        was_dragging   = self._dragging
        self._dragging = False
        self._last_interact = time.monotonic()
        # Drop or click → play action, then resume state machine
        self._enter("action")
        if was_dragging:
            # After landing, go idle (action's stimer will expire naturally)
            self._state = "action"

    def _on_motion(self, _, ev):
        if not (ev.state & Gdk.ModifierType.BUTTON1_MASK):
            return
        ddx = ev.x_root - self._last_drag_x
        ddy = ev.y_root - self._last_drag_y
        self._last_drag_x = ev.x_root
        self._last_drag_y = ev.y_root
        if not self._dragging and (abs(ddx) > 0 or abs(ddy) > 0):
            self._dragging = True
            self._anim     = "jumping"
            self._fidx     = 0
            self._ftimer   = 0.0
        if self._dragging:
            self._x = max(0.0, min(float(self._sw - self._tw), self._x + ddx))
            self._y = max(0.0, min(float(self._sh - self._th), self._y + ddy))
            self.move(int(self._x), int(self._y))

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
            self._target_x = random.uniform(margin, self._sw - self._tw - margin)
            self._target_y = random.uniform(margin, self._sh - self._th - margin)
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
            # With movement: 55% walk, 35% idle, rest other
            if   r < 0.55: self._enter("walking")
            elif r < 0.90: self._enter("idle")
            elif r < 0.95: self._enter("action")
            elif r < 0.98: self._enter("jump")
            else:          self._enter("special")
        else:
            # Without movement: 90% idle, 10% other
            if   r < 0.90: self._enter("idle")
            elif r < 0.96: self._enter("action")
            elif r < 0.98: self._enter("jump")
            else:          self._enter("special")

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self) -> bool:
        dt = 0.016

        # Always advance animation frame
        _, nf, fps = self._anims[self._anim]
        self._ftimer += dt
        prev_fidx = self._fidx
        if self._ftimer >= 1.0 / fps:
            self._ftimer = 0.0
            self._fidx   = (self._fidx + 1) % nf
        if self._fidx != prev_fidx:
            self._update_input_shape()

        # Freeze state machine while being dragged
        if self._dragging:
            self.queue_draw()
            return True

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
                self._x  = max(0.0, min(float(self._sw - self._tw), self._x))
                self._y  = max(0.0, min(float(self._sh - self._th), self._y))
                self.move(int(self._x), int(self._y))
        elif self._stimer <= 0:
            self._pick_next()

        self.queue_draw()
        return True

    # ── Draw ──────────────────────────────────────────────────────────────────

    def _on_draw(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        row = self._anims[self._anim][0]
        Gdk.cairo_set_source_pixbuf(cr, self._pixbufs[row][self._fidx], 0, 0)
        cr.paint()


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
        None
    )
    if not zip_path:
        pets = list_pets()
        if not pets:
            print(f"No .codex-pet.zip files found in {PETS_DIR}")
            print("Drop .codex-pet.zip pet bundles into ~/pets/")
            sys.exit(1)
        zip_path = pets[0]

    if not os.path.exists(zip_path):
        print(f"File not found: {zip_path}")
        sys.exit(1)

    os.makedirs(PETS_DIR, exist_ok=True)
    DesktopPet(zip_path, scale=scale)
    Gtk.main()


if __name__ == "__main__":
    main()
