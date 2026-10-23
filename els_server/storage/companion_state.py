"""Owner-scoped companions; activation consumption and receipts commit together."""
import hashlib,json,secrets,sqlite3
from contextlib import closing
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import ensure_inventory,load_items
from els_server.domain.companions import catalog
from els_server.protocol import companion_messages as wire

def ensure(db):
    ensure_inventory(db)
    db.execute('CREATE TABLE IF NOT EXISTS companions (uid INTEGER PRIMARY KEY,owner INTEGER NOT NULL,kind TEXT NOT NULL CHECK(kind IN (\'pet\',\'mount\')),unit INTEGER NOT NULL,name TEXT NOT NULL,source_item INTEGER NOT NULL,UNIQUE(owner,kind,name))')
    db.execute('CREATE TABLE IF NOT EXISTS companion_active (owner INTEGER PRIMARY KEY,pet INTEGER NOT NULL DEFAULT 0,mount INTEGER NOT NULL DEFAULT 0,mounted INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS companion_receipts (owner INTEGER NOT NULL,operation TEXT NOT NULL,digest TEXT NOT NULL,kind INTEGER NOT NULL,response BLOB NOT NULL,PRIMARY KEY(owner,operation))')
    from els_server.storage.pet_progression import ensure as progression
    progression(db)

def rows(db,owner,kind=None):
    sql='SELECT uid,owner,kind,unit,name,source_item FROM companions WHERE owner=?';args=[owner]
    if kind:sql+=' AND kind=?';args.append(kind)
    result=[dict(zip(('uid','owner','kind','unit','name','source_item'),r)) for r in db.execute(sql+' ORDER BY uid',args)]
    from els_server.storage.boosting_2026_limited_pet import attach as attach_limited
    attach_limited(db,owner,result)
    from els_server.storage.pet_support import attach
    attach(db,owner,result)
    from els_server.storage.pet_progression import attach as attach_progression
    attach_progression(db,owner,result)
    from els_server.storage.mount_state import attach as attach_mount
    attach_mount(db,owner,result)
    return result

def snapshot(path,owner,*,enter_world=False):
    owner=character_uid(owner)
    with closing(sqlite3.connect(path,timeout=10)) as db:
        with db:
            ensure(db)
            from els_server.storage.boosting_2026_limited_pet import present,expire_active,clear_pending,TABLE
            if present(db) and db.execute('SELECT 1 FROM '+TABLE+' WHERE owner=?',(owner,)).fetchone():
                if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
                expire_active(db,owner)
                if enter_world:clear_pending(db,owner)
            # Fresh login restores ownership and the active pet. The original
            # scene starts on foot; riding requires a new native 42C request.
            if enter_world:
                from els_server.storage.mount_state import login as mount_login
                mount_login(db,owner)
                db.execute('UPDATE companion_active SET mount=0,mounted=0 WHERE owner=?',(owner,))
            active=db.execute('SELECT pet,mount,mounted FROM companion_active WHERE owner=?',(owner,)).fetchone() or (0,0,0)
            if enter_world:
                from els_server.storage.pet_progression import clock
                clock(db,owner,active[0])
            return {'companions':rows(db,owner),'pet':active[0],'mount':active[1],'mounted':bool(active[2])}

