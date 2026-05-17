#!/usr/bin/env python3
"""
DeskPet — desktop companion for Ubuntu/GNOME.
Loads any .codex-pet.zip from ~/pets/ or ~/.deskpet/pets/ and animates
the sprite on your desktop.

Usage:
  desktop_pet.py [pet.codex-pet.zip] [--scale 0.5]
  (no argument = first pet found in ~/pets/)

Controls:
  Left-click     Trigger action animation
  Left-drag      Pick up and move the pet (plays jumping animation)
  Right-click    Context menu: change pet · size · personality · movement · quit
"""

import sys, os, io, shutil

# Locate the shared core package: prefer the installed copy, fall back to repo.
_share = os.path.expanduser("~/.local/share/deskpet")
_repo  = os.path.join(os.path.dirname(__file__), "..", "..")
for _p in (_share, _repo):
    if os.path.isdir(os.path.join(_p, "core")):
        sys.path.insert(0, os.path.abspath(_p))
        break

# Force X11 backend so window.move() works (Wayland ignores it)
os.environ.setdefault("GDK_BACKEND", "x11")
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio
import cairo
from PIL import Image

from core.bundle import list_pets as _list_pets, load_pet_pil, pet_display_name, parse_cli
from core.state import PetState
from core.constants import TILE_W, TILE_H
from core.settings import load as load_settings, save as save_settings

PETS_DIR     = os.path.expanduser("~/pets")
PETS_DIR_ALT = os.path.expanduser("~/.deskpet/pets")

_SCALES       = [("S  (×0.25)", 0.25), ("M  (×0.50)", 0.50), ("L  (×0.75)", 0.75)]
_PERSONALITIES = [("Friendly", "friendly"), ("Focused", "focused"), ("Playful", "playful")]


def list_pets() -> list[str]:
    return _list_pets(PETS_DIR, PETS_DIR_ALT)


# ── Image conversion ──────────────────────────────────────────────────────────

def _pil_to_pixbuf(img: Image.Image) -> GdkPixbuf.Pixbuf:
    buf = io.BytesIO()
    img.convert("RGBA").save(buf, "PNG")
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(buf.getvalue())
    loader.close()
    return loader.get_pixbuf()


def _pil_to_input_region(img: Image.Image) -> cairo.Region:
    """Build a cairo.Region covering opaque pixels (alpha > 10), run-length per row."""
    w, h   = img.size
    data   = img.tobytes()
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
    name, pil_frames, anims = load_pet_pil(zip_path, scale)
    pixbufs = [[_pil_to_pixbuf(tile) for tile in row] for row in pil_frames]
    regions = [[_pil_to_input_region(tile) for tile in row] for row in pil_frames]
    return name, pixbufs, regions, anims


# ── Autostart (.desktop) ──────────────────────────────────────────────────────

AUTOSTART_FILE = os.path.expanduser("~/.config/autostart/deskpet.desktop")
_SCRIPT        = os.path.abspath(__file__)


def _autostart_enabled() -> bool:
    return os.path.isfile(AUTOSTART_FILE)


def _write_autostart(zip_path: str, scale: float):
    os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=DeskPet\n"
        f"Exec=python3 {_SCRIPT} {zip_path} --scale {scale}\n"
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


_SCRIPT = os.path.abspath(__file__)


