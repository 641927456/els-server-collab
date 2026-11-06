"""Finite original reset-ticket definitions; no grant or reset operation policy."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA
DATA_SHA='d4f2efd8f35a895df498cc15958fd914c796e8c8c5072f14157baefc29ec898e'
@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/equipment_chip_reset_items.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Chip reset item evidence identity')
    c=json.loads(raw)
    if c['schema_version']!=1 or c['policy_id']!='chip-reset-items-layout-v1' or c['client_sha256']!=CLIENT_SHA:raise ValueError('Chip reset item build')
    if set(c['items'])!={str(x) for x in (118639,118640,118641,118642,118656,118657,118658,118659)}:raise ValueError('Chip reset finite scope')
    for row in c['items'].values():
        item=client_data().item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or item['metadata']!=row['metadata'] or (row['metadata'],row['group'],row['source_max_stack'])!=(2,4,300):raise ValueError('Chip reset original definition')
    return c
def ticket(template):return catalog()['items'].get(str(template))
