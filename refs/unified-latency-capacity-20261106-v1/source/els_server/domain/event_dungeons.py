"""Pinned event specifications. Importing this module does not open an entry."""
import functools
import hashlib
import json
from els_server.game_data import CLIENT_SHA, client_data
from els_server.paths import PROJECT_ROOT


@functools.lru_cache(maxsize=1)
def catalog():
    directory = PROJECT_ROOT / 'els_server/data'
    raw = (directory / 'event_dungeons.json').read_bytes()
    manifest = json.loads((directory / 'event_dungeons.manifest.json').read_text('utf8'))
    if (manifest['schema_version'] != 1 or manifest['client_sha256'] != CLIENT_SHA
            or hashlib.sha256(raw).hexdigest() != manifest['payload_sha256']):
        raise ValueError('Event specification identity')
    result = json.loads(raw)
    source = client_data()
    if result['catalog_sha256'] != source.manifest['catalog_sha256']:
        raise ValueError('Event client catalog identity')
    if set(result['events']) != {'41550', '41580', '41620'}:
        raise ValueError('Unreviewed event entry')
    for key, event in result['events'].items():
        definition = source.dungeon(int(key))
        tickets = [v for v in definition['requireItemID'].values() if v]
        if (definition['dataFileName'] != event['source'] or tickets != event['tickets']
                or definition['requireItemCount'] != event['ticket_count']
                or definition['m_MinLevel'] != event['minimum_level']
                or definition['m_MaxLevel'] != event['maximum_level']
                or 1 not in definition['DUNGEON_CHECK_CONDITION'].values()):
            raise ValueError('Event admission source changed')
    for key, ticket in result['tickets'].items():
        native = source.item(int(key))
        if (native['metadata'] != ticket['metadata']
                or hashlib.sha256(native['record']).hexdigest() != ticket['record_sha256']
                or ticket['bag_group'] != 4):
            raise ValueError('Event ticket source changed')
    return result


def is_reviewed(identity):
    return type(identity) is int and identity in (41550, 41580, 41620)


def definition(identity):
    if type(identity) is not int or str(identity) not in catalog()['events']:
        raise ValueError('Event is not in the reviewed ticket path')
    return catalog()['events'][str(identity)]
