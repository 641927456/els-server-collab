"""Consume one owned career item and commit class/Artifact state atomically."""
from contextlib import closing
import hashlib,json,sqlite3,struct
from els_server.storage.characters import Characters
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.domain.careers import transition
from els_server.protocol.career_messages import use_request,use_ack

def use_career_item(path,uid,payload,operation_id,prepare_refresh=None):
    uid=character_uid(uid);item_uid=use_request(payload)
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=160:raise ValueError('Career operation identity')
    digest=hashlib.sha256(str(uid).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS career_receipts (operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, owner INTEGER NOT NULL, item_uid INTEGER NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL, response BLOB NOT NULL)')
        old=db.execute('SELECT request_hash,response FROM career_receipts WHERE operation_id=?',(operation_id,)).fetchone()
        if old:
            if old[0]!=digest:raise ValueError('Conflicting career retry')
            receipt=dict(response=old[1],replayed=True)
            if prepare_refresh is not None:receipt['prepared_events']=prepare_refresh(db,receipt)
            return receipt
        item=next((i for i in load_items(db,uid) if i['uid']==item_uid),None)
        if item is None or item['group']!=4:raise ValueError('Career item is not in owned consumable bag')
        from els_server.domain.item_expiration import require_current
        require_current(item)
        before,after=apply_transition(db,uid,item['template'])
        remaining=dict(item,count=item['count']-1) if item['count']>1 else None
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
        ack=use_ack([((item['group'],item['slot']),remaining)],item['template'],ed).payload
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,uid))
        else:
            from els_server.storage.item_expiration import forget
            forget(db,item_uid)
            db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item_uid,uid))
        db.execute('INSERT INTO career_receipts VALUES (?,?,?,?,?,?,?)',
            (operation_id,digest,uid,item_uid,json.dumps(before,sort_keys=True),json.dumps(after,sort_keys=True),ack))
        receipt=dict(response=ack,replayed=False,before=before,after=after)
        if prepare_refresh is not None:receipt['prepared_events']=prepare_refresh(db,receipt)
        return receipt


def apply_transition(db,uid,template):
    """Caller owns the transaction; shop and bag use the same state change."""
    return _apply_transition(db,uid,lambda before:transition(before,template))


def apply_quest_transition(db,uid,quest):
    from els_server.domain.job_quests import quest_transition
    return _apply_transition(db,uid,lambda before:quest_transition(before,quest))


def _apply_transition(db,uid,change):
    """Shared persistence and skill migration; caller supplies proven authority."""
    row=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
    before=Characters._row(row)
    from els_server.domain.relationship_skills import saved as relationship_saved
    before['relationship']=relationship_saved(db,uid)
    from els_server.storage.skill_expansion import is_expanded
    before['skill_row_expanded']=is_expanded(db,uid)
    from els_server.storage.skill_unlocks import saved_groups
    before['skill_seal_groups']=saved_groups(db,uid)
    artifact=db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',(uid,)).fetchone()
    before['artifact']=dict(zip(('template','evolution','level','experience','potentials'),artifact)) if artifact else None
    if artifact:before['artifact']['potentials']=json.loads(artifact[4])
    after=change(before)
    # A route change can remove or replace learned skills. Persist the
    # new layout in the same transaction as the class/item change so a
    # reconnect never reloads skills belonging to the previous route.
    saved_slots=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(uid,)).fetchone()
    if saved_slots:
        from els_server.domain.skill_rules import upgraded_slots,equippable_skills
        from els_server.domain.skill_state import encode_slots
        raw=bytes(saved_slots[0])
        if len(raw)!=88:raise ValueError('Invalid persisted skill slots')
        slots=struct.unpack('>22i',raw)
        from els_server.game_data import client_data
        from els_server.domain.character_rules import CLASSES
        from els_server.domain.role_progression import known_skills,first_master_skill
        known=known_skills(before['unit_class'])
        from els_server.domain.skill_expansion import unlocked_indices
        if any(s and s not in known for s in slots) or any(s for i,s in enumerate(slots) if i not in unlocked_indices(before)) or len([s for s in slots if s])!=len(set(s for s in slots if s)):
            raise ValueError('Invalid persisted career skills')
        slots=list(upgraded_slots(slots,after))
        if after['master'] and not before['master']:slots[21]=first_master_skill(after)
        visible=encode_slots(slots,equippable_skills(after),after)
        from els_server.domain.relationship_skills import persisted_slots
        migrated=struct.pack('>22i',*persisted_slots(struct.unpack('>22i',raw),struct.unpack('>22i',visible),after))
        db.execute('UPDATE skill_slots SET payload=?,revision=revision+1 WHERE uid=? AND payload<>?',(migrated,uid,migrated))
    db.execute('UPDATE characters SET unit_class=?,transcendence=?,master=?,revision=? WHERE uid=?',
               (after['unit_class'],after['transcendence'],after['master'],after['revision'],uid))
    if after['artifact'] and not before['artifact']:
        a=after['artifact'];db.execute('INSERT INTO character_artifacts VALUES (?,?,?,?,?,?)',
            (uid,a['template'],a['evolution'],a['level'],a['experience'],json.dumps(a['potentials'])))
    if after['master']:
        from els_server.storage.master_presets import mark
        mark(db,after)
    from els_server.storage.el_search_collection import career_changed
    career_changed(db,uid,after)
    return before,after
