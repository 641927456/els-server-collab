"""Atomic ordinary essence decrement for an owned equipped unsealed hyper."""
import sqlite3,struct,time
from contextlib import closing
from els_server.domain.boosting_2026_essence import ORDINARY,request,acknowledgement
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.boosting_2026_force_equipment import _character
from els_server.protocol.protocol_codec import Event,encode_event

def action(path,owner,account,payload,operation,*,now=None):
    skill=request(payload)
    if not isinstance(operation,str):raise ValueError('Essence operation identity')
    operation='ordinary-essence:'+operation;owner,digest=_identity(owner,0x460,payload,operation)
    if type(account) is not int or not 0<account<2**63:raise ValueError('Essence account')
    epoch=int(time.time()) if now is None else now
    if type(epoch) is not int or not 0<=epoch<2**40:raise ValueError('Essence epoch')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        character=_character(db,owner,account);old=_previous(db,operation,digest);items=load_items(db,owner)
        if old is not None:
            if db.execute('SELECT owner,kind FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()!=(owner,0x460):raise ValueError('Essence retry owner/kind')
            from els_server.domain.fashion_state import move_ack
            bypos={(i['group'],i['slot']):i for i in items}
            events=[acknowledgement(replayed=True),Event(0x201,kind=0x105,payload=move_ack([(p,bypos.get(p)) for p in old]))]
            for e in events:encode_event(e)
            return dict(replayed=True,events=events)
        from els_server.domain.skill_rules import learned_skills,equippable_skills,upgraded_slots
        from els_server.domain.skill_state import validate_slots
        from els_server.domain.character_rules import default_slots
        from els_server.game_data import client_data
        if skill not in learned_skills(character) or client_data().skill(skill)['m_eType']!=13:raise ValueError('Owned unsealed hyper skill required')
        row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(owner,)).fetchone()
        if row and len(row[0])!=88:raise ValueError('Saved skill preset size')
        slots=upgraded_slots(struct.unpack('>22i',row[0]),character) if row else default_slots(character)
        slots=validate_slots(slots,equippable_skills(character),character)
        if slots[20]!=skill:raise ValueError('Equipped hyper skill required')
        if character['revision']>=2**63-1:raise ValueError('Essence character revision overflow')
        balance=db.execute('SELECT revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()
        if balance is None or balance[0]>=2**63-1:raise ValueError('Essence balance revision overflow')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        eligible=[]
        for item in items:
            if item['template'] not in ORDINARY or item['group']!=4 or item.get('sealed'):continue
            try:require_current(item,now=epoch);require_unlocked(item,now=epoch)
            except ValueError:continue
            eligible.append(item)
        if not eligible:raise ValueError('Current unlocked ordinary essence required')
        # Native request names no UID. Earliest eligible bag slot is explicit
        # local selection policy; original retail item priority is unknown.
        source=min(eligible,key=lambda i:(i['slot'],i['uid']));position=(source['group'],source['slot'])
        remaining=dict(source,count=source['count']-1) if source['count']>1 else None
        event=acknowledgement([(position,remaining)]);encode_event(event)
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,source['uid']))
        else:
            # Inventory-instance helper covers the existing dependent metadata;
            # seal rows need explicit cleanup in this pinned parent version.
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_seals'").fetchone():db.execute('DELETE FROM item_seals WHERE item_uid=?',(source['uid'],))
            from els_server.storage.item_instances import remove
            remove(db,owner,source)
        db.execute('UPDATE characters SET revision=revision+1 WHERE uid=?',(owner,))
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x460,[position],[source],[remaining] if remaining else [])
        load_items(db,owner)
        return dict(replayed=False,events=[event])
