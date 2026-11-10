"""Original166572 fixed seven-day accessory sets, by native character family."""
from pathlib import Path
from functools import lru_cache
import hashlib,json

DATA_SHA='7e467667b444c7ebc57175b89622e92166078492b18926c36b511011a20276d9'


@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/mentor_duelist_box.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Mentor duelist box source identity')
    data=json.loads(raw)
    from els_server.game_data import client_data,CLIENT_SHA
    c=client_data()
    if data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=c.manifest['catalog_sha256']:
        raise ValueError('Mentor duelist box client identity')
    rows=data['readers'];box=data['box'];groups={}
    for row in rows:
        item=c.item(row['template']);record=item['record']
        if (item['name']!=row['name']or item['metadata']!=0 or item['equip_position']!=row['equip_position']
                or record[210:212]!=bytes((row['unit_type'],row['required_class']))
                or hashlib.sha256(record).hexdigest()!=row['record_sha256']
                or(row['metadata'],row['group'],row['max_stack'])!=(0,2,1)):
            raise ValueError('Mentor duelist accessory original item')
        groups.setdefault(row['unit_type'],[]).append(dict(template=row['template'],quantity=1,inventory_days=7))
    with c.connect()as db:families=dict(db.execute('SELECT class_id,unit_type FROM units'))
    from els_server.domain.character_rules import CLASSES
    if (len(rows)!=64 or set(groups)!=set(range(1,16))
            or box['class_outputs']!={str(k):groups[families[k]]for k in CLASSES}
            or any(len(v)!=(8 if k==10 else 4)for k,v in groups.items())
            or box['template']!=166572 or box['selection_count']!=0):
        raise ValueError('Mentor duelist exact fixed role outputs')
    return data
