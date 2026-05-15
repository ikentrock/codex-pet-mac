#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_NAME="deskpet"
VENV_DIR="$HOME/.local/share/deskpet/venv"

echo "=== DeskPet Mac — installer ==="
echo

# ── Python 3.10+ check ────────────────────────────────────────────────────────
# Prefer Homebrew Python over Apple's system Python 3.9 (Xcode CLT), which
# cannot build pyobjc-core 12 from source.

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        PY="$candidate"
        break
    fi
done
[ -z "$PY" ] && PY="python3"

PY_MINOR=$("$PY" -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$("$PY" -c "import sys; print(sys.version_info.major)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ is required (found $($PY --version 2>&1))."
    echo
    echo "The system Python 3.9 bundled with Xcode Command Line Tools cannot"
    echo "build pyobjc-core. Install a newer Python first:"
    echo
    echo "  brew install python@3.11"
    echo
    echo "Then re-run this installer. Homebrew Python is detected automatically."
    exit 1
fi

echo "Using $($PY --version 2>&1) at $(command -v "$PY")"

# ── Virtual environment ───────────────────────────────────────────────────────
# Homebrew Python 3.13+ is PEP 668 "externally managed" — pip install --user
# is blocked. A dedicated venv sidesteps this cleanly.

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv: $VENV_DIR"
    "$PY" -m venv "$VENV_DIR"
else
    echo "Venv exists: $VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ── Dependencies ──────────────────────────────────────────────────────────────
echo "Checking dependencies..."

MISSING_PIP=()
"$VENV_PY" -c "from PIL import Image" 2>/dev/null || MISSING_PIP+=("Pillow")
"$VENV_PY" -c "import AppKit"         2>/dev/null || MISSING_PIP+=("pyobjc-framework-Cocoa")

if [ ${#MISSING_PIP[@]} -gt 0 ]; then
    echo "Installing into venv: ${MISSING_PIP[*]}"
    "$VENV_PIP" install "${MISSING_PIP[@]}"
else
    echo "  All dependencies satisfied."
fi

# ── Pets directories ─────────────────────────────────────────────────────────
mkdir -p "$HOME/DeskPets" "$HOME/.deskpet/pets"
echo "Pets libraries:"
echo "  ~/DeskPets/        (primary)"
echo "  ~/.deskpet/pets/   (secondary)"
echo "  Drop any .codex-pet.zip into either folder."

# ── Install launcher ──────────────────────────────────────────────────────────
# Point the shebang at the venv Python so 'deskpet' always finds the packages.
mkdir -p "$INSTALL_DIR"
{ printf '#!%s\n' "$VENV_PY"; tail -n +2 desktop_pet.py; } > "$INSTALL_DIR/$SCRIPT_NAME"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"
echo "Installed: $INSTALL_DIR/$SCRIPT_NAME  (venv: $VENV_DIR)"

# ── PATH check ───────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo
    echo "  NOTE: $INSTALL_DIR is not in your PATH."
    echo "  Add this to your ~/.zshrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo
echo "Done! Run with:  deskpet"
echo "Or:              $VENV_PY desktop_pet.py"
