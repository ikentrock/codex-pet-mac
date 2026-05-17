import json, os, shutil, tempfile, zipfile
from PIL import Image
from .constants import TILE_W, TILE_H, COLS, ROWS, ANIM_DEFS


def list_pets(primary_dir: str, alt_dir: str) -> list[str]:
    """Return sorted list of .codex-pet.zip paths found in either pet directory."""
    found: dict[str, str] = {}
    for d in (primary_dir, alt_dir):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".codex-pet.zip"):
                    found.setdefault(f, os.path.join(d, f))
    return sorted(found.values(), key=os.path.basename)


def pet_display_name(zip_path: str) -> str:
    """Read the displayName from pet.json inside the bundle, fall back to filename."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            meta = json.loads(z.read("pet.json"))
            return meta.get("displayName") or _stem(zip_path)
    except Exception:
        return _stem(zip_path)


def _stem(zip_path: str) -> str:
    return os.path.basename(zip_path).replace(".codex-pet.zip", "")


def _count_frames(sheet: Image.Image, row: int) -> int:
    """Count non-blank frames in a spritesheet row by checking alpha channel."""
    count = 0
    for col in range(COLS):
        tile = sheet.crop((col * TILE_W, row * TILE_H,
                           (col + 1) * TILE_W, (row + 1) * TILE_H))
        if tile.getchannel("A").getextrema()[1] > 10:
            count = col + 1
        else:
            break
    return max(count, 1)


def load_pet_pil(zip_path: str, scale: float) -> tuple[str, list[list[Image.Image]], dict]:
    """Extract and slice a pet bundle into PIL RGBA tiles.

    Returns (display_name, frames[row][col], anims) where anims maps
    animation name → (row, frame_count, fps).
    """
    tmp = tempfile.mkdtemp(prefix="deskpet-")
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        with open(os.path.join(tmp, "pet.json")) as f:
            meta = json.load(f)
        name  = meta.get("displayName") or _stem(zip_path)
        sheet = Image.open(
            os.path.join(tmp, meta.get("spritesheetPath", "spritesheet.webp"))
        ).convert("RGBA")
        tw, th     = int(TILE_W * scale), int(TILE_H * scale)
        row_frames = [_count_frames(sheet, r) for r in range(ROWS)]
        anims = {
            aname: (row, row_frames[row], fps)
            for aname, (row, fps) in ANIM_DEFS.items()
        }
        frames: list[list[Image.Image]] = []
        for row in range(ROWS):
            row_imgs = []
            for col in range(row_frames[row]):
                tile = sheet.crop((col * TILE_W, row * TILE_H,
                                   (col + 1) * TILE_W, (row + 1) * TILE_H))
                if scale != 1.0:
                    tile = tile.resize((tw, th), Image.LANCZOS)
                row_imgs.append(tile)
            frames.append(row_imgs)
        return name, frames, anims
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def parse_cli(argv: list[str]) -> tuple[str | None, float]:
    """Parse [pet.codex-pet.zip] [--scale N] from a sys.argv slice."""
    scale = 0.5
    if "--scale" in argv:
        try:
            scale = float(argv[argv.index("--scale") + 1])
        except (IndexError, ValueError):
            pass
    zip_path = next(
        (os.path.abspath(a) for a in argv if a.endswith(".zip") and not a.startswith("--")),
        None,
    )
    return zip_path, scale
