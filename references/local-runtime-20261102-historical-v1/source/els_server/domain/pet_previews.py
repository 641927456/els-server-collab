"""Native cash-item to companion preview links.

The client registers `AddPetPreViewData(item, unit)` so a shop page can show what
a ticket opens. 571 distinct links over 512 items:

  * 430 pet links over 411 items (191 distinct pets, PET_UNIT_ID)
  * 141 mount links over 101 items (90 distinct mounts, RIDING_PET_UNIT_ID)

An item does **not** map to exactly one unit. Ten items are pools — random boxes
that preview up to 24 units — so every item maps to an ordered list. Keying by
item alone would silently keep only the last registration and lose 59 links.

Every link resolves to an entry in `companion_templets.json`, so a preview can be
followed straight to the growth and skill data.

This is a display link only. It does not authorise granting the companion, and
it carries no drop chance: the native call registers pool membership, not a
distribution, so a 24-unit pool must not be read as 1/24 each.
"""
import functools
import hashlib
import json

from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT

DATA = PROJECT_ROOT / 'els_server/data/pet_previews.json'


@functools.lru_cache(maxsize=1)
def _payload():
    data = json.loads(DATA.read_text(encoding='utf8'))
    if data.get('client_sha256') != CLIENT_SHA:
        raise ValueError('Pet preview client mismatch')
    for source in data.get('sources', []):
        path = PROJECT_ROOT / source['path']
        # The analysis artifacts ship in the runtime asset archive, not in git.
        # Verify them whenever they are present so drift cannot pass silently.
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Pet preview source changed: %s' % source['path'])
    for key in ('pet_previews', 'mount_previews'):
        data[key] = {int(k): v for k, v in data[key].items()}
    return data


def pet_previews():
    """`{item_id: [{symbol, unit_id, templet_key}, ...]}`."""
    return dict(_payload()['pet_previews'])


def mount_previews():
    """`{item_id: [{symbol, unit_id, templet_key}, ...]}`."""
    return dict(_payload()['mount_previews'])


def previews(item_id, kind=None):
    """Preview rows for one item, or () when the item previews nothing.

    `kind` may be 'pet' or 'mount' to narrow a pool to one companion family.
    """
    if kind not in (None, 'pet', 'mount'):
        raise ValueError('Unknown preview kind: %r' % (kind,))
    payload = _payload()
    wanted = int(item_id)
    if kind == 'pet':
        rows = list(payload['pet_previews'].get(wanted, ()))
    elif kind == 'mount':
        rows = list(payload['mount_previews'].get(wanted, ()))
    else:
        rows = list(payload['pet_previews'].get(wanted, ()))
        rows += payload['mount_previews'].get(wanted, ())
    return tuple(rows)


def units(item_id, kind=None):
    """Sorted unit ids the item previews."""
    return tuple(sorted(row['unit_id'] for row in previews(item_id, kind)))


def symbols(item_id, kind=None):
    """Sorted unit symbols the item previews."""
    return tuple(sorted(row['symbol'] for row in previews(item_id, kind)))


def is_pool(item_id):
    """Whether the item previews more than one unit (a random box)."""
    return len(previews(item_id)) > 1


@functools.lru_cache(maxsize=1)
def _by_symbol():
    index = {}
    for key, kind in (('pet_previews', 'pet'), ('mount_previews', 'mount')):
        for item_id, rows in _payload()[key].items():
            for row in rows:
                index.setdefault(row['symbol'], []).append((item_id, kind))
    return {symbol: tuple(sorted(hits)) for symbol, hits in index.items()}


def items_for(symbol):
    """`((item_id, kind), ...)` — every shop item that previews `symbol`."""
    return _by_symbol().get(symbol.rpartition('.')[-1], ())


def summary():
    return dict(_payload()['summary'])
