"""Align the pinned local client's template caps with the local stack policy."""
import hashlib
import json
from pathlib import Path

IMAGE_SHA256 = '3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a'


def source(image):
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError('Local stack template adapter image mismatch')
    from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
    ids = sorted(t for t, cap in TEMPLATE_MAX_STACKS.items() if cap == 999)
    if not ids or any(not isinstance(t, int) or t <= 0 for t in ids):
        raise ValueError('Invalid local stack template policy')
    code = Path(__file__).with_suffix('.js').read_text(encoding='utf8')
    return code.replace('__STACK_IDS__', json.dumps(ids)).replace(
        '__LOOKUP_PREFIX__', json.dumps(image[0x6d56c0:0x6d56d0].hex()))
