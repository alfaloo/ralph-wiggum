"""Per-repository settings persistence for Ralph Wiggum.

Settings are stored in ./.ralph/settings.json relative to the current
working directory. The file is a flat JSON object, e.g.:

    {"verbose": false, "rounds": 1}

The directory and file are created automatically when any setter or
defaulting-write logic runs.
"""

import json
import os

_SETTINGS_DIR = ".ralph"
_SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "settings.json")


def _read_settings() -> dict:
    """Read settings from disk, returning an empty dict if the file is absent or unreadable."""
    if not os.path.exists(_SETTINGS_FILE):
        return {}
    try:
        with open(_SETTINGS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_settings(data: dict) -> None:
    """Persist settings to disk, creating the directory and file if needed."""
    os.makedirs(_SETTINGS_DIR, exist_ok=True)
    with open(_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_verbose() -> bool:
    """Return the persisted verbose setting (default: False)."""
    return bool(_read_settings().get("verbose", False))


def set_verbose(value: bool) -> None:
    """Persist the verbose setting."""
    data = _read_settings()
    data["verbose"] = value
    _write_settings(data)


def get_rounds() -> int:
    """Return the persisted rounds setting.

    If the key is absent, writes the default value of 1 back to the file
    so that it is self-healed for future reads.
    """
    data = _read_settings()
    if "rounds" not in data:
        data["rounds"] = 1
        _write_settings(data)
        return 1
    return int(data["rounds"])


def set_rounds(value: int) -> None:
    """Persist the rounds setting."""
    data = _read_settings()
    data["rounds"] = value
    _write_settings(data)


def get_limit() -> int:
    """Return the persisted limit setting.

    If the key is absent, writes the default value of 20 back to the file
    so that it is self-healed for future reads.
    """
    data = _read_settings()
    if "limit" not in data:
        data["limit"] = 20
        _write_settings(data)
        return 20
    return int(data["limit"])


def set_limit(value: int) -> None:
    """Persist the limit setting."""
    data = _read_settings()
    data["limit"] = value
    _write_settings(data)


def get_base() -> str:
    """Return the persisted base branch setting.

    If the key is absent, writes the default value of 'main' back to the file
    so that it is self-healed for future reads.
    """
    data = _read_settings()
    if "base" not in data:
        data["base"] = "main"
        _write_settings(data)
        return "main"
    return str(data["base"])


def set_base(value: str) -> None:
    """Persist the base branch setting."""
    data = _read_settings()
    data["base"] = value
    _write_settings(data)


_VALID_PROVIDERS = ["github", "gitlab"]


def get_provider() -> str:
    """Return the persisted provider setting (default: 'github')."""
    data = _read_settings()
    if "provider" not in data:
        data["provider"] = "github"
        _write_settings(data)
        return "github"
    return str(data["provider"])


def set_provider(value: str) -> None:
    """Persist the provider setting.

    Prints an error and returns early if the value is not one of the
    supported providers.
    """
    if value not in _VALID_PROVIDERS:
        print(f"[ralph] Error: '{value}' is not a supported provider. Choose from: {', '.join(_VALID_PROVIDERS)}.")
        return
    data = _read_settings()
    data["provider"] = value
    _write_settings(data)


_DEFAULTS = {
    "verbose": False,
    "rounds": 1,
    "limit": 20,
    "base": "main",
    "provider": "github",
}


def ensure_defaults() -> None:
    """Ensure all flag variables have default values in settings.json.

    Creates .ralph/settings.json (and the directory) if absent. Writes default
    values only for keys not already present; existing values are not changed.
    """
    data = _read_settings()
    changed = False
    for key, default in _DEFAULTS.items():
        if key not in data:
            data[key] = default
            changed = True
    if changed or not os.path.exists(_SETTINGS_FILE):
        _write_settings(data)
