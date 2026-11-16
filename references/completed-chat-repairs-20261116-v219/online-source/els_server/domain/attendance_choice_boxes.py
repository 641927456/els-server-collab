"""Original current-CN attendance choices for already registered reward items."""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import CLIENT_SHA,client_data

DATA_SHA='72c9a5cd48b5fa8916917c576da31df8f7e98ad55521b5d7d5dfc9a6059c0ecd'


@functools.lru_cache(maxsize=1)
def _data():
    raw=(Path(__file__).resolve().parents[1]/'data/attendance_choice_boxes.json').read_bytes()
    data=json.loads(raw);client=client_data()
    if (hashlib.sha256(raw).hexdigest()!=DATA_SHA or data['client_sha256']!=CLIENT_SHA
        or data['catalog_sha256']!=client.manifest['catalog_sha256']):
        raise ValueError('Attendance choice box source identity')
    for row in (*data['boxes'],*data['outputs']):
        item=client.item(row['template'])
        if ((item['name'],item['metadata'])!=(row['name'],row['metadata'])
            or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):
            raise ValueError('Attendance choice box item identity')
    return data


@functools.lru_cache(maxsize=1)
def catalog():
    return MappingProxyType({row['template']:MappingProxyType(row)for row in _data()['boxes']})


def inventory_definitions():
    data=_data()
    return tuple(row for row in data['outputs']if row['template']in data['new_reader_templates'])
