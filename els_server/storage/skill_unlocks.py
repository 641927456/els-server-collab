"""Character seal ownership and idempotent native book consumption."""
from contextlib import closing
import hashlib,sqlite3
from els_server.protocol.career_messages import use_request,use_ack
from els_server.storage.inventory_state import load_items
from els_server.storage.character_schema import character_uid

def saved_groups(db,uid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_skill_seals'").fetchone():return ()
    return tuple(r[0] for r in db.execute('SELECT seal_group FROM character_skill_seals WHERE owner=? ORDER BY seal_group',(uid,)))

def owned_character(db,uid):
    from els_server.storage.characters import Characters
    row=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
    if row is None:raise ValueError('Unknown skill book owner')
    character=Characters._row(row);character['skill_seal_groups']=saved_groups(db,uid)
    return character

def apply_unlock(db,uid,group):
    """Buy-only skill service, inside the caller's debit/receipt transaction."""
    from els_server.domain.skill_unlocks import validate_unlock,unsealed_skills
    character=owned_character(db,uid);validate_unlock(character,group)
    previous=unsealed_skills(character)
    db.execute('CREATE TABLE IF NOT EXISTS character_skill_seals (owner INTEGER NOT NULL REFERENCES characters(uid), seal_group INTEGER NOT NULL CHECK(seal_group BETWEEN 1 AND 11), PRIMARY KEY(owner,seal_group))')
    db.execute('INSERT INTO character_skill_seals VALUES (?,?)',(uid,group))
    character['skill_seal_groups']=(*character['skill_seal_groups'],group)
    return character,previous

def purchase_notifications(db,uid,character,previous,replayed):
    from els_server.domain.skill_unlocks import unlock_notice
    from els_server.protocol.protocol_codec import Event
    if replayed:character=owned_character(db,uid);previous=()
    if character['uid']!=uid:raise ValueError('Skill book refresh owner mismatch')
    # A shop purchase replaces the accepted Camilla training task exactly like
    # a consumed manual; the absolute 2B snapshot removes the hidden task.
    from els_server.storage.seal_quests import state_in
    from els_server.protocol import quest_messages as quest_wire
    return [unlock_notice(character,previous),Event(0x201,kind=0x55b,payload=saved_initialization(db,character)),
            quest_wire.initialization(state_in(db,uid))]

def saved_initialization(db,character):
    import struct
    from els_server.storage.skill_expansion import is_expanded
    from els_server.domain.character_rules import default_slots
    from els_server.domain.skill_rules import upgraded_slots,learned_skills,equippable_skills
    from els_server.domain.skill_state import initialization_payload
    from els_server.domain.role_progression import known_skills
    character=dict(character,skill_row_expanded=is_expanded(db,character['uid']))
    from els_server.storage.skill_traits import saved as saved_traits
    character['skill_traits']=saved_traits(db,character['uid'])
    from els_server.storage.ordinary_skill_pages import view as skill_pages_view,_actor as skill_page_actor
    page_state=skill_pages_view(db,character['uid'])
    if page_state['count']>1:
        account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(character['uid'],)).fetchone()
        if account is None:raise ValueError('Skill page initialization owner')
        character.update(skill_page_actor(db,character['uid'],account[0]))
        character['ordinary_skill_pages']=page_state
    row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(character['uid'],)).fetchone()
    if row:
        if len(row[0])!=88:raise ValueError('Invalid saved skill preset size')
        old=struct.unpack('>22i',row[0]);known=known_skills(character['unit_class'])
        if any(s and s not in known for s in old):raise ValueError('Unknown saved skill')
        slots=upgraded_slots(old,character)
    else:slots=default_slots(character)
    return initialization_payload(slots,character['uid'],equippable_skills(character),learned_skills(character),character)

def use_skill_book(path,uid,payload,operation_id):
    from els_server.domain.skill_unlocks import catalog,validate_unlock,unlock_notice
    from els_server.storage.characters import Characters
    uid=character_uid(uid);item_uid=use_request(payload)
    if not isinstance(operation_id,str) or not 1<=len(operation_id)<=160:raise ValueError('Skill unlock operation identity')
    digest=hashlib.sha256(str(uid).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        old=None
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_book_receipts'").fetchone():
            old=db.execute('SELECT request_hash,bag_group,slot FROM skill_book_receipts WHERE operation_id=?',(operation_id,)).fetchone()
        if old:
            if old[0]!=digest:raise ValueError('Conflicting skill book retry')
            current=next((i for i in load_items(db,uid) if (i['group'],i['slot'])==old[1:]),None)
            ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
            row=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
            character=Characters._row(row);character['skill_seal_groups']=saved_groups(db,uid)
            from els_server.storage.seal_quests import state_in
            return dict(replayed=True,response=use_ack([(old[1:],current)],ed=ed).payload,
                        initialization=saved_initialization(db,character),quest_state=state_in(db,uid))
        item=next((i for i in load_items(db,uid) if i['uid']==item_uid),None)
        rule=catalog()['books'].get(str(item['template'])) if item else None
        if rule is None:return None
        if item['group']!=4:raise ValueError('Skill book outside owned consumable inventory')
        from els_server.domain.item_expiration import require_current
        require_current(item)
        row=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
        character=Characters._row(row);character['skill_seal_groups']=saved_groups(db,uid)
        group=rule['seal_group'];validate_unlock(character,group)
        from els_server.domain.skill_unlocks import unsealed_skills
        previous=unsealed_skills(character)
        character['skill_seal_groups']=(*character['skill_seal_groups'],group)
        # Serialize every outgoing state before committing inventory or ownership.
        notification=unlock_notice(character,previous)
        initialization=saved_initialization(db,character)
        remaining=dict(item,count=item['count']-1) if item['count']>1 else None
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
        response=use_ack([((item['group'],item['slot']),remaining)],item['template'],ed).payload
        db.execute('CREATE TABLE IF NOT EXISTS character_skill_seals (owner INTEGER NOT NULL REFERENCES characters(uid), seal_group INTEGER NOT NULL CHECK(seal_group BETWEEN 1 AND 11), PRIMARY KEY(owner,seal_group))')
        db.execute('INSERT INTO character_skill_seals VALUES (?,?)',(uid,group))
        if remaining:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(item_uid,uid))
        else:
            from els_server.storage.item_expiration import forget
            forget(db,item_uid);db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item_uid,uid))
        db.execute('CREATE TABLE IF NOT EXISTS skill_book_receipts (operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, owner INTEGER NOT NULL, item_uid INTEGER NOT NULL, template INTEGER NOT NULL, bag_group INTEGER NOT NULL, slot INTEGER NOT NULL)')
        db.execute('INSERT INTO skill_book_receipts VALUES (?,?,?,?,?,?,?)',(operation_id,digest,uid,item_uid,item['template'],item['group'],item['slot']))
        # The manual replaces the Camilla training task: native HIDE_QUEST_SKILL
        # marks it hidden once the group is owned, so drop it in this writer and
        # hand the client one authoritative quest snapshot.
        from els_server.storage.seal_quests import state_in
        return dict(replayed=False,response=response,notification=notification,initialization=initialization,
                    quest_state=state_in(db,uid))
