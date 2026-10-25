"""Local-only exact potion totals for the pinned ordinary shortcut HUD."""
import hashlib
import json
from pathlib import Path

IMAGE_SHA256 = '3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a'


def source(image):
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError('Local shortcut total adapter image mismatch')
    # Use stable body bytes: an independent observer may own the entry trampoline.
    prefixes = {r: image[r:r + 16].hex() for r in (0x3475710, 0x347592f)}
    return Path(__file__).with_suffix('.js').read_text(encoding='utf8').replace(
        '__PREFIXES__', json.dumps(prefixes))
