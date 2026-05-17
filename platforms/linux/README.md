# DeskPet — Linux

Linux runtime for DeskPet. Uses GTK3 for transparent, always-on-top desktop
rendering. Requires a compositor.

## Requirements

- Ubuntu 20.04+ (or any Linux with GTK3 + a compositor)
- Python 3.10+
- `python3-gi` — GTK3 bindings
- `python3-pil` — Pillow / WebP spritesheet loading

> **Wayland note:** The app forces the X11 GDK backend (`GDK_BACKEND=x11`) so
> window positioning works correctly under XWayland. This is handled
> automatically — no extra configuration needed.

## Install

```bash
bash install_linux.sh
```

Or manually:

```bash
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pil
mkdir -p ~/pets
cp desktop_pet.py ~/.local/bin/deskpet
chmod +x ~/.local/bin/deskpet
```

## Getting pets

| Directory | Notes |
|-----------|-------|
| `~/pets/` | Primary library |
| `~/.codex/pets/` | Secondary library |

## Usage

```bash
deskpet
deskpet ~/pets/grogu-kid.codex-pet.zip
deskpet --scale 0.75
```

## Context menu

- **Pet list** — switch instantly between all pets in your library
- **Enable movement** — pet wanders around the screen
- **Run on startup** — creates/removes `~/.config/autostart/deskpet.desktop`
- **Keep screen awake** — inhibits screen saver via D-Bus
- **Quit**

## Autostart (manual)

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/deskpet.desktop << EOF
[Desktop Entry]
Type=Application
Name=DeskPet
Exec=deskpet
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
```