def _install_default_pet():
    """Seed ~/pets/ from the repo's pets/ directory on first run."""
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

    def __init__(self, zip_path: str, scale: float = 0.5, settings: dict | None = None):
        super().__init__(title="DeskPet")
        self._scale    = scale
        self._zip_path = zip_path
        self._settings = settings or {}

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
        sw, sh  = geo.width, geo.height
        tw, th  = int(TILE_W * scale), int(TILE_H * scale)

        self._name, self._pixbufs, self._regions, self._anims = _load_pet(zip_path, scale)
        self._ps = PetState(sx=0, sy=0, sw=sw, sh=sh, tw=tw, th=th)

        if self._settings.get("movement_enabled"):
            self._ps.set_moving(True)
        self._ps.set_personality(self._settings.get("personality_style", "friendly"))

        self._sleep_cookie = None
        self._dragging     = False
        self._drag_mouse_x = 0.0
        self._drag_mouse_y = 0.0
        self._drag_start_x = 0.0
        self._drag_start_y = 0.0

        # Pointer device for Playful mouse-chase cursor tracking
        try:
            self._gdk_pointer = Gdk.Display.get_default().get_default_seat().get_pointer()
        except Exception:
            self._gdk_pointer = None

        self.set_default_size(tw, th)
        self.move(int(self._ps.x), int(self._ps.y))

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
        GLib.idle_add(self._update_input_shape)

    def _update_input_shape(self):
        row = self._anims[self._ps.anim][0]
        self.input_shape_combine_region(self._regions[row][self._ps.fidx])

    def _switch_pet(self, zip_path: str):
        self._zip_path = zip_path
        self._name, self._pixbufs, self._regions, self._anims = _load_pet(zip_path, self._scale)
        self._ps.enter("idle")
        self._update_input_shape()
        self.queue_draw()
        self._save_settings()

    def _apply_scale(self, scale: float):
        self._scale = scale
        tw, th = int(TILE_W * scale), int(TILE_H * scale)
        self._name, self._pixbufs, self._regions, self._anims = _load_pet(self._zip_path, scale)
        self._ps.resize(tw, th)
        self.set_resizable(True)
        self.resize(tw, th)
        self.set_resizable(False)
        self.move(int(self._ps.x), int(self._ps.y))
        self._update_input_shape()
        self.queue_draw()
        self._save_settings()
        if _autostart_enabled():
            _write_autostart(self._zip_path, scale)

    def _apply_personality(self, name: str):
        self._ps.set_personality(name)
        self._save_settings()

    def _save_settings(self):
        ps   = self._ps
        data = {
            **self._settings,
            "pet_path":          self._zip_path,
            "pet_scale":         self._scale,
            "movement_enabled":  ps.moving,
            "personality_style": ps.personality,
        }
        save_settings(data)
        self._settings = data

    # ── Context menu ──────────────────────────────────────────────────────────

    _MENU_CSS = b"""
        window { background:#2b2d30; border:1px solid #555; }
        button { color:#dce0e8; padding:5px 20px; background:transparent;
                 border:none; border-radius:0; font-size:13px; }
        button:hover { background:#3574f0; color:#ffffff; }
        .sep { background:#4a4a4a; min-height:1px; margin:2px 0; }
    """

    def _show_menu(self, ev):
        ps = self._ps
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
        overlay.resize(ps.sw, ps.sh)
        overlay.move(0, 0)
        overlay.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        overlay.show_all()

        popup = Gtk.Window(Gtk.WindowType.POPUP)
        popup.set_decorated(False)

        provider = Gtk.CssProvider()
        provider.load_from_data(self._MENU_CSS)
        def sp(w):
            w.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        popup.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

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

        # Switch Pet
        for path in list_pets():
            name = pet_display_name(path)
            mark = "● " if path == self._zip_path else "  "
            p    = path
            row(mark + name, lambda pp=p: self._switch_pet(pp))
        sep()

        # Size
        for label, sc in _SCALES:
            mark = "● " if abs(sc - self._scale) < 0.01 else "  "
            s = sc
            row(mark + label, lambda ss=s: self._apply_scale(ss))
        sep()

        # Personality
        for label, pname in _PERSONALITIES:
            mark = "● " if pname == ps.personality else "  "
            n = pname
            row(mark + label, lambda nn=n: self._apply_personality(nn))
        sep()

        move_mark = "☑  " if ps.moving else "☐  "
        row(move_mark + "Enable movement",
            lambda: (ps.set_moving(not ps.moving), self._save_settings()))

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
        x = min(int(ev.x_root), max(0, ps.sw - w))
        y = min(int(ev.y_root), max(0, ps.sh - h))
        popup.move(x, y)

        def raise_popup():
            gdk_win = popup.get_window()
            if gdk_win:
                gdk_win.raise_()
            return False
        GLib.idle_add(raise_popup)

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
        fn = getattr(self, "_menu_close_fn", None)
        if fn:
            fn()
            return True
        self._drag_mouse_x = ev.x_root
        self._drag_mouse_y = ev.y_root
        self._drag_start_x = self._ps.x
        self._drag_start_y = self._ps.y
        self._dragging = False

    def _on_release(self, _, ev):
        if ev.button != 1:
            return
        self._dragging = False
        self._ps.on_release()

    def _on_motion(self, _, ev):
        if not (ev.state & Gdk.ModifierType.BUTTON1_MASK):
            return
        if not self._dragging:
            self._dragging = True
            self._ps.on_drag_start()
        dx = ev.x_root - self._drag_mouse_x
        dy = ev.y_root - self._drag_mouse_y
        self._ps.on_drag(self._drag_start_x + dx, self._drag_start_y + dy)
        self.move(int(self._ps.x), int(self._ps.y))

    # ── Tick ──────────────────────────────────────────────────────────────────

    def _tick(self) -> bool:
        if self._gdk_pointer is not None:
            try:
                result = self._gdk_pointer.get_position()
                self._ps.update_cursor(float(result[1]), float(result[2]))
            except Exception:
                pass

        prev_fidx        = self._ps.fidx
        position_changed = self._ps.tick(0.016, self._anims)
        if position_changed:
            self.move(int(self._ps.x), int(self._ps.y))
        if self._ps.fidx != prev_fidx:
            self._update_input_shape()
        self.queue_draw()
        return True

    # ── Draw ──────────────────────────────────────────────────────────────────

    def _on_draw(self, _widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        row = self._anims[self._ps.anim][0]
        Gdk.cairo_set_source_pixbuf(cr, self._pixbufs[row][self._ps.fidx], 0, 0)
        cr.paint()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    settings        = load_settings()
    scale_explicit  = "--scale" in sys.argv
    zip_str, scale_cli = parse_cli(sys.argv[1:])
    scale = scale_cli if scale_explicit else settings.get("pet_scale", 0.5)

    if not zip_str:
        zip_str = settings.get("pet_path")

    if zip_str and not os.path.exists(zip_str):
        zip_str = None  # saved pet was deleted; fall through to auto-select

    if not zip_str:
        pets = list_pets()
        if not pets:
            print(f"No .codex-pet.zip files found in {PETS_DIR}")
            print("Drop .codex-pet.zip pet bundles into ~/pets/")
            sys.exit(1)
        zip_str = pets[0]

    os.makedirs(PETS_DIR, exist_ok=True)
    _install_default_pet()
    DesktopPet(zip_str, scale=scale, settings=settings)
    Gtk.main()


if __name__ == "__main__":
    main()
