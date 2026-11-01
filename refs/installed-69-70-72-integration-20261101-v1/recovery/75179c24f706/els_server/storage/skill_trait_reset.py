"""Atomic native ED/scroll resets over the existing trait and inventory stores."""
import hashlib,sqlite3
from contextlib import closing
from els_server.storage.skill_traits import saved

def reset(path,uid,account_id,payload,operation,*,prepare):
    from els_server.storage.character_schema import character_uid
    from els_server.storage.characters import Characters
    from els_server.storage.skill_unlocks import saved_groups
    from els_server.domain.skill_trait_reset import reset_request,reset_acknowledgement,reset_items
    from els_server.domain.skill_traits import validate,RESET_ED
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
        if not use_ed:raise ValueError('Recovery only: fresh trait scroll is disabled')
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

