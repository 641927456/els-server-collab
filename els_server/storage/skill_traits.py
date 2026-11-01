"""Owned trait choices and atomic ED/scroll reset receipts."""
from contextlib import closing
import hashlib,sqlite3


def saved(db,uid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_skill_traits'").fetchone():return {}
    rows=db.execute('SELECT skill,note FROM character_skill_traits WHERE owner=? ORDER BY skill',(uid,)).fetchall()
    if any(type(s) is not int or s<1 or type(n) is not int or not 1<=n<=22 for s,n in rows):raise ValueError('Invalid saved skill trait')
    return dict(rows)


def choose(path,uid,account_id,payload,operation):
    from els_server.storage.character_schema import character_uid
    uid=character_uid(uid)
    if type(account_id) is not int or account_id<1:raise ValueError('Skill trait account identity')
    from els_server.domain.skill_traits import request,validate,acknowledgement,map_wire
    from els_server.storage.characters import Characters
    from els_server.storage.skill_unlocks import saved_groups
    skill,note=request(payload)
    if not isinstance(operation,str) or not 1<=len(operation)<=160:raise ValueError('Skill trait operation identity')
    digest=hashlib.sha256(str(uid).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Skill trait owner mismatch')
        row=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
        character=Characters._row(row);character['skill_seal_groups']=saved_groups(db,uid)
        from els_server.storage.ordinary_skill_pages import selected_page
        page=selected_page(db,uid)
        base=validate(character,skill,note)
        current=saved(db,uid)
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_trait_receipts'").fetchone():
            old=db.execute('SELECT request_hash,owner,skill FROM skill_trait_receipts WHERE operation=?',(operation,)).fetchone()
            if old:
                if old!=(digest,uid,base):raise ValueError('Conflicting skill trait retry')
                if base not in current:return acknowledgement(result=-1,page=page)
                return acknowledgement(base,current[base],page=page)
        if base in current and current[base]!=note:raise ValueError('Reset the existing skill trait first')
        character['skill_traits']=dict(current);character['skill_traits'][base]=note
        map_wire(character);ack=acknowledgement(base,note,page=page)
        db.execute('CREATE TABLE IF NOT EXISTS character_skill_traits (owner INTEGER NOT NULL REFERENCES characters(uid),skill INTEGER NOT NULL CHECK(skill>0),note INTEGER NOT NULL CHECK(note BETWEEN 1 AND 22),revision INTEGER NOT NULL,PRIMARY KEY(owner,skill))')
        db.execute('CREATE TABLE IF NOT EXISTS skill_trait_receipts (operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,skill INTEGER NOT NULL)')
        db.execute('INSERT INTO character_skill_traits VALUES (?,?,?,1) ON CONFLICT(owner,skill) DO UPDATE SET note=excluded.note,revision=revision+1 WHERE note<>excluded.note',(uid,base,note))
        db.execute('INSERT INTO skill_trait_receipts VALUES (?,?,?,?)',(operation,digest,uid,base))
        return ack


def reset(path,uid,account_id,payload,operation,*,prepare):
    from els_server.storage.character_schema import character_uid
    from els_server.storage.characters import Characters
    from els_server.storage.skill_unlocks import saved_groups
    from els_server.domain.skill_traits import reset_request,validate,reset_acknowledgement,reset_items,RESET_ED
    from els_server.storage.inventory_actions import _previous,_commit
    from els_server.storage.inventory_state import load_items
    from els_server.storage.equipment_receipt_state import current_changes
    from els_server.protocol.protocol_codec import encode_event
    uid=character_uid(uid)
    if type(account_id) is not int or account_id<1:raise ValueError('Skill trait account identity')
    skill,note,item_uid,use_ed=reset_request(payload)
    if not isinstance(operation,str) or not 1<=len(operation)<=160:raise ValueError('Skill trait reset operation identity')
    digest=hashlib.sha256(str(uid).encode()+b':'+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        from els_server.storage.item_actor import require_active_character
        require_active_character(db,uid)
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Skill trait owner mismatch')
        row=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
        character=Characters._row(row);character['skill_seal_groups']=saved_groups(db,uid)
        base=validate(character,skill,note)
        ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skill_trait_reset_receipts'").fetchone():
            old=db.execute('SELECT request_hash,owner,skill,note FROM skill_trait_reset_receipts WHERE operation=?',(operation,)).fetchone()
            if old:
                if old!=(digest,uid,base,note):raise ValueError('Conflicting trait reset retry')
                changes=[]
                if not use_ed:
                    positions=_previous(db,operation,digest)
                    if positions is None:raise ValueError('Trait scroll receipt missing')
                    changes=current_changes(db,operation,uid,0x55f,positions,load_items(db,uid))
                ack=reset_acknowledgement(base,note,ed,changes=changes,use_ed=use_ed)
                encode_event(ack);prepare(db);return ack
        if saved(db,uid).get(base)!=note:raise ValueError('Skill trait to reset is not selected')
        changes=[]
        if use_ed:
            if ed<RESET_ED:raise ValueError('Insufficient ED for trait reset')
            db.execute('UPDATE reward_balances SET ed=ed-?,revision=revision+1 WHERE uid=?',(RESET_ED,uid))
            ed-=RESET_ED
        else:
            before=load_items(db,uid);item=next((i for i in before if i['uid']==item_uid),None)
            if item is None or item['template'] not in reset_items() or item['group']!=4:raise ValueError('Owned forgetfulness scroll required')
            from els_server.domain.item_expiration import require_current
            from els_server.domain.item_locks import require_unlocked
            from els_server.storage.item_instances import remove
            require_current(item);require_unlocked(item)
            if item.get('sealed'):raise ValueError('Sealed forgetfulness scroll')
            position=(item['group'],item['slot'])
            if item['count']==1:remove(db,uid,item)
            else:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(uid,item_uid))
            after=load_items(db,uid);current=next((i for i in after if i['uid']==item_uid),None)
            changes=[(position,current)]
            _commit(db,operation,digest,uid,0x55f,[position],before,after)
        db.execute('DELETE FROM character_skill_traits WHERE owner=? AND skill=? AND note=?',(uid,base,note))
        ack=reset_acknowledgement(base,note,ed,changes=changes,use_ed=use_ed)
        encode_event(ack);prepare(db)
        db.execute('CREATE TABLE IF NOT EXISTS skill_trait_reset_receipts (operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,skill INTEGER NOT NULL,note INTEGER NOT NULL)')
        db.execute('INSERT INTO skill_trait_reset_receipts VALUES (?,?,?,?,?)',(operation,digest,uid,base,note))
        return ack
