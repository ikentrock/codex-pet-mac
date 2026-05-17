import json, os

SETTINGS_DIR  = os.path.expanduser("~/.deskpet")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

_DEFAULTS: dict = {
    "pet_path":          None,
    "pet_scale":         0.5,
    "movement_enabled":  False,
    "personality_style": "friendly",
}


def load() -> dict:
    """Return persisted settings merged over defaults. Never raises."""
    try:
        with open(SETTINGS_FILE) as f:
            return {**_DEFAULTS, **json.load(f)}
    except Exception:
        return dict(_DEFAULTS)


def save(data: dict) -> None:
    """Persist settings to disk. Never raises."""
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass
