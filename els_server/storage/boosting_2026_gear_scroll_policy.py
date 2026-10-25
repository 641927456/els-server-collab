"""User-authorized local723680 reward policy,2026-10-24.

Not recovered CN event contents. No installer, player migration or packet route.
"""
import json,sqlite3,struct
from contextlib import closing
from itertools import product
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity
from els_server.storage.item_actor import require_active_character
from els_server.domain.boosting_2026_participation_gear import BOX,outputs_for
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_management import _updates

POLICY_ENABLED=True
LEGACY_POLICY_ENABLED=True
POLICY='user-authorized-723680-four-normal118259-20261024-v1'
AUTHORIZATION_SHA256='c66bced1e4f397a6746fbede01e9bff973d97364252aa18533db79a4c1ce4441'
SCROLL=118259

def actor(db,owner,account_id,prepare):
    if not callable(prepare):raise ValueError('Current selected lease callback required')
    prepare(db);require_active_character(db,owner)
    from els_server.storage.profession_state import require_owner
    require_owner(db,owner,account_id)
    row=db.execute('SELECT unit_class FROM characters WHERE uid=?',(owner,)).fetchone()
    if row is None:raise ValueError('Gift scroll current owner')
    return row[0]

def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS boosting2026_gear_scroll_receipts(
        original_operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,
        request_hash TEXT NOT NULL,source_uids_json TEXT NOT NULL,
        positions_json TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL)''')

def grant(db,owner,operation,digest,uids):
    ensure(db)
    if db.execute('SELECT 1 FROM boosting2026_gear_scroll_receipts WHERE original_operation=?',(operation,)).fetchone():
        raise ValueError('Gift scroll supplement already recorded')
    before=load_items(db,owner)
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    changed=grant_items(db,[dict(template=SCROLL,metadata=VERIFIED_TEMPLATES[SCROLL],group=TEMPLATE_BAG_GROUPS[SCROLL],quantity=4)],owner)
    after=load_items(db,owner);positions=[(i['group'],i['slot'])for i in changed]
    db.execute('INSERT INTO boosting2026_gear_scroll_receipts VALUES(?,?,?,?,?,?,?)',
        (operation,owner,digest,json.dumps(sorted(uids)),json.dumps(positions),json.dumps(before,sort_keys=True),json.dumps(after,sort_keys=True)))
    return positions

def attach_new(db,owner,account_id,operation,digest,uids,prepare):
    if not POLICY_ENABLED:return []
    actor(db,owner,account_id,prepare)
    if len(uids)!=4 or len(set(uids))!=4:raise ValueError('Four new armor instances required')
    return grant(db,owner,operation,digest,uids)

def legacy_proof(db,owner,account_id,operation,prepare):
    cls=actor(db,owner,account_id,prepare)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone():raise ValueError('No historical cube receipt')
    row=db.execute('SELECT request_hash,owner,kind,positions_json,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[1:3]!=(owner,0x196):raise ValueError('Historical cube owner/kind')
    before,after=json.loads(row[4]),json.loads(row[5]);old={i['uid']:i for i in before};new={i['uid']:i for i in after}
    if len(old)!=len(before)or len(new)!=len(after):raise ValueError('Duplicate historical inventory UIDs')
    consumed=[i for u,i in old.items()if i['template']==BOX and (u not in new or new[u].get('count')==i['count']-1)]
    if len(consumed)!=1:raise ValueError('Exactly one historical723680 decrement required')
    box=consumed[0]
    if box['group']!=4 or box['count']<1:raise ValueError('Historical box shape')
    remaining=dict(box,count=box['count']-1)if box['count']>1 else None
    if new.get(box['uid'])!=remaining:raise ValueError('Historical box decrement changed fields')
    hashes={_identity(owner,0x196,struct.pack('>i',BOX)+struct.pack('>QBBBIi',box['uid'],*flags,0,0),operation)[1]for flags in product((0,1),repeat=3)}
    if row[0]not in hashes:raise ValueError('Historical request is not exact723680 use')
    added=[i for u,i in new.items()if u not in old];outputs=outputs_for(cls)
    if len(added)!=4 or {i['template']for i in added}!={r['template']for r in outputs}:raise ValueError('Four original role output UIDs required')
    for i in added:
        out=next(r for r in outputs if r['template']==i['template'])
        if i['metadata']!=1 or i['group']!=1 or i['count']!=1 or i.get('enhancement')!=11 or i.get('durability')!=10000 or i.get('reforge')!=[21,100,0]or i.get('option_groups')!={'13':list(out['reforge_options'])}:raise ValueError('Historical armor not exact blank gift output')
    for u,i in old.items():
        if u!=box['uid']and new.get(u)!=i:raise ValueError('Historical unrelated inventory mutation')
    points=[tuple(p)for p in json.loads(row[3])]
    if set(points)!={(box['group'],box['slot']),*((i['group'],i['slot'])for i in added)}or len(points)!=5:raise ValueError('Historical cube affected positions')
    return row[0],added

def supplement(path,owner,account_id,original_operation,*,prepare):
    """Server-internal explicit reconciliation only; never scan or auto-migrate."""
    if not LEGACY_POLICY_ENABLED:raise ValueError('Local reconciliation policy is disabled')
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        digest,originals=legacy_proof(db,owner,account_id,original_operation,prepare)
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='boosting2026_gear_scroll_receipts'").fetchone()
        prior=db.execute('SELECT owner,request_hash,source_uids_json,positions_json,before_json,after_json FROM boosting2026_gear_scroll_receipts WHERE original_operation=?',(original_operation,)).fetchone()if exists else None
        if prior:
            if prior[:3]!=(owner,digest,json.dumps(sorted(i['uid']for i in originals))):raise ValueError('Supplement receipt identity conflict')
            old,new=json.loads(prior[4]),json.loads(prior[5]);affected={i['uid']for i in old+new if i['template']==SCROLL}
            current=load_items(db,owner);positions=list(dict.fromkeys([*(tuple(p)for p in json.loads(prior[3])),*((i['group'],i['slot'])for i in current if i['uid']in affected)]))
        else:
            current={i['uid']:i for i in load_items(db,owner)}
            for old in originals:
                now=current.get(old['uid'])
                if now is None or now['group']!=1 or {k:v for k,v in now.items()if k!='slot'}!={k:v for k,v in old.items()if k!='slot'}:raise ValueError('Original deficient armor no longer owned unchanged in bag')
            positions=grant(db,owner,original_operation,digest,[i['uid']for i in originals]);current=load_items(db,owner)
            balance=db.execute('SELECT revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
            if balance is None or balance[0]>=2**63-1:raise ValueError('Gift supplement revision bound')
            db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        current=load_items(db,owner);by={(i['group'],i['slot']):i for i in current};events=_updates([(p,by.get(p))for p in positions])
        for e in events:encode_event(e)
        actor(db,owner,account_id,prepare)
        return events

def reconcile_selected(session):
    """Normal successful227 arrival, including cold login; no packet replay."""
    if not LEGACY_POLICY_ENABLED:return []
    from els_server.domain.tenebros_capacity_flow import selected
    path,owner,account_id,prepare=selected(session)
    with closing(sqlite3.connect(path,timeout=10))as db:
        db.execute('BEGIN');actor(db,owner,account_id,prepare)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone():return []
        rows=db.execute('SELECT operation_id FROM inventory_action_receipts WHERE owner=? AND kind=? ORDER BY operation_id LIMIT 65',(owner,0x196)).fetchall()
        # Deliberately finite: unknown large legacy histories need separate
        # source review, never a blanket migration or guessed reward.
        if len(rows)>64:return []
        eligible=[]
        for operation, in rows:
            try:legacy_proof(db,owner,account_id,operation,prepare)
            except (ValueError,KeyError,TypeError):continue
            eligible.append(operation)
    answer=[]
    for operation in eligible:
        try:answer.extend(supplement(path,owner,account_id,operation,prepare=prepare))
        except (ValueError,KeyError,TypeError):continue
    return answer
