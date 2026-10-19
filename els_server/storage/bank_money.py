"""Shared bank ED and character ED move atomically, with absolute retry replies."""
import sqlite3
from contextlib import closing
from els_server.storage.bank_state import account_for,capacity
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.npc_trade import balances
from els_server.domain.bank_rules import TIERS,ED_LIMITS,player_ed_limit
from els_server.protocol.bank_messages import money_request,money_ack


def balance(db,owner):
    account=account_for(db,owner)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='shared_bank_balances'").fetchone():return 0,0
    row=db.execute('SELECT ed,revision FROM shared_bank_balances WHERE account_id=?',(account,)).fetchone()
    ed,revision=row or (0,0)
    if any(type(n) is not int or not 0<=n<2**63 for n in (ed,revision)) or ed>ED_LIMITS[TIERS.index(capacity(db,owner,16))]:
        raise ValueError('Invalid persisted shared ED balance')
    return ed,revision


def transfer(path,owner,payload,operation):
    deposit,amount=money_request(payload)
    owner,digest=_identity(owner,0x7d7,payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');account=account_for(db,owner)
        old=_previous(db,operation,digest);character=balances(db,owner);bank_ed,revision=balance(db,owner)
        if old is not None:return money_ack(deposit,bank_ed,character['ed'])
        if character['revision']>=2**63-1 or revision>=2**63-1:raise ValueError('Shared ED revision limit')
        bank_after=bank_ed+amount if deposit else bank_ed-amount
        player_after=character['ed']-amount if deposit else character['ed']+amount
        if not 0<=bank_after<=ED_LIMITS[TIERS.index(capacity(db,owner,16))] or player_after<0:
            raise ValueError('Insufficient ED or bank capacity limit')
        if not deposit:
            # The native dialog looks up level -> max ED at service+480.
            row=(db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='characters'").fetchone() else (1,))
            if row is None or player_after>player_ed_limit(row[0]):raise ValueError('Character ED carrying limit')
        db.execute('''CREATE TABLE IF NOT EXISTS shared_bank_balances (
            account_id INTEGER PRIMARY KEY CHECK(account_id>0),
            ed INTEGER NOT NULL CHECK(ed BETWEEN 0 AND 70000000000),
            revision INTEGER NOT NULL CHECK(revision>=0))''')
        db.execute('INSERT INTO shared_bank_balances VALUES (?,?,?) ON CONFLICT(account_id) DO UPDATE SET ed=excluded.ed,revision=excluded.revision',(account,bank_after,revision+1))
        db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=?',(player_after,owner))
        wire=money_ack(deposit,bank_after,player_after)
        _commit(db,operation,digest,owner,0x7d7,[],
            [dict(character_ed=character['ed'],shared_ed=bank_ed)],
            [dict(character_ed=player_after,shared_ed=bank_after)])
        return wire
