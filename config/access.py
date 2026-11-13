import json

from config.settings import ACCESS_FILE, API_KEYS, OWNER_ID

_data = json.loads(ACCESS_FILE.read_text(encoding="utf-8")) if ACCESS_FILE.exists() else {}
allowed_ids = {int(x) for x in _data.get("users", [])}


def _save():
    ACCESS_FILE.write_text(
        json.dumps({"users": sorted(allowed_ids)}),
        encoding="utf-8",
    )


def get_api_key():
    return API_KEYS[0]


def add_user(user_id):
    allowed_ids.add(user_id)
    _save()


def remove_user(user_id):
    allowed_ids.discard(user_id)
    _save()


def has_access(user_id):
    return user_id == OWNER_ID or user_id in allowed_ids
