"""Atomic repair; gated by verified pricing context and transport ID."""
import hashlib,json,sqlite3
from contextlib import closing
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.profession_state import require_owner
from els_server.storage.reward_state import validate_balances
from els_server.storage.equipment_durability import replace_durability
from els_server.domain.normal_equipment import definitions
from els_server.domain.repair_pricing import character_quote
from els_server.protocol.repair_messages import request,acknowledgement


def repair(path,owner,payload,operation_id,*,account_id):
    owner=character_uid(owner);req=request(payload)
    if req['flag_a'] or req['flag_b']:raise ValueError('Unsupported repair mode')
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=160:raise ValueError('Repair operation identity')
    digest=hashlib.sha256(str(owner).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        require_owner(db,owner,account_id)
        row=db.execute('SELECT unit_type FROM characters WHERE uid=?',(owner,)).fetchone()
        if row is None:raise ValueError('Unknown repair owner')
        if row[0]!=10 and req['form']:raise ValueError('Foreign repair price side')
        balance=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
        items=load_items(db,owner)
        db.execute('''CREATE TABLE IF NOT EXISTS equipment_repair_receipts (
            operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
            owner INTEGER NOT NULL REFERENCES characters(uid), evidence_json TEXT NOT NULL)''')
        previous=db.execute('SELECT request_hash,owner FROM equipment_repair_receipts WHERE operation_id=?',(operation_id,)).fetchone()
        if previous:
            if previous!=(digest,owner):raise ValueError('Conflicting repair retry')
            return dict(replayed=True,response=acknowledgement(balance['ed']),balances=balance,
                        requires_inventory_sync=True,inventory=items)
        owned={i['uid']:i for i in items}
        if any(uid not in owned for uid in req['uids']):raise ValueError('Repair item not owned')
        selected=[owned[uid] for uid in req['uids']]
        from els_server.domain.item_expiration import require_current
        for item in selected:require_current(item)
        if any(i['template'] not in definitions() for i in selected):raise ValueError('Unsupported repair equipment')
        from els_server.storage.titles import character as title_character,snapshot as title_snapshot
        context=title_character(db,owner);context['title']=title_snapshot(db,owner)['title']
        if row[0]==10:
            from els_server.storage.luciel_state import state,active_state
            from els_server.domain.repair_pricing import price_side
            context['luciel_style']=state(db,owner)['style']
            context['luciel_active_unit']=active_state(db,owner)['active_unit']
            if req['form']!=price_side(context):raise ValueError('Stale LuCiel repair price side')
        quote=character_quote(selected,context,items);cost=quote['total_ed']
        if balance['ed']<cost:raise ValueError('Insufficient repair ED')
        changed=[]
        for item,q in zip(selected,quote['items']):
            if q['requires_repair']:
                updated=replace_durability(db,owner,item['uid'],q['current'],q['maximum'])
                changed.append(dict(item,durability=updated))
        if changed:
            if balance['revision']==2**63-1:raise ValueError('Repair revision overflow')
            balance=dict(balance,ed=balance['ed']-cost,revision=balance['revision']+1)
            db.execute('UPDATE reward_balances SET ed=?,revision=? WHERE uid=?',(balance['ed'],balance['revision'],owner))
        inventory=load_items(db,owner);response=acknowledgement(balance['ed'],changed)
        evidence=dict(ed_cost=cost,pricing='verified_default_equipment_effects',before=selected,after=changed,quote=quote)
        db.execute('INSERT INTO equipment_repair_receipts VALUES (?,?,?,?)',(operation_id,digest,owner,json.dumps(evidence,sort_keys=True)))
        return dict(replayed=False,response=response,balances=balance,inventory=inventory,
                    requires_inventory_sync=False,evidence=evidence)
