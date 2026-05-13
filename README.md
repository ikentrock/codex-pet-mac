# Codex Pet for macOS

Run your [codex-pets.net](https://codex-pets.net) desktop companions on macOS.

Loads any `.codex-pet.zip` file and animates the sprite on your desktop — transparent, always-on-top, wandering around your screen.

## Requirements

- macOS 11+
- Python 3.10+
- `Pillow` — WebP spritesheet loading
- `pyobjc-framework-Cocoa` — AppKit bindings

## Install

```bash
git clone https://github.com/ikentrock/codex-pet-mac
cd codex-pet-mac
bash install_mac.sh
```

Or manually:

```bash
pip3 install --user Pillow pyobjc-framework-Cocoa
mkdir -p ~/pets
cp desktop_pet.py ~/.local/bin/codex-pet
chmod +x ~/.local/bin/codex-pet
```

## Getting pets

Pets are loaded from two directories (both are optional):

| Directory | Notes |
|-----------|-------|
| `~/pets/` | Primary library |
| `~/.codex/pets/` | Secondary library (scanned if it exists) |

1. Download any `.codex-pet.zip` from [codex-pets.net](https://codex-pets.net)
2. Drop the file into `~/pets/`
3. It will appear automatically in the right-click menu

## Usage

```bash
# Launch with the first pet found in ~/pets/
codex-pet

# Launch a specific pet
codex-pet ~/pets/grogu-kid.codex-pet.zip

# Larger size (default scale is 0.5)
codex-pet --scale 0.75
```

## Controls

| Action | Result |
|--------|--------|
| **Left-click** | Trigger waving animation |
| **Left-drag** | Pick up and move the pet (plays jumping animation) |
| **Right-click** | Context menu |

### Context menu

- **Pet list** — switch instantly between all pets in your library
- **☑ Enable movement** — pet wanders around the screen using Run Right / Run Left animations
- **☑ Run on startup** — creates/removes `~/Library/LaunchAgents/net.codex-pet.desktop.plist`
- **☑ Keep screen awake** — runs `caffeinate -d` to prevent display sleep; off by default
- **Quit**

## Autostart

Toggle **Run on startup** from the right-click menu, or load the LaunchAgent manually:

```bash
launchctl load ~/Library/LaunchAgents/net.codex-pet.desktop.plist
```

## Pet format

The `.codex-pet.zip` format from codex-pets.net contains:

```
pet.json          # metadata: id, displayName, spritesheetPath
spritesheet.webp  # RGBA spritesheet: 192×208px tiles, 8 cols × 9 rows
```

| Row | Animation | When used |
|-----|-----------|-----------|
| 0 | Idle | Standing still |
| 1 | Run Right | Moving right |
| 2 | Run Left | Moving left |
| 3 | Waving | Left-click / drop |
| 4 | Jumping | Dragging |
| 5 | Failed | Sleeping (after 60 s idle) |
| 6 | Waiting | Moving vertically |
| 7 | Running | *(reserved)* |
| 8 | Review | Rare special event |

Blank frames at the end of each row are detected and skipped automatically.
