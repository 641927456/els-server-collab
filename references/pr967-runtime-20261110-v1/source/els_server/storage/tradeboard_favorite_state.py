"""Owned native saved search conditions; no market/item/money production.

Per-character storage with actual account ownership is an explicit local
storage scope. The original packed CC conditions remain lossless and opaque
where their business labels are unqualified. Rename changes only native+9.
"""
from pathlib import Path
from contextlib import closing
import sqlite3,time
from els_server.protocol import tradeboard_favorite_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.trade_board_state import _authority
from els_server.storage.inventory_actions import _identity
from els_server.storage.game_mail import _active_owner

WRITER_ENABLED=True
POLICY='local-owned-native-saved-search-v1'
TABLE='trade_board_favorites'
RECEIPTS='trade_board_favorite_actions'
clock=lambda:int(time.time())


def _exists(db,name):return db.execute('SELECT 1 FROM sqlite_master WHERE type=?AND name=?',('table',name)).fetchone()is not None


def _name(value):
    if type(value)is not str or '\0'in value:raise ValueError('Exact native favorite label required')
    raw=value.encode('utf-16le');units=[int.from_bytes(raw[i:i+2],'little')for i in range(0,len(raw),2)]
    if not 1<=sum(1 if unit<128 else 2 for unit in units)<=20:raise ValueError('Native weighted label length1..20 required')


def _decode(raw):return wire.request(b'\0'+raw).record


def read_rows(db,owner,account_id):
    if(not db.in_transaction or any(type(v)is not int or not 0<v<2**63 for v in(owner,account_id))):
        raise ValueError('Actual owner and active transaction required')
    _active_owner(db,account_id,owner)
    if not _exists(db,TABLE):return []
    result=[]
    for identity,account,raw,policy in db.execute('SELECT id,account_id,record_blob,policy FROM trade_board_favorites WHERE owner=?ORDER BY id',(owner,)):
        if(type(identity)is not int or not 0<identity<2**63 or account!=account_id or type(raw)is not bytes or policy!=POLICY):
            raise ValueError('Original favorite source identity or policy mismatch')
        value=_decode(raw)
        if value['key_00']!=identity:raise ValueError('Saved original favorite key mismatch')
        _name(value['text_09']);result.append(value)
    if len(result)>20:raise ValueError('Original favorite limit exceeded; no hidden truncation')
    return result


def _ensure(db):
    if not db.in_transaction:raise ValueError('Original favorite transaction required')
    db.execute('''CREATE TABLE IF NOT EXISTS trade_board_favorites(
      id INTEGER PRIMARY KEY AUTOINCREMENT,owner INTEGER NOT NULL,account_id INTEGER NOT NULL,
      record_blob BLOB NOT NULL,policy TEXT NOT NULL)''')
    db.execute('CREATE INDEX IF NOT EXISTS trade_board_favorite_owner ON trade_board_favorites(owner,id)')
    db.execute('''CREATE TABLE IF NOT EXISTS trade_board_favorite_actions(
      operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,account_id INTEGER NOT NULL,
      digest TEXT NOT NULL,tag INTEGER NOT NULL,source_id INTEGER NOT NULL,policy TEXT NOT NULL)''')


def perform(path,owner,payload,operation,*,account_id,authority):
    selected=wire.request(payload)
    if selected.tag not in(0,1,2,3):raise ValueError('Unqualified native favorite operation')
    owner,digest=_identity(owner,0xa11,payload,operation);path=Path(path).resolve()
    if not path.is_file():raise ValueError('Existing actual player store required')
    with closing(sqlite3.connect(path,timeout=15))as db,db:
        db.execute('PRAGMA foreign_keys=ON')
        if selected.tag==0:
            db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        else:db.execute('BEGIN IMMEDIATE')
        now=clock() # Only after the actual read/write lock has been acquired.
        _authority(db,authority,path,owner,account_id,0xa11,now)
        current=read_rows(db,owner,account_id)
        if selected.tag==0:
            result=wire.reply(current);encode_event(result);return[result]
        old=db.execute('SELECT owner,account_id,digest,tag,source_id,policy FROM trade_board_favorite_actions WHERE operation=?',(operation,)).fetchone()if _exists(db,RECEIPTS)else None
        if old is not None:
            if old[:4]!=(owner,account_id,digest,selected.tag)or old[5]!=POLICY:raise ValueError('Original favorite replay/owner mismatch')
            result=wire.reply(current);encode_event(result);return[result]
        if not WRITER_ENABLED:raise ValueError('New favorite writes not qualified')
        value=selected.record;identity=value['key_00']
        if selected.tag==1:
            if identity!=0 or len(current)>=20:raise ValueError('Original new favorite key or maximum20')
            _name(value['text_09']);_ensure(db)
            identity=db.execute('INSERT INTO trade_board_favorites(owner,account_id,record_blob,policy)VALUES(?,?,?,?)',(owner,account_id,b'',POLICY)).lastrowid
            if not 0<identity<2**63:raise ValueError('Native signed favorite key exhausted')
            value=dict(value,key_00=identity)
            db.execute('UPDATE trade_board_favorites SET record_blob=?WHERE id=?',(wire.record(value),identity))
        else:
            if type(identity)is not int or identity<=0:raise ValueError('Original owned favorite key required')
            actual=next((r for r in current if r['key_00']==identity),None)
            if actual is None:raise ValueError('Original favorite absent or belongs to another owner')
            _ensure(db)
            if selected.tag==2:
                _name(value['text_09'])
                if {k:v for k,v in value.items()if k!='text_09'}!={k:v for k,v in actual.items()if k!='text_09'}:
                    raise ValueError('Native rename cannot overwrite saved search conditions')
                changed=db.execute('UPDATE trade_board_favorites SET record_blob=?WHERE id=?AND owner=?AND account_id=?AND record_blob=?',
                  (wire.record(dict(actual,text_09=value['text_09'])),identity,owner,account_id,wire.record(actual))).rowcount
            else:
                changed=db.execute('DELETE FROM trade_board_favorites WHERE id=?AND owner=?AND account_id=?',(identity,owner,account_id)).rowcount
            if changed!=1:raise ValueError('Original favorite changed during operation')
        result=wire.reply(read_rows(db,owner,account_id),flag=selected.tag==1)
        encode_event(result) # Full map/frame encoded before receipt and commit.
        db.execute('INSERT INTO trade_board_favorite_actions VALUES(?,?,?,?,?,?,?)',(operation,owner,account_id,digest,selected.tag,identity,POLICY))
        return[result]
