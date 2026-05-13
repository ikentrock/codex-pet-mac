#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_NAME="codex-pet"

echo "=== Codex Pet for macOS — installer ==="
echo

# ── Dependencies ──────────────────────────────────────────────────────────────
echo "Checking dependencies..."

MISSING_PIP=()
python3 -c "from PIL import Image" 2>/dev/null || MISSING_PIP+=("Pillow")
python3 -c "import AppKit"         2>/dev/null || MISSING_PIP+=("pyobjc-framework-Cocoa")

if [ ${#MISSING_PIP[@]} -gt 0 ]; then
    echo "Installing Python packages: ${MISSING_PIP[*]}"
    pip3 install --user "${MISSING_PIP[@]}"
else
    echo "  All dependencies satisfied."
fi

# ── Pets directory ────────────────────────────────────────────────────────────
mkdir -p "$HOME/pets"
echo "Pets library: ~/pets/"
echo "  Drop any .codex-pet.zip from codex-pets.net into that folder."

# ── Install script ────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
cp desktop_pet.py "$INSTALL_DIR/$SCRIPT_NAME"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"
echo "Installed: $INSTALL_DIR/$SCRIPT_NAME"

# ── PATH check ───────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo
    echo "  NOTE: $INSTALL_DIR is not in your PATH."
    echo "  Add this to your ~/.zshrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo
echo "Done! Run with:  codex-pet"
echo "Or:              python3 desktop_pet.py"
