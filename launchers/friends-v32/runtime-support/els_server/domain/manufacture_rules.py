"""User-authorized compatibility crafting policy; numerical defaults are not retail data."""
import functools,json,hashlib,struct
from pathlib import Path
from dataclasses import replace
from els_server.game_data import client_data
from els_server.protocol.profession_messages import ProfessionState
DATA=Path(__file__).resolve().parents[1]/'data'

@functools.lru_cache(maxsize=1)
def policy():
    p=json.loads((DATA/'manufacture_policy.json').read_text(encoding='utf8'))
    if p['mode']!='compatibility-v1' or p['max_batch']!=99:raise ValueError('Unsupported crafting policy')
    if p['success_probability']!={'numerator':1,'denominator':1}:raise ValueError('Only guaranteed-success compatibility crafting is implemented')
    if any(type(v) is not int or not 1<=v<=99 for v in [p['default_output_quantity'],*p['quantity_overrides'].values()]):raise ValueError('Crafting output policy bound')
    if type(p['xp_per_required_level']) is not int or not 1<=p['xp_per_required_level']<=100000:raise ValueError('Crafting XP policy bound')
    if type(p['title_double_percent']) is not int or not 0<=p['title_double_percent']<=100:raise ValueError('Crafting title policy bound')
    if set(p['level_thresholds'])!={str(i) for i in range(1,10)} or any(type(v) is not int or not 1<=v<2**31 for v in p['level_thresholds'].values()):raise ValueError('Crafting level threshold policy bound')
    if p['quota']!={'recipe':10130467,'maximum':30,'reset':'Wednesday10:00UTC+8','scope':'character'}:raise ValueError('Unsupported crafting quota policy')
    return p

@functools.lru_cache(maxsize=1)
def inventory_definitions():
    raw=(DATA/'manufacture_inventory.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=policy()['inventory_sha256']:raise ValueError('Craft inventory identity')
    d=json.loads(raw)
    if d['client_sha256']!=client_data().manifest['client_sha256']:raise ValueError('Craft client mismatch')
    # Verify the same records in original row order using one immutable
    # catalog connection. Bound each IN query; do not populate the item LRU
    # with tens of thousands of rows used only for their record proof.
    from itertools import islice
    data=client_data();rows=iter(d['rows']);result={}
    with data.connect() as db:
        while chunk:=list(islice(rows,256)):
            ids=[]
            for row in chunk:
                # Malformed fields still fail at their original ordered
                # validation below, rather than masking an earlier bad SHA.
                try:template=row['template']
                except (KeyError,TypeError):continue
                if type(template) is int and -2**63<=template<2**63:ids.append(template)
            records={i:(record,stats,bonus) for i,record,stats,bonus in db.execute('SELECT id,record,stats,stat_bonus FROM items WHERE id IN ('+
                ','.join('?' for _ in ids)+')',ids)} if ids else {}
            for row in chunk:
                template=row['template']
                if type(template) is int and -2**63<=template<2**63:
                    if template not in records:raise ValueError(f'Unknown client item: {template}')
                    record,stats,bonus=records[template]
                    struct.unpack('<7f',stats);tuple(bonus)
                else:
                    # Preserve SQLite coercion and errors for legacy malformed
                    # keys; normal admitted rows use the bounded batch above.
                    record=data.item(template)['record']
                if hashlib.sha256(record).hexdigest()!=row['record_sha256']:raise ValueError('Craft item changed')
                result[template]=row
    return result

def inventory_fashion_records():
    """Transient static rows for startup classification, never player items."""
    from itertools import islice
    definitions=inventory_definitions()
    rows=iter(row for row in definitions.values() if row['group'] in (7,27))
    result={}
    with client_data().connect() as db:
        while chunk:=list(islice(rows,256)):
            ids=[row['template'] for row in chunk]
            records={i:(record,position,stats,bonus) for i,record,position,stats,bonus in db.execute(
                'SELECT id,record,equip_position,stats,stat_bonus FROM items WHERE id IN ('+
                ','.join('?' for _ in ids)+')',ids)}
            for row in chunk:
                template=row['template']
                if template not in records:raise ValueError(f'Unknown client item: {template}')
                record,position,stats,bonus=records[template]
                if hashlib.sha256(record).hexdigest()!=row['record_sha256']:raise ValueError('Craft item changed')
                result[template]=(record,position,stats,bonus)
    return result


def inventory_fashion_position(row):
    # Match data.item decoding at the original inventory-loop position.
    # Do not predecode later records before earlier classification failures.
    record,position,stats,bonus=row
    struct.unpack('<7f',stats);tuple(bonus)
    return position


@functools.lru_cache(maxsize=1)
def native_socket_data():
    raw=(DATA/'manufacture_sockets.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=policy()['sockets_sha256']:raise ValueError('Craft socket proof changed')
    d=json.loads(raw)
    return ({r['template']:r['capacity'] for r in d['custom']},
            {(r['costume'],r['item_type'],r['grade']):r['capacity'] for r in d['defaults']})

def socket_capacity(template):
    d=client_data().item(template)
    if d['item_type'] not in (1,2):raise ValueError('Socket equipment required')
    custom,defaults=native_socket_data()
    return custom.get(template,defaults[(int(bool(d['flags4']&1)),d['item_type'],(d['flags4']>>20)&15)])

@functools.lru_cache(maxsize=1)
def option_ids():
    from els_server.domain.sage_sockets import catalog
    from els_server.paths import PROJECT_ROOT
    ids=set()
    for s in catalog()['sources'][:2]:
        for c in json.loads((PROJECT_ROOT/s['path']).read_text(encoding='utf8'))['__symbolic_calls__']:
            d=c['arguments'][1]
            if d.get('TYPE')==1:ids.add(d['ID'])
    return frozenset(ids)

def validate_sockets(template,values):
    if not isinstance(values,(list,tuple)) or len(values)>socket_capacity(template) or any(type(x) is not int or x!=0 and x not in option_ids() for x in values):
        raise ValueError('Invalid original socket options/capacity')
    return list(values)

def xp_advance(state,minimum,quantity):
    """Compatibility: 10*recipe minimum per craft, thresholds100*2^(level-1)."""
    if state.profession!=3 or not minimum or state.level>=10:return state,0,False
    if not 1<=state.level<=10:raise ValueError('Invalid alchemist level')
    p=policy();delta=p['xp_per_required_level']*minimum*quantity
    if state.experience+delta>=2**31:raise ValueError('Profession XP overflow')
    level,progress=state.level,state.progress+delta
    required=state.required or p['level_thresholds'][str(level)]
    while level<10 and progress>=required:
        progress-=required;level+=1
        required=p['level_thresholds'].get(str(level),0)
    if level==10:progress=0;required=0
    return replace(state,level=level,experience=state.experience+delta,progress=progress,required=required),delta,level!=state.level

def output_quantity(recipe_id):
    return policy()['quantity_overrides'].get(str(recipe_id),policy()['default_output_quantity'])
