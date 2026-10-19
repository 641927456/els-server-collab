"""Atomic ordinary 104/105 slot moves; no payload-only replay cache."""
import json,sqlite3,struct
from contextlib import closing
from els_server.domain.inventory_items import validate_item
from els_server.domain.equipment_requirements import catalog as requirements
from els_server.domain.equipment_instance import require_wearable
from els_server.domain.normal_equipment import definitions
from els_server.domain.fashion_state import move_ack
from els_server.domain.bag_capacity import NATIVE_LIMIT
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.storage.bag_capacity import allowances


def request_positions(payload):
    if not isinstance(payload,bytes) or len(payload)!=11:raise ValueError('Equipment move request length')
    sg,ss,dg,ds,flag=struct.unpack('>BiBiB',payload);positions=((sg,ss),(dg,ds))
    if flag!=0 or positions[0]==positions[1] or 1 not in (sg,dg):raise ValueError('Unsupported equipment move')
    slots=set(requirements()[1].values())
    for g,s in positions:
        if not ((g==1 and 0<=s<NATIVE_LIMIT) or (g==9 and s in slots)):raise ValueError('Equipment move slot')
    return positions


def move_equipment(path,payload,uid=1001):
    uid=character_uid(uid);source,destination=request_positions(payload)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT unit_class,level FROM characters WHERE uid=?',(uid,)).fetchone()
        if row is None:raise ValueError('Unknown equipment owner')
        character=dict(unit_class=row[0],level=row[1]);limit=allowances(db,uid)[1]
        if any(g==1 and s>=limit for g,s in (source,destination)):raise ValueError('Unowned bag position')
        items=load_items(db,uid);by_pos={(i['group'],i['slot']):i for i in items}
        first,second=by_pos.get(source),by_pos.get(destination)
        if first is None:raise ValueError('Equipment source empty')
        from els_server.domain.item_expiration import require_current
        for item in (first,second):
            if item:require_current(item)
        # Existing wearable Artifacts share bag1 with ordinary equipment.
        # Wear routes retain the original ordinary-equipment admission gate.
        from els_server.domain.artifact_progression import slots as artifact_slots
        from els_server.domain.equipment_chip_rules import material as chip_material
        bag_only=source[0]==destination[0]==1
        if any(i and i['template'] not in definitions() and not (bag_only and (artifact_slots(i['template']) or chip_material(i['template']))) for i in (first,second)):raise ValueError('Non-normal equipment move')
        moved=validate_item({**first,'group':destination[0],'slot':destination[1]})
        swapped=validate_item({**second,'group':source[0],'slot':source[1]}) if second else None
        for item in (moved,swapped):
            if item and item['group']==9:require_wearable(item,character)
        response=move_ack([(source,swapped),(destination,moved)])
        # A paid engraving preview belongs to the old physical position.
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_engrave_previews'").fetchone():
            db.execute('DELETE FROM equipment_engrave_previews WHERE item_uid IN (SELECT uid FROM inventory_items WHERE owner=? AND uid IN (?,?))',
                       (uid,first['uid'],second['uid'] if second else 0))
        # Keep the same UID rows: deleting a parent cascades opened sockets
        # and any other UID-owned state even when its foreign key is deferred.
        for old_item in (first,second):
            if old_item:db.execute('UPDATE inventory_items SET slot=? WHERE uid=? AND owner=?',(-old_item['uid'],old_item['uid'],uid))
        for item in (moved,swapped):
            if item:db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE uid=? AND owner=?',(item['group'],item['slot'],item['uid'],uid))
        after=load_items(db,uid)
        stable=lambda rows:sorted(({k:v for k,v in i.items() if k not in ('group','slot')} for i in rows),key=lambda i:i['uid'])
        if stable(after)!=stable(items):raise ValueError('Equipment move changed item data')
        db.execute('CREATE TABLE IF NOT EXISTS equipment_moves (id INTEGER PRIMARY KEY, owner INTEGER NOT NULL, request BLOB NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL)')
        db.execute('INSERT INTO equipment_moves(owner,request,before_json,after_json) VALUES (?,?,?,?)',(uid,payload,json.dumps([first,second],sort_keys=True),json.dumps([swapped,moved],sort_keys=True)))
        return response
