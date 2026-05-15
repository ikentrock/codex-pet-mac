# DeskPet Mac

A lightweight macOS desktop companion runtime. Loads pet bundles and animates
sprites on your desktop — transparent, always-on-top, wandering around your
screen.

Compatible with `.codex-pet.zip` pet bundles.

> **Note:** This project is independent and is not affiliated with, endorsed
> by, sponsored by, or officially connected to Codex, OpenAI, codex-pets.net,
> or any related third-party project.

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
git clone https://github.com/ikentrock/deskpet
cd codex-pet-mac
bash install_mac.sh
```

Or manually (with Python 3.10+):

```bash
python3.11 -m venv ~/.local/share/deskpet/venv
~/.local/share/deskpet/venv/bin/pip install Pillow pyobjc-framework-Cocoa
mkdir -p ~/DeskPets ~/Library/bin
# launcher with venv shebang
{ printf '#!/Users/$USER/.local/share/deskpet/venv/bin/python\n'; tail -n +2 desktop_pet.py; } \
  > ~/.local/bin/deskpet
chmod +x ~/.local/bin/deskpet
```

## Getting pets

Pets are loaded from two directories (both are optional):

| Directory | Notes |
|-----------|-------|
| `~/DeskPets/` | Primary library |
| `~/.deskpet/pets/` | Secondary library (scanned if it exists) |

1. Obtain any `.codex-pet.zip` pet bundle
2. Drop the file into `~/DeskPets/`
3. It will appear automatically in the right-click menu

## Usage

```bash
# Launch with the first pet found in ~/DeskPets/
deskpet

# Launch a specific pet
deskpet ~/DeskPets/my-pet.codex-pet.zip

# Larger size (default scale is 0.5)
deskpet --scale 0.75
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
- **☑ Run on startup** — creates/removes `~/Library/LaunchAgents/com.ikentrock.deskpet.plist`
- **☑ Keep screen awake** — runs `caffeinate -d` to prevent display sleep; off by default
- **Quit**

## Autostart

Toggle **Run on startup** from the right-click menu, or load the LaunchAgent manually:

```bash
launchctl load ~/Library/LaunchAgents/com.ikentrock.deskpet.plist
```

## Pet bundle format

The `.codex-pet.zip` format contains:

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

## Pet bundle safety

Only load pet bundles from sources you trust.

- Third-party pet bundles may have their own licenses and terms.
- This repository does not grant permission to reuse third-party pet assets.
- The maintainers are not responsible for the content or licensing of
  third-party pet bundles.

See [SECURITY.md](SECURITY.md) for more details.

## Roadmap

This repository is the open-source macOS desktop pet runtime. The scope of
this public repository is intentionally limited.

**Open-source runtime (this repo):**

- Local desktop pet rendering
- Pet bundle loading
- Animation and movement behavior
- macOS desktop integration
- Community themes or pets, where legally contributed

**Future commercial / private product areas (not in this repo):**

- AI agent behavior and memory
- Voice interaction
- App and system integrations
- Cloud sync
- Premium characters and personalities
- Packaged, signed macOS app
- Subscriptions or marketplace

The existence of this roadmap does not mean all future features will be added
to this public repository.

See [ROADMAP.md](ROADMAP.md) for open strategic work items.

## Licensing

The source code in this repository is licensed under the
[Apache License 2.0](LICENSE).

The Apache License 2.0 applies **only** to the source code in this
repository. It does **not** grant rights to any third-party pet files,
sprites, logos, characters, mascots, artwork, animations, icons, sounds,
names, trademarks, screenshots, or branded assets.

See [TRADEMARKS.md](TRADEMARKS.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
for additional details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Commercial development

This repository contains the open desktop pet runtime.

The commercial DeskPet product, including AI-agent behavior, proprietary characters, premium assets, cloud features, account systems, subscriptions, signed installers, and enterprise functionality, is developed separately by Suber Systems.

The open-source license for this repository does not grant rights to Suber Systems trademarks, logos, product names, mascots, artwork, characters, or commercial service components.

## Security

See [SECURITY.md](SECURITY.md).
