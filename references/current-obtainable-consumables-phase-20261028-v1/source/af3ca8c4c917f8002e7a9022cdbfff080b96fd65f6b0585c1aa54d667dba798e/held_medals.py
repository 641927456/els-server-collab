"""Current box medals, sampled once inside the original ordinary reward writer.

Holding semantics and 50% come from the pinned current item descriptions.
Additive combination with existing elixir percentages is a human-approved local
rule, not a claim about an unrecovered retail stacking formula.
"""
import functools,hashlib,json,time

RULES={190414:('experience','404be57df63b2ab1a44f623af011216be524f8876a9166873a5cbaebbe12258f'),
       190416:('drop','19f65556a41195350378a2b18031c485e2506ec890825932b5c0e3896c5bd8b1')}
TABLE='held_medal_reward_facts'
SQL='CREATE TABLE held_medal_reward_facts(operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),dungeon INTEGER NOT NULL,kind TEXT NOT NULL,context_sha256 TEXT NOT NULL,basis_points INTEGER NOT NULL,settled_at INTEGER NOT NULL,snapshot_json TEXT NOT NULL)'

@functools.lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    for template,(kind,digest)in RULES.items():
        r=client_data().item(template)
        if hashlib.sha256(r['record']).hexdigest()!=digest or (r['item_type'],r['metadata'],VERIFIED_TEMPLATES.get(template),TEMPLATE_BAG_GROUPS.get(template))!=(7,0,0,4):
            raise ValueError('Current held medal source definition')
    return RULES

def _validate(snapshot,owner,kind,amount,when):
    from els_server.domain.item_expiration import validate
    if type(snapshot)is not list or len(snapshot)>1 or type(amount)is not int or amount not in(0,5000)or bool(snapshot)!=bool(amount):raise ValueError('Held medal reward snapshot')
    for row in snapshot:
        expected={'owner','uid','template','metadata','count','group','slot','expires_at','record_sha256'}
        if type(row)is not dict or set(row)!=expected:raise ValueError('Held medal source shape')
        rule=definitions().get(row['template'])
        if rule is None or rule!=(kind,row['record_sha256'])or row['owner']!=owner or(row['metadata'],row['count'],row['group'])!=(0,1,4):raise ValueError('Held medal source identity')
        if any(type(row[k])is not int or row[k]<0 for k in('owner','uid','template','metadata','count','group','slot','expires_at'))or not row['uid']or when>validate(row['expires_at']):raise ValueError('Held medal source deadline')

def bonus(db,owner,identity,kind,operation,context,*,already_issued=False,now=None):
    from els_server.domain.elixir_economy import eligible
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.bank_state import account_for
    if not db.in_transaction or type(owner)is not int or type(identity)is not int or kind not in('experience','drop')or type(operation)is not str or not 1<=len(operation)<=200 or type(context)is not dict:raise ValueError('Held medal original reward transaction')
    require_active_character(db,owner);account_for(db,owner)
    digest=hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()
    prior=db.execute('SELECT owner,dungeon,kind,context_sha256,basis_points,settled_at,snapshot_json FROM held_medal_reward_facts WHERE operation=?',(operation,)).fetchone()if exists else None
    if prior:
        if prior[:4]!=(owner,identity,kind,digest):raise ValueError('Changed held medal reward receipt')
        _validate(json.loads(prior[6]),owner,kind,prior[4],prior[5]);return prior[4]
    if already_issued or not eligible(identity):return 0
    when=int(time.time())if now is None else now
    if type(when)is not int or not 0<when<2**31:raise ValueError('Held medal reward clock')
    from els_server.storage.inventory_state import load_items
    from els_server.domain.item_expiration import expired
    rules=definitions()
    held=[i for i in load_items(db,owner)if i['template']in rules and rules[i['template']][0]==kind and i['group']==4 and 'expires_at'in i and not expired(i,now=when)]
    held.sort(key=lambda i:(i['expires_at'],i['slot'],i['uid']))
    # Only the two admitted50% medals are supported. Duplicate copies never
    # accumulate. Other historical medal IDs acquire no new reader/source.
    selected=held[:1];amount=5000 if selected else 0
    snapshot=[{**{k:i[k]for k in('uid','template','metadata','count','group','slot','expires_at')},'owner':owner,'record_sha256':rules[i['template']][1]}for i in selected]
    _validate(snapshot,owner,kind,amount,when)
    # Freeze zero too: inventory changes cannot revise this operation later.
    db.execute(SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
    db.execute('INSERT INTO held_medal_reward_facts VALUES(?,?,?,?,?,?,?,?)',(operation,owner,identity,kind,digest,amount,when,json.dumps(snapshot,sort_keys=True,separators=(',',':'))))
    return amount
