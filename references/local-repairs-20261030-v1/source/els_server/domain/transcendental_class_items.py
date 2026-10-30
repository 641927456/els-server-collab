"""Native transcendence and master-class item registrations.

Two native registrations answer different questions about the same item id:

  * `AddTranscendentalClassItem(item, stage)` — the item opens a transcendence
    stage (the client only ever passes 0, 1 or 2)
  * `AddMasterClassItem(item, UNIT_CLASS)` — the item advances one specific class

240 of the 242 master-class items are also registered as transcendental items,
so the two are merged into one `items` entry carrying both keys instead of
being deduplicated into a lossy single answer.

`careers.json` already carries 541 advancement rules, but it covers only 361 of
the 697 transcendental items and 60 of the 242 master-class items. This catalog
closes that gap. It is read-only: it says what an item unlocks and never grants
the unlock, and it does not decide whether the class is legal for the caller.
"""
import functools
import hashlib
import json

from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT

DATA = PROJECT_ROOT / 'els_server/data/transcendental_class_items.json'


@functools.lru_cache(maxsize=1)
def _payload():
    data = json.loads(DATA.read_text(encoding='utf8'))
    if data.get('client_sha256') != CLIENT_SHA:
        raise ValueError('Transcendental class client mismatch')
    for source in data.get('sources', []):
        path = PROJECT_ROOT / source['path']
        # The analysis artifacts ship in the runtime asset archive, not in git.
        # Verify them whenever they are present so drift cannot pass silently.
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Transcendental class source changed: %s' % source['path'])
    data['items'] = {int(k): v for k, v in data['items'].items()}
    return data


def items():
    """`{item_id: {'transcendental_stage': int?, 'master_unit_class': str?}}`."""
    return dict(_payload()['items'])


def item(item_id):
    """One entry, or None when the client does not register the item."""
    return _payload()['items'].get(int(item_id))


def stage(item_id):
    """Transcendence stage 0/1/2, or None when the item is not transcendental."""
    entry = item(item_id)
    return entry.get('transcendental_stage') if entry else None


def master_class(item_id):
    """Native UNIT_CLASS symbol, or None when the item is not a master-class item."""
    entry = item(item_id)
    return entry.get('master_unit_class') if entry else None


def items_with_stage(stage_index):
    """Sorted item ids registered for one transcendence stage."""
    wanted = int(stage_index)
    return tuple(sorted(item_id for item_id, entry in _payload()['items'].items()
                        if entry.get('transcendental_stage') == wanted))


def items_for_master_class(symbol):
    """Sorted item ids that advance `symbol`, with or without the table prefix."""
    wanted = symbol.rpartition('.')[-1]
    return tuple(sorted(item_id for item_id, entry in _payload()['items'].items()
                        if entry.get('master_unit_class') == wanted))


def master_classes():
    """`{UNIT_CLASS symbol: enum id}` for every class a master item advances."""
    return dict(_payload()['enum_authority']['UNIT_CLASS'])


def unit_types():
    """`{UNIT_TYPE symbol: enum id}` — only the types actually registered.

    The client UNIT_TYPE table also holds UT_NONE and UT_END; neither is
    registered as transcendental, so neither appears here.
    """
    return dict(_payload()['enum_authority']['UNIT_TYPE'])


def can_transcend(symbol):
    """Whether the client registers `symbol` as a transcendental unit type."""
    return symbol.rpartition('.')[-1] in unit_types()


def summary():
    return dict(_payload()['summary'])
