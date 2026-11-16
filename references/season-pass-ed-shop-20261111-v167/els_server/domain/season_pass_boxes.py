"""Current premium pass boxes consumed by the shared owned-box writer."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json

from els_server.game_data import CLIENT_SHA, client_data


DATA_SHA = 'cd8bb0c32c8dd8efb8a2cabe17f1c68deabea4a731231087d15be50e7f12eac2'


@lru_cache(maxsize=1)
def catalog():
    raw = (Path(__file__).resolve().parents[1] / 'data/season_pass_boxes.json').read_bytes()
    data = json.loads(raw)
    client = client_data()
    if (sha256(raw).hexdigest() != DATA_SHA or data['client_sha256'] != CLIENT_SHA
            or data['catalog_sha256'] != client.manifest['catalog_sha256']):
        raise ValueError('Current pass box source identity')
    for row in data['readers']:
        item = client.item(row['template'])
        if ((item['name'], item['metadata']) != (row['name'], row['metadata'])
                or sha256(item['record']).hexdigest() != row['record_sha256']):
            raise ValueError('Current pass box native reader identity')
    return data


@lru_cache(maxsize=1)
def boxes():
    return frozenset(row['template'] for row in catalog()['boxes'])


@lru_cache(maxsize=1)
def outputs():
    return frozenset(output['template'] for row in catalog()['boxes']
                     for output in row['class_outputs']['0'])


def authorize_output(template, source):
    if source is None or template not in outputs():
        return False
    from els_server.domain.raid_reward_items import validate_source
    source = validate_source(source)
    identity = json.loads(source._source)
    if (identity.get('policy') != 'owned-reward-boxes-20261031-v1'
            or identity.get('template') not in boxes()):
        return False
    from els_server.domain.owned_reward_boxes import authorize_output as owned_output
    return owned_output(template, source)
