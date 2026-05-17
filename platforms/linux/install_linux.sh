#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_NAME="deskpet"

echo "=== DeskPet Linux — installer ==="
echo

# ── Dependencies ──────────────────────────────────────────────────────────────
echo "Checking dependencies..."

MISSING=()
python3 -c "import gi" 2>/dev/null         || MISSING+=("python3-gi python3-gi-cairo gir1.2-gtk-3.0")
python3 -c "from PIL import Image" 2>/dev/null || MISSING+=("python3-pil")

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Installing: ${MISSING[*]}"
    sudo apt-get install -y "${MISSING[@]}"
else
    echo "  All dependencies satisfied."
fi

# ── Shared core package ───────────────────────────────────────────────────────
SHARE_DIR="$HOME/.local/share/deskpet"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$SHARE_DIR"
echo "Installing core package: $SHARE_DIR/core"
cp -r "$REPO_ROOT/core" "$SHARE_DIR/"

# ── Pets directory ────────────────────────────────────────────────────────────
mkdir -p "$HOME/pets" "$HOME/.deskpet/pets"
echo "Pets library: ~/pets/"

# Copy bundled pets from the repo's pets/ directory (skip if already present)
if [ -d "$REPO_ROOT/pets" ]; then
    for f in "$REPO_ROOT/pets/"*-pet.zip; do
        [ -f "$f" ] || continue
        dst="$HOME/pets/$(basename "$f")"
        if [ ! -f "$dst" ]; then
            cp "$f" "$dst"
            echo "  Installed pet: $(basename "$f")"
        fi
    done
fi

# ── Install script ────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
cp desktop_pet.py "$INSTALL_DIR/$SCRIPT_NAME"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"
echo "Installed: $INSTALL_DIR/$SCRIPT_NAME"

# ── PATH check ───────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo
    echo "  NOTE: $INSTALL_DIR is not in your PATH."
    echo "  Add this to your ~/.bashrc or ~/.zshrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ── Autostart (optional) ──────────────────────────────────────────────────────
echo
read -r -p "Launch DeskPet automatically on login? [y/N] " ans
if [[ "$ans" =~ ^[Yy]$ ]]; then
    mkdir -p "$HOME/.config/autostart"
    cat > "$HOME/.config/autostart/deskpet.desktop" << EOF
[Desktop Entry]
Type=Application
Name=DeskPet
Exec=$INSTALL_DIR/$SCRIPT_NAME
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF
    echo "Autostart entry created."
fi

echo
echo "Done! Run with:  deskpet"
echo "Or:              python3 desktop_pet.py"
