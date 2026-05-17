import json, os, shutil, tempfile, zipfile
from PIL import Image
from .constants import TILE_W, TILE_H, COLS, ROWS, ANIM_DEFS


def list_pets(primary_dir: str, alt_dir: str) -> list[str]:
    """Return sorted list of *-pet.zip paths found in either pet directory."""
    found: dict[str, str] = {}
    for d in (primary_dir, alt_dir):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith("-pet.zip"):
                    found.setdefault(f, os.path.join(d, f))
    return sorted(found.values(), key=os.path.basename)


def pet_display_name(zip_path: str) -> str:
    """Read the displayName from pet.json inside the bundle, fall back to filename."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            entry = next(
                n for n in z.namelist()
                if os.path.basename(n) == "pet.json" and "__MACOSX" not in n
            )
            meta = json.loads(z.read(entry))
            return meta.get("displayName") or _stem(zip_path)
    except Exception:
        return _stem(zip_path)


def _stem(zip_path: str) -> str:
    name = os.path.basename(zip_path)
    idx  = name.lower().rfind("-pet.zip")
    if idx > 0:
        stem = name[:idx]
        dot  = stem.rfind(".")
        return stem[:dot] if dot > 0 else stem
    return name.removesuffix(".zip")


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

    Handles both flat zips (pet.json at root) and subdirectory zips
    (e.g. ibera/pet.json), and ignores __MACOSX metadata entries.
    """
    tmp = tempfile.mkdtemp(prefix="deskpet-")
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)

        # Locate pet.json — may be inside a subdirectory
        pet_json_path = None
        for root, dirs, files in os.walk(tmp):
            dirs[:] = [d for d in dirs if d != "__MACOSX"]
            if "pet.json" in files:
                pet_json_path = os.path.join(root, "pet.json")
                break
        if pet_json_path is None:
            raise FileNotFoundError(f"pet.json not found in {zip_path}")
        pet_dir = os.path.dirname(pet_json_path)

        with open(pet_json_path) as f:
            meta = json.load(f)
        name  = meta.get("displayName") or _stem(zip_path)
        sheet = Image.open(
            os.path.join(pet_dir, meta.get("spritesheetPath", "spritesheet.webp"))
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
    """Parse [pet-bundle.zip] [--scale N] from a sys.argv slice."""
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
