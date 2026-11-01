"""Original camp outfit membership, Lu/Ciel priority and truncated wait."""
import functools,hashlib,json
from els_server.game_data import CLIENT_SHA,client_data
from els_server.paths import PROJECT_ROOT

@functools.lru_cache(maxsize=1)
def catalog():
    p=PROJECT_ROOT/'els_server/data/town_rest.json';raw=p.read_bytes();d=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=json.loads(p.with_suffix('.manifest.json').read_bytes())['payload_sha256']
        or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=client_data().manifest['catalog_sha256']):raise ValueError('Native camp outfit source')
    for group in d['groups']:
        for row in group['items']:
            if hashlib.sha256(client_data().item(row['template'])['record']).hexdigest()!=row['record_sha256']:raise ValueError('Native camp outfit template')
    return d

def minimum_wait():
    d=catalog();return min(int(d['base_wait_seconds']*g['multiplier'])for g in d['groups'])

def required(items,unit_class,unit_type,now):
    from els_server.domain.item_expiration import expired
    from els_server.domain.equipment_requirements import class_matches
    d=catalog();chosen=set();deadlines=[]
    groups={row['template']:g['division_group']for g in d['groups']for row in g['items']}
    for item in items:
        if item['group']!=9 or item['slot']not in ((35,36)if unit_type==10 else(35,)) or item['template']not in groups or expired(item,now=now):continue
        if not class_matches(unit_class,client_data().item(item['template'])['record'][0xd3]):continue
        chosen.add(groups[item['template']])
        if item.get('expires_at'):deadlines.append(item['expires_at'])
    # 2B53350 checks both Lu/Ciel onepiece slots and gives121 priority over120.
    group=121 if 121 in chosen else 120 if 120 in chosen else 0
    rate=next((g['multiplier']for g in d['groups']if g['division_group']==group),1.)
    # 2B521D0: double multiply then CVTTSD2SI;360*.7 truncates to251.
    return int(d['base_wait_seconds']*rate),min(deadlines)if deadlines else None

def saved_wait(session,db,token,now):
    row=db.execute('SELECT b.revision,c.revision,c.unit_class,c.unit_type FROM reward_balances b JOIN characters c ON c.uid=b.uid WHERE c.uid=?',(session.account.uid,)).fetchone()
    if row is None:raise ValueError('Camp selected character missing')
    # Ordinary104 wear moves preserve the economic and career revisions.
    # Include the two real positions so taking off an outfit cannot retain a
    # shorter wait, without loading the full inventory on every idle tick.
    wear=tuple(db.execute('SELECT uid,template,slot FROM inventory_items WHERE owner=? AND bag_group=9 AND slot IN (35,36) ORDER BY slot',(session.account.uid,)))
    identity=(row,wear)
    cached=getattr(session,'_town_rest_outfit',None)
    if cached and cached[:2]==(token,identity) and(cached[2]is None or now<=cached[2]):return cached[3]
    from els_server.storage.inventory_state import load_items
    seconds,until=required(load_items(db,session.account.uid),row[2],row[3],now)
    session._town_rest_outfit=(token,identity,until,seconds)
    return seconds
