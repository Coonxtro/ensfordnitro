import os
import time
from urllib.parse import quote_plus
import requests

_data_cache = {}
CACHE_TTL = int(os.getenv("CACHE_TTL", 3600))


def fetch_roblox_id(username: str) -> int:
    now = time.time()
    if username in _data_cache and now - _data_cache[username][0] < CACHE_TTL:
        return _data_cache[username][1]
    url = f"https://users.roblox.com/v1/users/search?keyword={quote_plus(username)}"
    backoff = 1
    for _ in range(5):
        resp = requests.get(url, timeout=5)
        if resp.status_code == 429:
            time.sleep(backoff)
            backoff *= 2
            continue
        resp.raise_for_status()
        data = resp.json().get("data", [])
        uid = data[0].get("id", 0) if data else 0
        _data_cache[username] = (now, uid)
        return uid
    return 0