"""The approved fashion catalogue for the daily hidden-dungeon voucher."""

from functools import lru_cache
import hashlib
import json
from pathlib import Path

from els_server.game_data import CLIENT_SHA, client_data


VOUCHER = 719756
POLICY = 'hidden-fashion-daily-20261110-v1'
DATA_SHA = '845a1728204a8f33abf13a047d1540e129a6e941895d72f9ab11bd697a8f9af3'


@lru_cache(maxsize=1)
def catalogue():
    raw = Path(__file__).resolve().parents[1].joinpath('data/hidden_fashion.json').read_bytes()
    data = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != DATA_SHA or (data['client_sha256'], data['token']) != (CLIENT_SHA, VOUCHER):
        raise ValueError('Hidden fashion catalogue identity')
    data['boxes'] = {int(template): row for template, row in data['boxes'].items()}
    native = client_data()
    for row in (*data['definitions'], *data['boxes'].values()):
        item = native.item(row['template'])
        if (item['name'], item['metadata'], hashlib.sha256(item['record']).hexdigest()) != (row['name'], row['metadata'], row['record_sha256']):
            raise ValueError('Hidden fashion native item identity')
    return data


def authorize_voucher(source):
    if source is None:
        return False
    from els_server.domain.raid_reward_items import validate_source
    source = validate_source(source)
    identity = json.loads(source._source)
    if source.kind != 'ordinary' or identity.get('policy') != POLICY:
        return False
    source.validate_template(VOUCHER)
    return True
