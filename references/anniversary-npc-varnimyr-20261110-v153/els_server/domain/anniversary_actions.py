"""Permanent anniversary sit motions from the current native item table."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct

COUNT = 32
SUPPLEMENTAL_IDS = frozenset((721877, 721878, 721879))
DATA_SHA = '0de0bc7b39127f4c30ae02e483dade17a45f17b4cc8ef82e75b400a07eb6e524'
SUPPLEMENT_SHA = '2388e03e9464f2438de15ce0fe32dd51aafe3941b3569532e03bb1ea1972c9de'


@lru_cache(maxsize=1)
def supplemental_records():
    """Three exact official KIM records and their original referenced data."""
    raw = (Path(__file__).parents[1] / 'data/anniversary_action_records.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != SUPPLEMENT_SHA:
        raise ValueError('Anniversary supplemental item source changed')
    rows = json.loads(raw)
    result = {}
    for row in rows:
        record = bytes.fromhex(row['record_hex'])
        template, flags4, flags8 = struct.unpack_from('<III', record)
        if (len(record), template, flags4, flags8, record[16:20], record[164:168], record[196:200]) != (
                232, row['template'], 4202506, 112, bytes(4), bytes(4), bytes(4)):
            raise ValueError('Anniversary supplemental item identity')
        result[template] = row
    if result.keys() != SUPPLEMENTAL_IDS or len(rows) != len(result):
        raise ValueError('Anniversary supplemental item coverage')
    return result


def supplemental_item(template):
    row = supplemental_records()[template]
    record = bytes.fromhex(row['record_hex'])
    _, flags4, flags8 = struct.unpack_from('<III', record)
    return template, row['name'], flags4, flags8, 14, 0, 0, record, bytes(28), bytes(6)


@lru_cache(maxsize=1)
def books():
    from els_server.game_data import client_data

    raw = (Path(__file__).parents[1] / 'data/anniversary_actions.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != DATA_SHA:
        raise ValueError('Anniversary action catalog changed')
    rows = json.loads(raw)
    rules = {}
    client = client_data()
    for template, custom, unit, variant, sha in rows:
        item = client.item(template)
        if (item['item_type'], item['metadata'], item['record'][210], hashlib.sha256(item['record']).hexdigest()) != (14, 0, unit, sha):
            raise ValueError('Anniversary action book native identity')
        rules[template] = dict(book=template, custom_id=custom, custom_ids=[custom], type=7, slot=7,
                               unit_type=unit, units=[unit], variant=variant, ability_group=None,
                               native_item_sha256=sha)
    if len(rules) != COUNT or len({row['custom_id'] for row in rules.values()}) != COUNT:
        raise ValueError('Anniversary action coverage')
    return rules
