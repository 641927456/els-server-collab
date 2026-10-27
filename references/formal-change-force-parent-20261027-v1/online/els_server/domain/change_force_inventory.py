"""Finite original type-18 rank-1 change-force books from 360 native recipes."""
import functools
import hashlib
import json
from pathlib import Path

REGISTRY_SHA = 'a113941b7ae34703c144d4e0ac336d3b5a563ea7f3d27f2467f36d1f3ca66077'
CLIENT_SHA = '6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'


@functools.lru_cache(maxsize=1)
def catalog():
    path = Path(__file__).resolve().parents[1] / 'data/change_force_books.json'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRY_SHA:
        raise ValueError('Original type18 change registry checksum')
    source = json.loads(raw)
    if (source['schema_version'] != 1 or source['client_sha256'] != CLIENT_SHA
        or source['original_elpage_sha256'] != 'c6bc76e3a9613752f007b25b068ed34913e83c2d9981f9fc8b6395390f6ee9ac'
        or len(source['rows']) != 360):
        raise ValueError('Original type18 source identity')
    from els_server.game_data import client_data
    from els_server.domain.el_search_collection import classes
    data = client_data()
    roles = classes()
    result = {}
    by_skill = set()
    for row in source['rows']:
        item = row['item']
        role = roles.get(row['unit_class'])
        if (type(item) is not int or item in result or row['skill'] in by_skill
            or row['rank'] != 1 or row['recipe'] != item
            or (row['material'], row['cost']) not in ((135911, 500000), (136174, 5000000))
            or role is None or role['job_stage'] != 3 or (role['unit_type'], role['line']) != (row['unit_type'], row['line'])
            or data.skill(row['skill'])['m_eType'] != 18
            or hashlib.sha256(data.item(item)['record']).hexdigest() != row['record_sha256']):
            raise ValueError('Original type18 row identity')
        by_skill.add(row['skill'])
        result[item] = row
    if (len(result) != 360 or {row['material'] for row in result.values()} != {135911, 136174}):
        raise ValueError('Original type18 coverage')
    return result


def by_skill():
    return {row['skill']: row for row in catalog().values()}


def for_character(template, character):
    row = catalog().get(template)
    if row is None or character['unit_class'] != row['unit_class'] or character['unit_type'] != row['unit_type']:
        raise ValueError('Change force requires the exact native third-job branch')
    if character['level'] < 99:
        raise ValueError('Change force requires level 99')
    return row
