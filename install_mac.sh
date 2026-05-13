#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_NAME="codex-pet"

echo "=== Codex Pet for macOS — installer ==="
echo

# ── Python 3.10+ check ────────────────────────────────────────────────────────
# Prefer a Homebrew python over the system one (Apple's Python 3.9 from
# Xcode CLT can't build pyobjc-core 12 from source).

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" &>/dev/null; then
        PY="$candidate"
        break
    fi
done

# Fall back to whatever python3 resolves to, then check its version.
if [ -z "$PY" ]; then
    PY="python3"
fi

PY_MINOR=$("$PY" -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$("$PY" -c "import sys; print(sys.version_info.major)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ is required (found $($PY --version 2>&1))."
    echo
    echo "The system Python 3.9 bundled with Xcode Command Line Tools cannot"
    echo "build the pyobjc-core extension. Install a newer Python first:"
    echo
    echo "  brew install python@3.11"
    echo
    echo "Then re-run this installer. Homebrew Python is detected automatically."
    exit 1
fi

echo "Using $($PY --version 2>&1) at $(command -v "$PY")"
PIP="$PY -m pip"

# ── Dependencies ──────────────────────────────────────────────────────────────
echo "Checking dependencies..."

MISSING_PIP=()
"$PY" -c "from PIL import Image" 2>/dev/null || MISSING_PIP+=("Pillow")
"$PY" -c "import AppKit"         2>/dev/null || MISSING_PIP+=("pyobjc-framework-Cocoa")

if [ ${#MISSING_PIP[@]} -gt 0 ]; then
    echo "Installing Python packages: ${MISSING_PIP[*]}"
    $PIP install --user "${MISSING_PIP[@]}"
else
    echo "  All dependencies satisfied."
fi

# ── Pets directory ────────────────────────────────────────────────────────────
mkdir -p "$HOME/pets"
echo "Pets library: ~/pets/"
echo "  Drop any .codex-pet.zip from codex-pets.net into that folder."

# ── Install script ────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"
# Embed the correct interpreter in the shebang so 'codex-pet' always uses
# the Python that has the packages installed.
PY_ABS=$(command -v "$PY")
{ echo "#!$PY_ABS"; tail -n +2 desktop_pet.py; } > "$INSTALL_DIR/$SCRIPT_NAME"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"
echo "Installed: $INSTALL_DIR/$SCRIPT_NAME  (interpreter: $PY_ABS)"

# ── PATH check ───────────────────────────────────────────────────────────────
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo
    echo "  NOTE: $INSTALL_DIR is not in your PATH."
    echo "  Add this to your ~/.zshrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo
echo "Done! Run with:  codex-pet"
echo "Or:              $PY desktop_pet.py"
