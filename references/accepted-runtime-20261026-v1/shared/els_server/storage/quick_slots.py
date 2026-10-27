"""Current-build item shortcut bindings, independent of inventory locations.

23546D0/DB1910: 202/8A1 = i32 type, map<i32 slot,i32 binding>.
2278410: 201/8A2 = i32 result, i32 type, same map.
3055590: 201/8A0 = normal map, secondary map. Type 1 is normal.
The six-slot local allowance is preserved; secondary bindings are not enabled.
"""
import sqlite3,struct
from contextlib import closing
from els_server.protocol.protocol_codec import Event
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items
from els_server.domain.quick_bindings import item_binding, binding_ids
from els_server.domain.bag_capacity import LOCAL_QUICK_SLOTS


def empty():return {s:0 for s in range(LOCAL_QUICK_SLOTS)}


def validate(values):
    if not isinstance(values,dict) or set(values)!=set(range(LOCAL_QUICK_SLOTS)):
        raise ValueError('Quick bindings require every owned slot')
    if any(type(k) is not int or type(v) is not int or v<0 or (v and v not in binding_ids()) for k,v in values.items()):
        raise ValueError('Invalid quick item binding')
    return dict(values)


def encode(values):
    values=validate(values)
    return struct.pack('>I',len(values))+b''.join(struct.pack('>ii',k,v) for k,v in sorted(values.items()))


def decode(payload):
    if not isinstance(payload,bytes) or len(payload)!=8+8*LOCAL_QUICK_SLOTS:
        raise ValueError('Quick binding request length')
    kind,count=struct.unpack_from('>iI',payload)
    if kind!=1 or count!=LOCAL_QUICK_SLOTS:raise ValueError('Unsupported quick binding type/count')
    rows=[struct.unpack_from('>ii',payload,8+8*i) for i in range(count)]
    if len(dict(rows))!=count:raise ValueError('Duplicate quick binding key')
    return validate(dict(rows))


def _load(db,uid):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quick_bindings'").fetchone():return empty()
    values=empty()
    values.update(db.execute('SELECT slot,binding FROM character_quick_bindings WHERE owner=?',(uid,)))
    return validate(values)


def load(path,uid=1001):
    uid=character_uid(uid)
    with closing(sqlite3.connect(path,timeout=10)) as db:return _load(db,uid)


def initialization(path,uid=1001):
    # Explicit zeros are necessary: 3061520 looks for existing free map keys.
    from els_server.storage.pet_support import automatic_binding_map
    return Event(0x201,kind=0x8a0,payload=encode(load(path,uid))+automatic_binding_map(path,uid))


def acknowledgement(values=None,result=0):
    return Event(0x201,kind=0x8a2,payload=struct.pack('>ii',result,1)+encode(empty() if values is None else values))


def save_request(path,payload,uid=1001):
    uid=character_uid(uid);values=decode(payload)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM characters WHERE uid=?',(uid,)).fetchone():raise ValueError('Unknown quick binding owner')
        before=_load(db,uid)
        owned={item_binding(i['template']) for i in load_items(db,uid) if i['group']==6}
        # Retain/move a previously saved shortcut after its stack is exhausted.
        # New bindings require an owned consumable. Duplicate templates in
        # different slots are supported by the native registration callback.
        if set(values.values())-{0}-owned-set(before.values()):raise ValueError('Unowned quick item')
        if values!=before:
            db.execute('CREATE TABLE IF NOT EXISTS character_quick_bindings (owner INTEGER NOT NULL REFERENCES characters(uid), slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 5), binding INTEGER NOT NULL CHECK(binding>=0), PRIMARY KEY(owner,slot))')
            db.executemany('INSERT INTO character_quick_bindings VALUES (?,?,?) ON CONFLICT(owner,slot) DO UPDATE SET binding=excluded.binding',[(uid,k,v) for k,v in sorted(values.items())])
        return acknowledgement(values)
