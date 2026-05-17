# DeskPet — Windows

Windows 11 runtime for DeskPet. Uses PySide6 for transparent, always-on-top
desktop rendering.

## Requirements

- Windows 11
- Python 3.10+
- `Pillow` — WebP spritesheet loading
- `PySide6` — transparent desktop window

## Install

Open PowerShell in this directory and run:

```powershell
.\install_win.ps1
```

If PowerShell blocks local scripts, run this once for the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install_win.ps1
```

## Getting pets

| Directory | Notes |
|-----------|-------|
| `%USERPROFILE%\pets\` | Primary library |
| `%USERPROFILE%\.deskpet\pets\` | Secondary library |

## Usage

```powershell
%USERPROFILE%\.local\bin\deskpet.cmd
%USERPROFILE%\.local\bin\deskpet.cmd %USERPROFILE%\pets\grogu-kid.codex-pet.zip
%USERPROFILE%\.local\bin\deskpet.cmd --scale 0.75
```

## Context menu

- **Pet list** — switch instantly between pets in your library
- **Enable movement** — pet wanders around the screen
- **Run on startup** — creates/removes a Startup folder launcher
- **Keep screen awake** — asks Windows to keep the display awake
- **Quit**
