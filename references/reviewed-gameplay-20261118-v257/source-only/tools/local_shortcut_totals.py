"""Display-only quantity labels for the pinned HUD and item icons."""
import hashlib
import json
from pathlib import Path

IMAGE_SHA256 = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'


def source(image):
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError('Local shortcut total adapter image mismatch')
    # Use stable body bytes: an independent observer may own the entry trampoline.
    prefixes = {r: image[r:r + 16].hex() for r in (0x3475710, 0x347592f)}
    icon_prefixes = {r: image[r:r + 16].hex()
                     for r in (0x6751c7, 0x675223, 0x679800)}
    from els_server.game_data import client_data
    with client_data().read_session():
        from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
        from els_server.domain.character_slots import client_identity
        stackable, singletons = set(), set()
        for template, cap in TEMPLATE_MAX_STACKS.items():
            identity = client_identity(template)
            wire_id = identity[0] if identity is not None else template
            (stackable if cap > 1 else singletons).add(wire_id)
    code = Path(__file__).with_suffix('.js').read_text(encoding='utf8')
    return (code.replace('__PREFIXES__', json.dumps(prefixes))
            .replace('__ICON_PREFIXES__', json.dumps(icon_prefixes))
            .replace('__ICON_STACK_IDS__', json.dumps(sorted(stackable)))
            .replace('__ICON_SINGLETON_IDS__', json.dumps(sorted(stackable & singletons))))
