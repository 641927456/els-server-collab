"""Native104/105 wearing: owned positions, stable UIDs and connection receipts."""
from els_server.storage.item_actor import require_active_character
import hashlib,json,sqlite3,struct,uuid
from contextlib import closing
from els_server.domain.inventory_items import validate_item,FASHION_EQUIP_SLOTS,TEMPLATE_BAG_GROUPS
from els_server.domain.normal_equipment import definitions as normal_definitions
from els_server.domain.ordinary_accessories import definitions as accessory_definitions
from els_server.domain.equipment_requirements import catalog as requirements
from els_server.domain.fashion_state import move_ack
from els_server.domain.bag_capacity import wire_limit
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.bag_capacity import allowances

def request_positions(payload):
    if not isinstance(payload,bytes) or len(payload)!=11:raise ValueError('Wear request length')
    sg,ss,dg,ds,flag=struct.unpack('>BiBiB',payload);positions=((sg,ss),(dg,ds))
    slots=set(requirements()[1].values())|set(FASHION_EQUIP_SLOTS.values())|{s for r in accessory_definitions().values() for s in r['slots']}
    if flag or positions[0]==positions[1] or any(not (g in (1,2,7,27) and 0<=s<wire_limit(g) or g==9 and s in slots) for g,s in positions):raise ValueError('Wear request positions')
    if sg!=dg and sg!=9 and dg!=9:raise ValueError('Wear bag classification')
    return positions

def require_wearable(item,character):
    if item.get('sealed',False):raise ValueError('Unseal equipment before wearing')
    t=item['template']
    if t in normal_definitions():
        from els_server.domain.equipment_instance import require_wearable as require_normal
        require_normal(item,character)
    elif t in accessory_definitions():
        from els_server.domain.ordinary_accessories import require_wearable as require_accessory
        require_accessory(item,character)
    elif t in FASHION_EQUIP_SLOTS:
        from els_server.game_data import client_data
        from els_server.domain.equipment_requirements import class_matches
        raw=client_data().item(t)['record']
        if raw[0xd2] and raw[0xd2]!=character['unit_type'] or not class_matches(character['unit_class'],raw[0xd3]):raise ValueError('Fashion character requirement')
        if raw[8]&4 and character['unit_type']!=10:raise ValueError('Companion fashion requirement')
    else:raise ValueError('Outside ordinary wearable scope')

def move(path,payload,uid,*,account_id,session_id,sequence,validate=lambda:None,prepare=None):
    uid=character_uid(uid);source,destination=request_positions(payload)
    if type(account_id) is not int or account_id<=0 or type(session_id) is not str:raise ValueError('Wear account/session')
    connection=uuid.UUID(session_id)
    if connection.version!=4 or str(connection)!=session_id or type(sequence) is not int or not 1<=sequence<2**32:raise ValueError('Wear operation identity')
    operation=session_id+':wear104:'+str(uid)+':'+str(sequence)
    digest=hashlib.sha256(struct.pack('>Q',uid)+payload).hexdigest();positions_json=json.dumps((source,destination),separators=(',',':'))
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');require_active_character(db,uid);validate()
        if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Wear owner mismatch')
        row=db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?',(uid,)).fetchone()
        if row is None:raise ValueError('Wear character missing')
        character=dict(unit_type=row[0],unit_class=row[1],level=row[2])
        from els_server.game_data import client_data
        if client_data().unit(character['unit_class'])['unitType']!=character['unit_type']:raise ValueError('Wear actor class identity')
        limits=allowances(db,uid)
        if any(g!=9 and s>=limits[g] for g,s in (source,destination)):raise ValueError('Wear unowned bag position')
        before=load_items(db,uid);positions={(i['group'],i['slot']):i for i in before}
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wear_move_receipts'").fetchone()
        old=db.execute('SELECT owner,account_id,request_hash,positions_json FROM wear_move_receipts WHERE operation_id=?',(operation,)).fetchone() if exists else None
        if old is not None:
            if old!=(uid,account_id,digest,positions_json):raise ValueError('Wear receipt conflict')
            response=move_ack([(source,positions.get(source)),(destination,positions.get(destination))]);validate();return response
        first,second=positions.get(source),positions.get(destination)
        if first is None:raise ValueError('Wear empty source')
        from els_server.domain.item_expiration import require_current
        for item in (first,second):
            if item is None:continue
            require_current(item)
            t=item['template'];bag_only=source[0]==destination[0] and source[0]!=9
            if t not in normal_definitions() and t not in accessory_definitions() and t not in FASHION_EQUIP_SLOTS:
                # Existing artifact/chip bag1 rearrangement remains available.
                from els_server.domain.artifact_progression import slots as artifact_slots
                from els_server.domain.equipment_chip_rules import material as chip_material
                if not (bag_only and source[0]==1 and (artifact_slots(t) or chip_material(t))):raise ValueError('Wear item scope')
            if any(g!=9 and g!=TEMPLATE_BAG_GROUPS[t] for g,s in (source,destination)):raise ValueError('Wear item bag classification')
        moved=validate_item({**first,'group':destination[0],'slot':destination[1]})
        swapped=validate_item({**second,'group':source[0],'slot':source[1]}) if second else None
        for item in (moved,swapped):
            if item and item['group']==9:require_wearable(item,character)
        from els_server.domain.ring_wear import require_compatible
        projected={i['uid']:i for i in before};projected.update({i['uid']:i for i in (moved,swapped) if i})
        for item in (moved,swapped):
            if item:require_compatible(item,projected.values())
        changes=((source,swapped),(destination,moved))
        response=move_ack(changes)
        if prepare is not None:prepare(changes,character)
        validate()
        from els_server.storage.spell_socket_pending import invalidate_moved
        invalidate_moved(db,uid,[first,second],[moved,swapped])
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_engrave_previews'").fetchone():
            db.execute('DELETE FROM equipment_engrave_previews WHERE item_uid IN (SELECT uid FROM inventory_items WHERE owner=? AND uid IN (?,?))',(uid,first['uid'],second['uid'] if second else 0))
        for item in (first,second):
            if item and db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?',(-item['uid'],item['uid'],uid)).rowcount!=1:raise ValueError('Wear retained UID owner')
        for item in (moved,swapped):
            if item and db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE uid=? AND owner=?',(item['group'],item['slot'],item['uid'],uid)).rowcount!=1:raise ValueError('Wear position owner')
        after=load_items(db,uid);expected={i['uid']:i for i in before};expected.update({i['uid']:i for i in (moved,swapped) if i})
        if expected!={i['uid']:i for i in after}:raise ValueError('Wear changed item state')
        db.execute("CREATE TABLE IF NOT EXISTS wear_move_receipts (operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),account_id INTEGER NOT NULL,request_hash TEXT NOT NULL CHECK(length(request_hash)=64),positions_json TEXT NOT NULL)")
        db.execute('INSERT INTO wear_move_receipts VALUES (?,?,?,?,?)',(operation,uid,account_id,digest,positions_json));validate()
        return response
