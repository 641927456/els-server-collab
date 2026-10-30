"""Native character customization (定制) catalog for the pinned DX11 client.

Customization is a cosmetic-only system: none of the native blocks carries a stat
field. It is also a three-hop chain, and the server implements none of it today:

    cash-shop item  ->  CUSTOM_ID  ->  CUSTOMIZING_TYPE slot  ->  client display

This module exposes the three hops as a read-only catalog so the registration,
selection and expiry work can be built against accurate data. It does not
register, select, expire or persist anything.
"""
import functools
import hashlib
import json

from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT

DATA = PROJECT_ROOT / 'els_server/data/character_customizations.json'


@functools.lru_cache(maxsize=1)
def _payload():
    data = json.loads(DATA.read_text(encoding='utf8'))
    if data.get('client_sha256') != CLIENT_SHA:
        raise ValueError('Customization client mismatch')
    for source in data.get('sources', []):
        path = PROJECT_ROOT / source['path']
        # The analysis artifacts ship in the runtime asset archive, not in git.
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Customization source changed: %s' % source['path'])

    by_custom = {}
    by_item = {}
    for label, block in data['blocks'].items():
        custom = {}
        for entry in block['entries']:
            cid = entry.get('CUSTOM_ID')
            if cid is None:
                continue
            custom[cid] = entry
            item = entry.get('ITEM_ID')
            if item is not None:
                by_item.setdefault(item, []).append({'block': label, 'custom_id': cid})
        block['by_custom_id'] = custom

    for label, block in data['blocks'].items():
        for entry in block['entries']:
            cid = entry.get('CUSTOM_ID')
            if cid is not None:
                by_custom.setdefault(cid, []).append(label)

    data['custom_to_blocks'] = by_custom
    data['item_to_custom'] = by_item
    data['period_by_item'] = {row['item_id']: row['period_hours']
                              for row in data.get('period_items', [])}
    data['account_scoped'] = {
        entry['CUSTOM_ID'] for block in data['blocks'].values() for entry in block['entries']
        if entry.get('ACCOUNT_CUSTOM') is True
    }
    data['replace_map'] = {}
    for row in data.get('replace_ids', []):
        if isinstance(row, list) and len(row) == 3 and all(isinstance(v, int) for v in row):
            data['replace_map'].setdefault(row[0], []).extend([row[1], row[2]])
    return data


def blocks():
    """Native slot blocks, e.g. {'portrait': {...}, 'quick_voice': {...}}."""
    return dict(_payload()['blocks'])


def entries(block):
    """Catalog entries for one slot block."""
    found = _payload()['blocks'].get(block)
    if found is None:
        raise ValueError('Unknown customization block: %r' % (block,))
    return list(found['entries'])


def entry(block, custom_id):
    """One catalog entry, or None."""
    found = _payload()['blocks'].get(block)
    if found is None:
        raise ValueError('Unknown customization block: %r' % (block,))
    return found['by_custom_id'].get(int(custom_id))


def blocks_for(custom_id):
    """Which slot blocks declare this custom id (a custom id can appear twice)."""
    return list(_payload()['custom_to_blocks'].get(int(custom_id), []))


def granted_by(item_id):
    """[(block, custom_id)] granted by an item template."""
    return list(_payload()['item_to_custom'].get(int(item_id), []))


def period_hours(item_id):
    """Native period for a timed customization item, or None when it is permanent."""
    return _payload()['period_by_item'].get(int(item_id))


def is_account_scoped(custom_id):
    """True when the native entry is account-wide instead of per character."""
    return int(custom_id) in _payload()['account_scoped']


def replace_targets(custom_id):
    """Native equivalent custom ids, so an alternate item keeps the look."""
    return list(_payload()['replace_map'].get(int(custom_id), []))


def slot_enum():
    """CUSTOMIZING_TYPE / CUSTOMIZING_DATA_TYPE values used by this table."""
    return dict(_payload()['enum_authority'])
