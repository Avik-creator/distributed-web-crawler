from __future__ import annotations

import hashlib
import re
from collections import defaultdict


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = text.split()
    return [w for w in words if len(w) > 2]


def _hash_token(token: str) -> int:
    h = hashlib.md5(token.encode()).digest()
    return int.from_bytes(h[:8], "big")


def simhash(text: str, bits: int = 64) -> int:
    tokens = _tokenize(text)
    if not tokens:
        return 0

    vectors = [0] * bits
    token_counts: dict[str, int] = defaultdict(int)
    for token in tokens:
        token_counts[token] += 1

    for token, count in token_counts.items():
        h = _hash_token(token)
        weight = count
        for i in range(bits):
            bit = (h >> i) & 1
            if bit:
                vectors[i] += weight
            else:
                vectors[i] -= weight

    fingerprint = 0
    for i in range(bits):
        if vectors[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(hash1: int, hash2: int) -> int:
    xor = hash1 ^ hash2
    count = 0
    while xor:
        count += 1
        xor &= xor - 1
    return count


def is_near_duplicate(hash1: int, hash2: int, threshold: int = 3) -> bool:
    return hamming_distance(hash1, hash2) <= threshold
