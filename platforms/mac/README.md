# DeskPet — macOS

macOS runtime for DeskPet. Uses PyObjC/AppKit for transparent, always-on-top
desktop rendering.

## Requirements

- macOS 11+
- **Python 3.10+** — the system Python 3.9 bundled with Xcode Command Line Tools cannot build `pyobjc-core` from source; use Homebrew Python instead
- `Pillow` — WebP spritesheet loading
- `pyobjc-framework-Cocoa` — AppKit bindings

> **Don't have Python 3.10+?** Install it with Homebrew:
> ```bash
> brew install python@3.11
> ```
> The installer detects Homebrew Python automatically.

## Install

```bash
bash install_mac.sh
```

Or manually (with Python 3.10+):

```bash
python3.11 -m venv ~/.local/share/deskpet/venv
~/.local/share/deskpet/venv/bin/pip install Pillow pyobjc-framework-Cocoa
mkdir -p ~/DeskPets
{ printf '#!/Users/$USER/.local/share/deskpet/venv/bin/python\n'; tail -n +2 desktop_pet.py; } \
  > ~/.local/bin/deskpet
chmod +x ~/.local/bin/deskpet
```

## Getting pets

| Directory | Notes |
|-----------|-------|
| `~/DeskPets/` | Primary library |
| `~/.deskpet/pets/` | Secondary library |

## Usage

```bash
deskpet
deskpet ~/DeskPets/my-pet.codex-pet.zip
deskpet --scale 0.75
```

## Context menu

- **Pet list** — switch instantly between all pets in your library
- **Enable movement** — pet wanders around the screen
- **Run on startup** — creates/removes `~/Library/LaunchAgents/com.ikentrock.deskpet.plist`
- **Keep screen awake** — runs `caffeinate -d` to prevent display sleep
- **Quit**

## Autostart (manual)

```bash
launchctl load ~/Library/LaunchAgents/com.ikentrock.deskpet.plist
```
