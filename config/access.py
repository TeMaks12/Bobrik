import json

from config.settings import ACCESS_FILE, API_KEYS, OWNER_ID

_data = json.loads(ACCESS_FILE.read_text(encoding="utf-8")) if ACCESS_FILE.exists() else {}
allowed_ids = {int(x) for x in _data.get("users", [])}
_state = {"key": min(max(int(_data.get("key", 0)), 0), len(API_KEYS) - 1)}


def _save():
    ACCESS_FILE.write_text(
        json.dumps({"users": sorted(allowed_ids), "key": _state["key"]}),
        encoding="utf-8",
    )


def get_api_key():
    return API_KEYS[_state["key"]]


def get_key_index():
    return _state["key"]


def set_key_index(index):
    _state["key"] = index
    _save()


def add_user(user_id):
    allowed_ids.add(user_id)
    _save()


def remove_user(user_id):
    allowed_ids.discard(user_id)
    _save()


def has_access(user_id):
    return user_id == OWNER_ID or user_id in allowed_ids