def handle(path,owner,kind,payload,operation,*,randbelow=secrets.randbelow,account_id=None):
    if kind in (0x42c,0x42f):
        from els_server.storage.mount_state import handle as mount_handle
        return mount_handle(path,owner,kind,payload,operation)
    owner=character_uid(owner)
    if kind==0x2e8:
        from els_server.storage.boosting_2026_limited_pet import activate
        limited=activate(path,owner,payload,operation,account_id=account_id)
        if limited is not None:return limited
    if not isinstance(operation,str) or not 1<=len(operation)<=160:raise ValueError('Invalid companion operation')
    digest=hashlib.sha256(kind.to_bytes(4,'big')+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            from els_server.storage.item_actor import require_active_character
            require_active_character(db,owner)
            if account_id is not None:
                from els_server.storage.profession_state import require_owner
                require_owner(db,owner,account_id)
            ensure(db)
            old=db.execute('SELECT digest,kind,response FROM companion_receipts WHERE owner=? AND operation=?',(owner,operation)).fetchone()
            if old:
                if old[0]!=digest:raise ValueError('Conflicting companion retry')
                if kind==0x2ec:
                    from els_server.storage.boosting_2026_limited_pet import reconcile_summon
                    current=reconcile_summon(db,owner,payload)
                    if current is not None:db.commit();return current
                db.commit();return wire.event(old[1],old[2])
            if kind in (0x2e8,0x432):
                typ='pet' if kind==0x2e8 else 'mount'
                item_uid,name=wire.create_pet_request(payload) if typ=='pet' else (wire.uid_request(payload),'')
                item=next((i for i in load_items(db,owner) if i['uid']==item_uid),None)
                if item is None or item['group']!=4:raise ValueError('Owned activation item required')
                from els_server.domain.item_expiration import require_current
                from els_server.domain.item_locks import require_unlocked
                require_current(item);require_unlocked(item)
                spec=catalog()[typ].get(item['template'])
                if spec is None or spec['duration']!=-1:raise ValueError('Unsupported activation item')
                pool=spec['outcomes'];total=sum(w for _,w in pool);roll=randbelow(total)
                if type(roll) is not int or not 0<=roll<total:raise ValueError('Invalid companion random source')
                for unit,weight in pool:
                    if roll<weight:break
                    roll-=weight
                uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
                if not 0<uid<2**63-1:raise ValueError('Companion UID limit')
                if typ=='mount':name=f'Mount{uid}'
                if db.execute('SELECT 1 FROM companions WHERE owner=? AND kind=? AND name=?',(owner,typ,name)).fetchone():raise ValueError('Companion name already exists')
                if len(rows(db,owner,typ))>=1000:raise ValueError('Companion capacity reached')
                companion=dict(uid=uid,owner=owner,kind=typ,unit=unit,name=name,source_item=item_uid)
                db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,))
                db.execute('INSERT INTO companions VALUES (?,?,?,?,?,?)',tuple(companion[k] for k in ('uid','owner','kind','unit','name','source_item')))
                original=dict(item);updates=[];removed=None
                if item['count']==1:
                    from els_server.storage.item_expiration import forget
                    forget(db,item_uid);db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?',(item_uid,owner));removed=original
                else:
                    item['count']-=1;db.execute('UPDATE inventory_items SET count=? WHERE uid=? AND owner=?',(item['count'],item_uid,owner));updates.append(item)
                delta=wire.inventory_delta(updates,removed)
                response=wire.activation_ack(typ,0,companion,delta)
                db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
            else:
                db.execute('INSERT OR IGNORE INTO companion_active(owner) VALUES (?)',(owner,))
                if kind==0x2ec:
                    uid=wire.uid_request(payload,zero=True);typ='pet'
                    companion=next((p for p in rows(db,owner,typ) if p['uid']==uid),None)
                    if uid and companion is None:raise ValueError('Owned pet required')
                    from els_server.storage.boosting_2026_limited_pet import require_current,clear_pending
                    if companion:require_current(companion)
                    clear_pending(db,owner)
                    db.execute('UPDATE companion_active SET pet=? WHERE owner=?',(uid,owner))
                    from els_server.storage.pet_progression import clock
                    clock(db,owner,uid)
                    response=wire.pet_summon(0,companion)
                elif kind in (0x42c,0x42f):
                    if kind==0x42c:
                        if len(payload)!=9 or payload[8] not in (0,1):raise ValueError('Invalid mount summon')
                    elif len(payload)!=12 or payload[8:]!=bytes(4):raise ValueError('Invalid mount dismount')
                    uid=wire.uid_request(payload[:8],zero=kind==0x42c);typ='mount'
                    companion=next((p for p in rows(db,owner,typ) if p['uid']==uid),None)
                    if uid and companion is None:raise ValueError('Owned mount required')
                    if kind==0x42c:
                        if not uid:raise ValueError('Owned mount required')
                        db.execute('UPDATE companion_active SET mount=?,mounted=1 WHERE owner=?',(uid,owner))
                        response=wire.mount_summon(0,owner,companion)
                    else:
                        # D79C10 sends its CURRENT mounted UID and zero. Its
                        # bool/next-UID arguments only queue a subsequent 42C.
                        active=db.execute('SELECT mount FROM companion_active WHERE owner=?',(owner,)).fetchone()[0]
                        if uid!=active or companion is None:raise ValueError('Current mounted companion required')
                        db.execute('UPDATE companion_active SET mount=0,mounted=0 WHERE owner=?',(owner,))
                        response=wire.mount_ride(0,uid,companion)
                else:raise ValueError('Unknown companion operation')
            db.execute('INSERT INTO companion_receipts VALUES (?,?,?,?,?)',(owner,operation,digest,response.kind,response.payload))
            db.commit();return response
        except BaseException:
            db.rollback();raise
