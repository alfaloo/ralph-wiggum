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


# Note: each setter performs a read-then-write without locking. This is a theoretical
# TOCTOU race, but acceptable since settings are only mutated by user-initiated commands.

def get_verbose() -> bool:
    """Return the persisted verbose setting (default: False)."""
    return bool(_read_settings().get("verbose", False))


def set_verbose(value: bool) -> None:
    """Persist the verbose setting."""
    data = _read_settings()
    data["verbose"] = value
    _write_settings(data)


def get_asynchronous() -> bool:
    """Return the persisted asynchronous setting (default: False)."""
    return bool(_read_settings().get("asynchronous", False))


def set_asynchronous(value: bool) -> None:
    """Persist the asynchronous setting."""
    data = _read_settings()
    data["asynchronous"] = value
    _write_settings(data)


def get_rounds() -> int:
    """Return the persisted rounds setting (default: 1)."""
    return int(_read_settings().get("rounds", 1))


def set_rounds(value: int) -> None:
    """Persist the rounds setting."""
    data = _read_settings()
    data["rounds"] = value
    _write_settings(data)


def get_limit() -> int:
    """Return the persisted limit setting (default: 20)."""
    return int(_read_settings().get("limit", 20))


def set_limit(value: int) -> None:
    """Persist the limit setting."""
    data = _read_settings()
    data["limit"] = value
    _write_settings(data)


DEFAULT_TIMEOUT = 15


def get_timeout() -> int:
    """Return the persisted timeout setting (default: DEFAULT_TIMEOUT minutes)."""
    return int(_read_settings().get("timeout", DEFAULT_TIMEOUT))


def set_timeout(value: int) -> None:
    """Persist the timeout setting.

    Validates that value is a positive integer. Prints an error and returns
    early if the value is invalid.
    """
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        print(f"[ralph] Oops! '{value}' is not a valid timeout. Use a positive integer (minutes).")
        return
    data = _read_settings()
    data["timeout"] = value
    _write_settings(data)


def get_base() -> str:
    """Return the persisted base branch setting (default: 'main')."""
    return str(_read_settings().get("base", "main"))


def set_base(value: str) -> None:
    """Persist the base branch setting."""
    data = _read_settings()
    data["base"] = value
    _write_settings(data)


_VALID_PROVIDERS = ["github", "gitlab"]


def get_provider() -> str:
    """Return the persisted provider setting (default: 'github')."""
    return str(_read_settings().get("provider", "github"))


def set_provider(value: str) -> None:
    """Persist the provider setting.

    Prints an error and returns early if the value is not one of the
    supported providers.
    """
    if value not in _VALID_PROVIDERS:
        print(f"[ralph] Oops! '{value}' is not a supported provider. Pick from: {', '.join(_VALID_PROVIDERS)}.")
        return
    data = _read_settings()
    data["provider"] = value
    _write_settings(data)


def get_single() -> bool:
    """Return the persisted single setting (default: False)."""
    return bool(_read_settings().get("single", False))


def set_single(value: bool) -> None:
    """Persist the single setting."""
    data = _read_settings()
    data["single"] = value
    _write_settings(data)


_DEFAULTS = {
    "verbose": False,
    "rounds": 1,
    "limit": 20,
    "timeout": DEFAULT_TIMEOUT,
    "base": "main",
    "provider": "github",
    "asynchronous": False,
    "single": False,
}

DEFAULT_LIMIT = _DEFAULTS["limit"]


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
