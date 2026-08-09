import hashlib
from functools import lru_cache


@lru_cache(maxsize=8192)
def hash_string(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
