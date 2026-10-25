"""Account-shared capacity, current-character ED, atomic native receipt.

Ownership/+1 are explicit local policy. No existing option data is migrated.
The two additive tables appear only after a successful first expansion.
"""
from contextlib import closing
from pathlib import Path
import sqlite3,struct
from els_server.protocol import tenebros_capacity_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.npc_trade import balances,charge

COST=2000000
POLICY='tenebros-account-capacity-local-20261024-v1'
SCHEMAS={
 'account_tenebros_capacity': 'CREATE TABLE account_tenebros_capacity (account_id INTEGER PRIMARY KEY CHECK(account_id>=1), body INTEGER NOT NULL CHECK(body BETWEEN 0 AND 3), leg INTEGER NOT NULL CHECK(leg BETWEEN 0 AND 3), hand INTEGER NOT NULL CHECK(hand BETWEEN 0 AND 3), foot INTEGER NOT NULL CHECK(foot BETWEEN 0 AND 3), revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 12))',
 'tenebros_capacity_receipts': 'CREATE TABLE tenebros_capacity_receipts (operation TEXT PRIMARY KEY, digest TEXT NOT NULL, account_id INTEGER NOT NULL REFERENCES account_tenebros_capacity(account_id), owner INTEGER NOT NULL CHECK(owner>=1001), part INTEGER NOT NULL CHECK(part BETWEEN 0 AND 3), before_extra INTEGER NOT NULL CHECK(before_extra BETWEEN 0 AND 2), after_extra INTEGER NOT NULL CHECK(after_extra=before_extra+1), before_ed INTEGER NOT NULL CHECK(before_ed>=2000000), after_ed INTEGER NOT NULL CHECK(after_ed=before_ed-2000000), wallet_revision INTEGER NOT NULL CHECK(wallet_revision>=1), revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 12), UNIQUE(account_id,revision))',
}


def schema(db,*,create=False):
    found=dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name IN (?,?)",tuple(SCHEMAS)))
    if found and found!=SCHEMAS:raise ValueError('Tenebros incompatible schema')
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name IN (?,?)",tuple(SCHEMAS)).fetchone():
        raise ValueError('Tenebros unexpected trigger')
    if not found and create:
        for sql in SCHEMAS.values():db.execute(sql)
    return bool(found) or create


def read(db,account_id):
    wire.integer(account_id,1,2**63-1)
    if not schema(db):return dict(extras=(0,0,0,0),revision=0)
    saved=db.execute('SELECT body,leg,hand,foot,revision FROM account_tenebros_capacity WHERE account_id=?',(account_id,)).fetchone()
    receipts=db.execute('SELECT operation,digest,owner,part,before_extra,after_extra,before_ed,after_ed,wallet_revision,revision FROM tenebros_capacity_receipts WHERE account_id=? ORDER BY revision',(account_id,)).fetchall()
    if saved is None:
        if receipts:raise ValueError('Tenebros orphan receipts')
        return dict(extras=(0,0,0,0),revision=0)
    extras=wire.capacities(saved[:4]);revision=wire.integer(saved[4],1,12)
    if sum(extras)!=revision or len(receipts)!=revision:raise ValueError('Tenebros capacity history')
    history=[0,0,0,0]
    for number,r in enumerate(receipts,1):
        operation,digest,owner,part,before,after,old_ed,new_ed,wallet_revision,rev=r
        wire.integer(owner,1001,2**63-1);wire.integer(part,0,3)
        wire.integer(before,0,2);wire.integer(after,1,3)
        wire.integer(old_ed,COST,2**63-1);wire.integer(new_ed,0,2**63-1)
        wire.integer(wallet_revision,1,2**63-1)
        _,expected=_identity(owner,0x9f2,struct.pack('>Qi',account_id,part),operation)
        if (digest!=expected or rev!=number or before!=history[part] or after!=before+1
                or new_ed!=old_ed-COST):raise ValueError('Tenebros receipt transition')
        history[part]=after
    if tuple(history)!=extras:raise ValueError('Tenebros receipt projection')
    return dict(extras=extras,revision=revision)


def guard(db,owner,account_id,prepare,*,npc=False):
    if not db.in_transaction or not callable(prepare):raise ValueError('Tenebros transaction context')
    prepare(db);require_active_character(db,owner);require_owner(db,owner,account_id)
    if npc:
        from els_server.domain.town_dialogue import catalog
        from els_server.domain.town_travel import require_destination
        from els_server.storage.seal_quests import load_character,completed_ids
        from els_server.storage.local_state import TOWN_SCENES
        if catalog()['npc_bindings']['10381']!=dict(houses=[40271],towns={'20013':1023}) or TOWN_SCENES.get(20013)!=1023:
            raise ValueError('Tenebros original NPC service binding')
        if db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()!=(20013,):
            raise ValueError('Tenebros NPC town')
        records={r[0] for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(owner,))}
        require_destination(20013,load_character(db,owner,account_id),completed_ids(db,owner),records)


def snapshot(path,owner,account_id,*,prepare):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('BEGIN');guard(db,owner,account_id,prepare)
        current=read(db,account_id)
        guard(db,owner,account_id,prepare)
        return current


def perform(path,owner,account_id,payload,operation,*,prepare,encode=None):
    part=wire.request(payload)
    wire.integer(account_id,1,2**63-1)
    owner,digest=_identity(owner,0x9f2,struct.pack('>Qi',account_id,part),operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db,owner,account_id,prepare,npc=True)
        if encode is None:
            def encode(part,extra,ed):
                from els_server.storage.tenebros_storage import cells
                extras=read(db,account_id)['extras']
                return wire.acknowledge(part,extra,ed,options=cells(db,owner,account_id,extras)[part])
        current=read(db,account_id);wallet=balances(db,owner)
        old=db.execute('SELECT digest,account_id,owner,part FROM tenebros_capacity_receipts WHERE operation=?',(operation,)).fetchone() if schema(db) else None
        if old is not None:
            if old!=(digest,account_id,owner,part):raise ValueError('Tenebros conflicting retry')
            reply=encode(part,current['extras'][part],wallet['ed']);encode_event(reply)
            guard(db,owner,account_id,prepare,npc=True)
            return [reply]
        extra=current['extras'][part]
        if extra>=3 or wallet['ed']<COST:raise ValueError('Tenebros maximum or insufficient ED')
        ed=charge(db,owner,wallet,COST)
        extras=list(current['extras']);extras[part]+=1;revision=current['revision']+1
        schema(db,create=True)
        db.execute('INSERT INTO account_tenebros_capacity VALUES (?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET body=excluded.body,leg=excluded.leg,hand=excluded.hand,foot=excluded.foot,revision=excluded.revision',(account_id,*extras,revision))
        db.execute('INSERT INTO tenebros_capacity_receipts VALUES (?,?,?,?,?,?,?,?,?,?,?)',(operation,digest,account_id,owner,part,extra,extra+1,wallet['ed'],ed,wallet['revision']+1,revision))
        if read(db,account_id)!=dict(extras=tuple(extras),revision=revision) or balances(db,owner)!=dict(wallet,ed=ed,revision=wallet['revision']+1):
            raise ValueError('Tenebros exact committed effect')
        reply=encode(part,extra+1,ed);encode_event(reply)
        guard(db,owner,account_id,prepare,npc=True)
        return [reply]
