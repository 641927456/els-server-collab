"""Local-only exact potion totals for the pinned ordinary shortcut HUD."""
import hashlib
import json
from pathlib import Path

IMAGE_SHA256 = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'


def source(image):
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError('Local shortcut total adapter image mismatch')
    # Use stable body bytes: an independent observer may own the entry trampoline.
    prefixes = {r: image[r:r + 16].hex() for r in (0x3475710, 0x347592f)}
    return Path(__file__).with_suffix('.js').read_text(encoding='utf8').replace(
        '__PREFIXES__', json.dumps(prefixes))
