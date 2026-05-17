# DeskPet

A lightweight desktop companion runtime for macOS, Linux, and Windows. Loads
pet bundles and animates sprites on your desktop — transparent, always-on-top,
wandering around your screen.

Compatible with `.codex-pet.zip` pet bundles.

> **Note:** This project is independent and is not affiliated with, endorsed
> by, sponsored by, or officially connected to Codex, OpenAI, codex-pets.net,
> or any related third-party project.

## Platforms

| Platform | Directory | Command |
|----------|-----------|---------|
| macOS 11+ | [`platforms/mac/`](platforms/mac/) | `bash platforms/mac/install_mac.sh` |
| Ubuntu/GNOME (Linux) | [`platforms/linux/`](platforms/linux/) | `bash platforms/linux/install_linux.sh` |
| Windows 11 | [`platforms/windows/`](platforms/windows/) | `.\platforms\windows\install_win.ps1` |

Each platform directory contains its own `desktop_pet.py` runtime and
installer. See the README in each subdirectory for platform-specific details.

## Quick install

**macOS**
```bash
git clone https://github.com/ikentrock/deskpet
cd deskpet
bash platforms/mac/install_mac.sh
```

**Linux (Ubuntu/GNOME)**
```bash
git clone https://github.com/ikentrock/deskpet
cd deskpet
bash platforms/linux/install_linux.sh
```

**Windows 11 (PowerShell)**
```powershell
git clone https://github.com/ikentrock/deskpet
cd deskpet
.\platforms\windows\install_win.ps1
```

## Getting pets

Pets are loaded from two directories (both optional):

| OS | Primary | Secondary |
|----|---------|-----------|
| macOS | `~/DeskPets/` | `~/.deskpet/pets/` |
| Linux | `~/pets/` | `~/.codex/pets/` |
| Windows | `%USERPROFILE%\pets\` | `%USERPROFILE%\.codex\pets\` |

1. Obtain any `.codex-pet.zip` pet bundle
2. Drop it into the primary directory for your OS
3. It will appear automatically in the right-click menu

## Controls

| Action | Result |
|--------|--------|
| **Left-click** | Trigger waving animation |
| **Left-drag** | Pick up and move the pet |
| **Right-click** | Context menu |

### Context menu

- **Pet list** — switch instantly between all pets in your library
- **Enable movement** — pet wanders around the screen
- **Run on startup** — register/remove the autostart entry for your OS
- **Keep screen awake** — prevent display sleep while the pet is running
- **Quit**

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

**Open-source runtime (this repo):**

- Local desktop pet rendering
- Pet bundle loading
- Animation and movement behavior
- macOS, Linux, and Windows desktop integration
- Community themes or pets, where legally contributed

**Future commercial / private product areas (not in this repo):**

- AI agent behavior and memory
- Voice interaction
- App and system integrations
- Cloud sync
- Premium characters and personalities
- Packaged, signed installers
- Subscriptions or marketplace

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

The commercial DeskPet product, including AI-agent behavior, proprietary characters,
premium assets, cloud features, account systems, subscriptions, signed installers,
and enterprise functionality, is developed separately by Suber Systems.

The open-source license for this repository does not grant rights to Suber Systems
trademarks, logos, product names, mascots, artwork, characters, or commercial
service components.

## Security

See [SECURITY.md](SECURITY.md).
