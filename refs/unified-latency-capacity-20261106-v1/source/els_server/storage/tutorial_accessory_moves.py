"""Owned finite accessory moves; current-state retry and precommit encoding."""
import hashlib,json,sqlite3,struct,uuid
from contextlib import closing
from els_server.domain.tutorial_accessory import TEMPLATES,SLOT_STYLE,require_wearable,definition
from els_server.domain.inventory_items import validate_item
from els_server.domain.fashion_state import move_ack
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.bag_capacity import allowances
from els_server.domain.bag_capacity import NATIVE_LIMIT

def request_positions(payload):
    if not isinstance(payload,bytes) or len(payload)!=11:raise ValueError('Accessory move size')
    sg,ss,dg,ds,flag=struct.unpack('>BiBiB',payload)
    if flag!=0 or ({sg,dg}!={2,9} and (sg,dg)!=(9,9)):raise ValueError('Accessory move groups')
    positions=((sg,ss),(dg,ds))
    if positions[0]==positions[1]:raise ValueError('Accessory source equals destination')
    if any(g==2 and not 0<=s<NATIVE_LIMIT or g==9 and s not in SLOT_STYLE for g,s in positions):raise ValueError('Accessory position')
    return positions

def move(path,payload,uid,*,account_id,session_id,sequence,validate=lambda:None):
    uid=character_uid(uid);source,destination=request_positions(payload)
    if type(account_id) is not int or account_id<=0:raise ValueError('Accessory account')
    if type(session_id) is not str:raise ValueError('Accessory connection identity')
    connection=uuid.UUID(session_id)
    if connection.version!=4 or str(connection)!=session_id or type(sequence) is not int or not 1<=sequence<2**32:raise ValueError('Accessory operation identity')
    operation=session_id+':accessory104:'+str(uid)+':'+str(sequence)
    digest=hashlib.sha256(struct.pack('>Q',uid)+payload).hexdigest()
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate()
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Accessory owner mismatch')
        row=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(uid,)).fetchone()
        if row is None:raise ValueError('Accessory character missing')
        character=dict(unit_type=row[0],unit_class=row[1],level=row[2])
        if character['unit_type']==10:
            from els_server.storage.luciel_state import state,active_state
            character.update(luciel_style=state(db,uid)['style'],luciel_active_unit=active_state(db,uid)['active_unit'])
        capacity=allowances(db,uid)[2]
        if any(g==2 and s>=capacity for g,s in (source,destination)):raise ValueError('Accessory unowned bag position')
        before=load_items(db,uid);positions={(i['group'],i['slot']):i for i in before}
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tutorial_accessory_receipts'").fetchone()
        old=db.execute('SELECT owner,request_hash,positions_json FROM tutorial_accessory_receipts WHERE operation_id=?',(operation,)).fetchone() if exists else None
        if old is not None:
            if old!=(uid,digest,json.dumps((source,destination),separators=(',',':'))):raise ValueError('Accessory receipt conflict')
            reply=move_ack([(source,positions.get(source)),(destination,positions.get(destination))]);validate();return reply
        first,second=positions.get(source),positions.get(destination)
        if first is None:raise ValueError('Accessory empty source')
        from els_server.domain.item_expiration import require_current
        from els_server.domain.item_locks import require_unlocked
        for item in (first,second):
            if item is None:continue
            if item['template'] not in TEMPLATES:raise ValueError('Outside accessory scope')
            definition(item['template']);require_current(item);require_unlocked(item)
        moved=validate_item({**first,'group':destination[0],'slot':destination[1]})
        swapped=validate_item({**second,'group':source[0],'slot':source[1]}) if second else None
        for item in (moved,swapped):
            if item and item['group']==9:require_wearable(item,character)
        response=move_ack([(source,swapped),(destination,moved)]);validate()
        # Preserve UID-owned expiry/lock and any referencing row during swaps.
        for item in (first,second):
            if item:db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?',(-item['uid'],item['uid'],uid))
        for item in (moved,swapped):
            if item:db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE uid=? AND owner=?',(item['group'],item['slot'],item['uid'],uid))
        after=load_items(db,uid)
        stable=lambda rows:sorted(({k:v for k,v in i.items() if k not in ('group','slot')} for i in rows),key=lambda i:i['uid'])
        if stable(after)!=stable(before):raise ValueError('Accessory mutated item state')
        db.execute("CREATE TABLE IF NOT EXISTS tutorial_accessory_receipts (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),request_hash TEXT NOT NULL CHECK(typeof(request_hash)='text' AND length(request_hash)=64 AND request_hash NOT GLOB '*[^0-9a-f]*'),positions_json TEXT NOT NULL CHECK(typeof(positions_json)='text'))")
        db.execute('INSERT INTO tutorial_accessory_receipts VALUES (?,?,?,?)',(operation,uid,digest,json.dumps((source,destination),separators=(',',':'))));validate()
        return response
