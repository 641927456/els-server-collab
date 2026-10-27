"""Atomic source-bound ED/EP conversion and read-only owned wallet."""
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.ep_conversion import Rate, policy, ConversionRejected, ConversionResult
from els_server.domain.ep_points import validate, MAX_EP
from els_server.storage.character_schema import character_uid
from els_server.storage.ep_points import balance, credit
from els_server.storage.reward_state import validate_balances
from els_server.protocol.ep_conversion_messages import request, acknowledgement


def _exists(db, name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS ep_conversion_receipts (
        owner INTEGER NOT NULL REFERENCES characters(uid),
        operation_id TEXT NOT NULL, account_id INTEGER NOT NULL CHECK(account_id>0),
        request_sha256 TEXT NOT NULL, rate_sha256 TEXT NOT NULL,
        ed_cost INTEGER NOT NULL CHECK(ed_cost>0), ep_gain INTEGER NOT NULL CHECK(ep_gain>0),
        PRIMARY KEY(owner,operation_id))''')


def convert(path, payload, operation_id, *, account_id, uid):
    quantity = request(payload)
    uid = character_uid(uid)
    if type(account_id) is not int or not 1 <= account_id < 2**63:
        raise ValueError('Invalid EP account')
    if type(operation_id) is not str or not 1 <= len(operation_id) <= 100:
        raise ValueError('Invalid server operation identity')
    digest = hashlib.sha256(payload).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw', uri=True, timeout=10)) as db:
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            owned = db.execute('SELECT 1 FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?', (uid, account_id)).fetchone()
            if owned is None:
                raise ConversionRejected(ConversionResult.UNKNOWN_CHARACTER)
            _active_character(db,uid)
            money = validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?', (uid,)).fetchone())
            ep = balance(db, uid)
            old = (db.execute('SELECT account_id,request_sha256 FROM ep_conversion_receipts WHERE owner=? AND operation_id=?', (uid, operation_id)).fetchone()
                   if _exists(db, 'ep_conversion_receipts') else None)
            if old is not None:
                if old != (account_id, digest):
                    raise ValueError('Conflicting EP conversion retry')
                # A delayed retry must not restore historical balances. A
                # committed operation remains replayable after rate removal.
                event = acknowledgement(money['ed'], ep)
                db.commit()
                return event
            rate = policy()
            if type(rate) is not Rate:
                raise ConversionRejected(ConversionResult.UNAVAILABLE)
            cost = quantity * rate.ed_per_bundle
            gain = quantity * rate.ep_per_bundle
            if cost >= 2**63:
                raise ConversionRejected(ConversionResult.UNAVAILABLE)
            if cost > money['ed']:
                raise ConversionRejected(ConversionResult.INSUFFICIENT_ED)
            if ep + gain > MAX_EP:
                raise ConversionRejected(ConversionResult.EP_LIMIT)
            after_ep = validate(ep + gain)
            if money['revision'] >= 2**63-1:
                raise ValueError('ED revision limit')
            if _exists(db, 'character_ep'):
                row = db.execute('SELECT revision FROM character_ep WHERE uid=?', (uid,)).fetchone()
                if row is not None and (type(row[0]) is not int or not 0 <= row[0] < 2**63-1):
                    raise ValueError('EP revision limit')
            _schema(db)
            changed = db.execute('UPDATE reward_balances SET ed=?,revision=revision+1 WHERE uid=? AND ed=? AND revision=?',
                                 (money['ed']-cost, uid, money['ed'], money['revision'])).rowcount
            if changed != 1:
                raise ValueError('ED balance changed during conversion')
            if credit(db, uid, gain) != after_ep:
                raise ValueError('EP credit mismatch')
            event = acknowledgement(money['ed']-cost, after_ep)
            db.execute('INSERT INTO ep_conversion_receipts VALUES (?,?,?,?,?,?,?)',
                       (uid, operation_id, account_id, digest, rate.source_sha256, cost, gain))
            db.commit()
            return event
        except BaseException:
            db.rollback()
            raise


def _active_character(db,uid):
    if _exists(db,'character_lifecycle'):
        row=db.execute('SELECT requested_at,finalized_at FROM character_lifecycle WHERE uid=?',(uid,)).fetchone()
        if row and row[1]:raise ConversionRejected(ConversionResult.UNKNOWN_CHARACTER)
        if row and row[0]:raise ConversionRejected(ConversionResult.INVALID_STATE)

def wallet(path,*,account_id,uid):
    uid=character_uid(uid)
    if type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('Invalid EP account')
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('BEGIN')
        if not db.execute('SELECT 1 FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=? AND o.account_id=?',(uid,account_id)).fetchone():
            raise ConversionRejected(ConversionResult.UNKNOWN_CHARACTER)
        _active_character(db,uid)
        money=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
        return money['ed'],balance(db,uid)
