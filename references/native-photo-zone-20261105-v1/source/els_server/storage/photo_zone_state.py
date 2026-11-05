"""Character-owned map unlocks and one atomic original ticket consumption."""
from contextlib import closing
from pathlib import Path
import sqlite3,time
from els_server.domain.photo_zone_catalog import catalog
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.protocol import photo_zone_messages as wire
from els_server.protocol.protocol_codec import encode_event

TABLE='native_photo_zone_unlocks'
SQL='CREATE TABLE native_photo_zone_unlocks (owner INTEGER NOT NULL REFERENCES characters(uid),world INTEGER NOT NULL,account_id INTEGER NOT NULL,unlocked_at INTEGER NOT NULL,PRIMARY KEY(owner,world))'

def snapshot(db,owner,account):
    require_owner(db,owner,account)
    data=catalog();maps=data['maps']
    from els_server.storage.seal_quests import completed_ids
    completed=completed_ids(db,owner)
    opened={int(key)for key,row in maps.items()
        if not row.get('m_Lock')or row.get('m_QuestID')in completed}
    if db.execute("SELECT 1 FROM sqlite_master WHERE name=?AND type='table'",(TABLE,)).fetchone():
        for world,saved_account in db.execute('SELECT world,account_id FROM native_photo_zone_unlocks WHERE owner=?',(owner,)):
            if saved_account!=account or str(world)not in maps:raise ValueError('Studio saved map ownership')
            opened.add(world)
    return frozenset(opened)

def use(path,owner,account,payload,operation,guard):
    source,world=wire.unlock_request(payload)
    owner,digest=_identity(owner,0x5b8,payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_owner(db,owner,account);require_active_character(db,owner)
        stamp=int(time.time());before=load_items(db,owner)
        opened=snapshot(db,owner,account);previous=_previous(db,operation,digest)
        if previous is not None:
            if world not in opened:raise ValueError('Studio ticket receipt lost its saved map')
            answer=[wire.unlocked_ack(current_changes(db,operation,owner,0x5b8,previous,before)),wire.unlocked(opened)]
            for event in answer:encode_event(event)
            guard(db);return answer
        row=catalog()['maps'].get(str(world))
        if row is None or row.get('m_OnlyQuest')or not row.get('m_Lock')or world in opened:
            raise ValueError('Studio ticket requires a locked non-quest-only background')
        item=next((item for item in before if item['uid']==source),None)
        if item is None or item['template']not in catalog()['tickets']or item['count']<1:
            raise ValueError('Studio owned unlock ticket required')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        require_current(item,now=stamp);require_unlocked(item,now=stamp)
        if item.get('sealed')or item['metadata']!=catalog()['items'][str(item['template'])]['metadata']:
            raise ValueError('Studio ticket native state')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone():db.execute(SQL)
        db.execute('INSERT INTO native_photo_zone_unlocks VALUES(?,?,?,?)',(owner,world,account,stamp))
        if item['count']==1:remove(db,owner,item)
        else:
            if db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=?AND uid=?AND count=?',(owner,source,item['count'])).rowcount!=1:
                raise ValueError('Studio unlock ticket changed')
        after=load_items(db,owner);position=(item['group'],item['slot'])
        current=next((item for item in after if item['uid']==source),None)
        answer=[wire.unlocked_ack([(position,current)]),wire.unlocked(snapshot(db,owner,account))]
        for event in answer:encode_event(event)
        guard(db);require_active_character(db,owner)
        _commit(db,operation,digest,owner,0x5b8,[position],before,after)
        return answer
