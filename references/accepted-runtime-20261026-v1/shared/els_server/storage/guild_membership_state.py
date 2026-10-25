"""Caller-owned guild SQL operations, with saved ownership and live fences.

No dispatch admission is installed by this leaf. The caller must supply a
fully source-bound native response encoder and its exact session/town guard.
Neither a quest flag nor an administrative membership import is supported.
"""
import hashlib
import unicodedata
import sqlite3
from contextlib import closing
from pathlib import Path
from els_server.storage.item_actor import require_active_character
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.protocol_codec import encode_event
from els_server.protocol.guild_membership_messages import create_request, invite_request, join_reply_request

LICENSE = 110845


def _exists(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def snapshot(db, owner, account_id, *, pending_operation=None):
    """Cold read; absent optional schema never creates tables or membership."""
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?', (owner,)).fetchone() != (account_id,):
        raise ValueError('Guild saved owner')
    tables = ('native_guilds', 'native_guild_members')
    present = [_exists(db, t) for t in tables]
    if not any(present):
        return None
    if not all(present):
        raise ValueError('Partial guild reader schema')
    row = db.execute('''SELECT g.id,g.name,g.master_uid,g.created_at,g.message,
        g.revision,m.grade,m.joined_at,m.source_operation,g.profile_version
        FROM native_guild_members m JOIN native_guilds g ON g.id=m.guild_id
        WHERE m.owner=? AND m.account_id=?''', (owner, account_id)).fetchone()
    if row is None:
        if db.execute('SELECT 1 FROM native_guild_members WHERE owner=?', (owner,)).fetchone():
            raise ValueError('Guild member owner or parent mismatch')
        return None
    result = dict(zip(('id','name','master_uid','created_at','message','revision',
                       'grade','joined_at','source_operation','profile_version'), row))
    if result['profile_version'] != 1:
        raise ValueError('Unknown guild profile version')
    result['members'] = tuple(r[0] for r in db.execute(
        'SELECT owner FROM native_guild_members WHERE guild_id=? ORDER BY owner', (result['id'],)))
    if not 0 < result['id'] < 2**31 or not 1 <= len(result['members']) <= 20:
        raise ValueError('Guild identity or membership capacity')
    if result['master_uid'] not in result['members'] or result['grade'] not in (1, 6):
        raise ValueError('Guild master or finite member grade')
    if db.execute('SELECT grade FROM native_guild_members WHERE owner=? AND guild_id=?',
                  (result['master_uid'],result['id'])).fetchone() != (1,):
        raise ValueError('Guild master membership changed')
    members = db.execute('''SELECT m.owner,m.account_id,m.grade,c.name,o.account_id,m.source_operation,m.joined_at
        FROM native_guild_members m LEFT JOIN characters c ON c.uid=m.owner
        LEFT JOIN character_owners o ON o.uid=m.owner
        WHERE m.guild_id=? ORDER BY m.owner''', (result['id'],)).fetchall()
    for member_uid, member_account, grade, name, saved_account, source_operation, joined_at in members:
        if (not name or member_account != saved_account
                or grade != (1 if member_uid == result['master_uid'] else 6)):
            raise ValueError('Guild cold member ownership or grade changed')
        expected_kind = 0x276 if grade == 1 else 0x288
        receipt = db.execute('SELECT owner,kind,guild_id,created_at,request_hash FROM native_guild_actions WHERE operation=?',
                             (source_operation,)).fetchone()
        staged = (pending_operation is not None and member_uid == owner
                  and source_operation == pending_operation[0]
                  and expected_kind == pending_operation[1])
        if receipt is None:
            if not staged:raise ValueError('Guild membership lacks its actual producer receipt')
        elif (receipt[:4] != (member_uid,expected_kind,result['id'],joined_at)
              or type(receipt[4]) is not str or len(receipt[4])!=64):
            raise ValueError('Guild membership producer receipt changed')
        if member_uid == result['master_uid']:
            if joined_at != result['created_at']:
                raise ValueError('Guild creation source clock changed')
            result['master_name'] = name
    return result


def cold(path, owner, account_id):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        db.execute('BEGIN')
        return snapshot(db,owner,account_id)


def _schema(db):
    if not db.in_transaction:
        raise ValueError('Guild SQL requires caller transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guilds(
        id INTEGER PRIMARY KEY AUTOINCREMENT CHECK(id>0 AND id<2147483648),
        name TEXT NOT NULL,name_key TEXT NOT NULL UNIQUE,
        master_uid INTEGER NOT NULL UNIQUE REFERENCES characters(uid),
        created_at INTEGER NOT NULL,message TEXT NOT NULL,revision INTEGER NOT NULL,
        profile_version INTEGER NOT NULL CHECK(profile_version=1))''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_members(
        owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL REFERENCES native_guilds(id),
        grade INTEGER NOT NULL CHECK(grade IN(1,6)),joined_at INTEGER NOT NULL,
        source_operation TEXT NOT NULL UNIQUE)''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_invitations(
        target_uid INTEGER PRIMARY KEY REFERENCES characters(uid),target_account INTEGER NOT NULL,
        guild_id INTEGER NOT NULL REFERENCES native_guilds(id),inviter_uid INTEGER NOT NULL,
        inviter_name TEXT NOT NULL,target_session TEXT NOT NULL,inviter_session TEXT NOT NULL,
        created_at INTEGER NOT NULL,operation TEXT NOT NULL UNIQUE)''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_actions(
        operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,
        kind INTEGER NOT NULL,guild_id INTEGER NOT NULL,created_at INTEGER NOT NULL)''')


def _actor(db, owner, account_id):
    if not db.in_transaction:
        raise ValueError('Guild action outside transaction')
    require_active_character(db, owner)
    if type(account_id) is not int or account_id <= 0:
        raise ValueError('Guild account identity')
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?', (owner,)).fetchone() != (account_id,):
        raise ValueError('Guild character ownership')
    row = db.execute('SELECT name FROM characters WHERE uid=?', (owner,)).fetchone()
    if row is None:
        raise ValueError('Guild character missing')
    return row[0]


def _operation(db, owner, kind, payload, operation):
    if not isinstance(operation, str) or not 1 <= len(operation) <= 160:
        raise ValueError('Guild operation identity')
    digest = hashlib.sha256(str(owner).encode()+b':'+str(kind).encode()+b':'+payload).hexdigest()
    old = None if not _exists(db, 'native_guild_actions') else db.execute(
        'SELECT request_hash,owner,kind,guild_id FROM native_guild_actions WHERE operation=?', (operation,)).fetchone()
    if old is not None and old[:3] != (digest,owner,kind):
        raise ValueError('Conflicting guild receipt')
    return digest, None if old is None else old[3]


def _finish(db, owner, account_id, kind, operation, digest, now, encode, guard, changes=(), repeat=False, expected_guild=None):
    current = snapshot(db, owner, account_id,
                       pending_operation=None if repeat else (operation,kind,digest))
    if current is None:
        raise ValueError('Guild mutation lost membership')
    if expected_guild is not None and current['id'] != expected_guild:
        raise ValueError('Guild receipt belongs to another saved membership')
    guard()
    events = tuple(encode(current, tuple(changes), repeat))
    if not events:
        raise ValueError('Guild native response is required')
    for event in events:
        encode_event(event)
    guard()
    _actor(db, owner, account_id)
    if not repeat:
        db.execute('INSERT INTO native_guild_actions VALUES(?,?,?,?,?,?)',
                   (operation,digest,owner,kind,current['id'],now))
    return events


def create(db, owner, account_id, item_uid, name, message, payload, operation,
           now, *, encode, guard):
    """276: real owned license -> guild plus master, one SQL transaction.

    The handler supplies the source-verified 277/full-profile encoder. Caller
    rolls back on every exception, including late session or encoding faults.
    """
    if create_request(payload)!=(item_uid,name,message):
        raise ValueError('Guild create request differs from parsed native source')
    _actor(db, owner, account_id); guard()
    digest, previous = _operation(db, owner, 0x276, payload, operation)
    if previous is not None:
        return _finish(db,owner,account_id,0x276,operation,digest,now,encode,guard,
                       repeat=True,expected_guild=previous)
    if snapshot(db, owner, account_id) is not None:
        raise ValueError('Character already belongs to a guild')
    if (type(name) is not str or not name or unicodedata.normalize('NFC',name)!=name
        or any(not c.isalnum() for c in name)
        or sum(2 if unicodedata.east_asian_width(c) in ('W','F') else 1 for c in name)>16):
        raise ValueError('Guild name outside current guide constraints')
    if type(message) is not str or '\0' in message or len(message.encode('utf-16le'))>8192:
        raise ValueError('Guild introduction encoding bound')
    if type(now) is not int or not 0 < now < 2**63:
        raise ValueError('Guild server clock')
    item = next((i for i in load_items(db,owner) if i['uid']==item_uid),None)
    if item is None or (item['template'],item['metadata'],item['group'],item['count']) != (LICENSE,0,4,1):
        raise ValueError('Guild creation requires its owned singleton license')
    require_current(item);require_unlocked(item)
    _schema(db)
    guild_id = db.execute('INSERT INTO native_guilds(name,name_key,master_uid,created_at,message,revision,profile_version) VALUES(?,?,?,?,?,0,1)',
                         (name,name.casefold(),owner,now,message)).lastrowid
    db.execute('INSERT INTO native_guild_members VALUES(?,?,?,?,?,?)',
               (owner,account_id,guild_id,1,now,operation))
    remove(db,owner,item)
    return _finish(db,owner,account_id,0x276,operation,digest,now,encode,guard,
                   changes=(((item['group'],item['slot']),None),))


def invite(db, owner, account_id, target_uid, target_account, source_session,
           target_session, payload, operation, now, *, encode, guard):
    """285: authoritative online recipient and permission, no membership yet."""
    inviter = _actor(db,owner,account_id);target_name=_actor(db,target_uid,target_account);guard()
    supplied_name,supplied_uid=invite_request(payload)
    if (supplied_name and supplied_name!=target_name) or (supplied_uid and supplied_uid!=target_uid):
        raise ValueError('Guild invite resolved another native target')
    if type(now) is not int or not 0 < now < 2**63:
        raise ValueError('Guild server clock')
    if owner==target_uid or any(type(s) is not str or not 1<=len(s)<=160 for s in (source_session,target_session)):
        raise ValueError('Guild invitation session identity')
    current = snapshot(db,owner,account_id)
    if current is None or current['grade']!=1 or current['master_uid']!=owner:
        raise ValueError('This finite producer requires the actual guild master')
    if snapshot(db,target_uid,target_account) is not None or len(current['members'])>=20:
        raise ValueError('Guild recipient already joined or capacity exhausted')
    digest, previous = _operation(db,owner,0x285,payload,operation)
    if previous is not None:
        if previous != current['id']:
            raise ValueError('Guild invitation receipt belongs to another guild')
        return ()  # The committed invitation is never reissued across sessions.
    _schema(db)
    pending = db.execute('SELECT target_account,target_session FROM native_guild_invitations WHERE target_uid=?',
                         (target_uid,)).fetchone()
    if pending is not None:
        if pending[0] != target_account or pending[1] == target_session:
            raise ValueError('Guild recipient already has a current invitation')
        # A verified new live recipient generation cannot answer its old
        # invitation. Retire only that exact stale row in this same writer.
        db.execute('DELETE FROM native_guild_invitations WHERE target_uid=? AND target_account=? AND target_session=?',
                   (target_uid, target_account, pending[1]))
    db.execute('INSERT INTO native_guild_invitations VALUES(?,?,?,?,?,?,?,?,?)',
        (target_uid,target_account,current['id'],owner,inviter,target_session,source_session,now,operation))
    events=tuple(encode(current,inviter,target_uid))
    if not events:raise ValueError('Guild invitation notification required')
    for event in events:encode_event(event)
    guard();_actor(db,owner,account_id);_actor(db,target_uid,target_account)
    db.execute('INSERT INTO native_guild_actions VALUES(?,?,?,?,?,?)',
               (operation,digest,owner,0x285,current['id'],now))
    return events


def accept(db, owner, account_id, guild_id, inviter, session, payload, operation,
           now, *, encode, guard, inviter_account_id, inviter_session):
    """288 explicit acceptance; exact invitation, same live target generation."""
    if join_reply_request(payload)!=(guild_id,inviter,0):
        raise ValueError('Guild join requires native affirmative reply')
    if type(now) is not int or not 0 < now < 2**63 or type(session) is not str or not 1<=len(session)<=160:
        raise ValueError('Guild acceptance clock/session')
    _actor(db,owner,account_id);guard()
    digest, previous = _operation(db,owner,0x288,payload,operation)
    if previous is not None:
        if previous != guild_id:
            raise ValueError('Guild acceptance receipt guild mismatch')
        return _finish(db,owner,account_id,0x288,operation,digest,now,encode,guard,
                       repeat=True,expected_guild=previous)
    if snapshot(db,owner,account_id) is not None or not _exists(db,'native_guild_invitations'):
        raise ValueError('Guild acceptance has no eligible pending invitation')
    invite_row=db.execute('SELECT target_account,guild_id,inviter_uid,inviter_name,target_session,inviter_session FROM native_guild_invitations WHERE target_uid=?',(owner,)).fetchone()
    if invite_row is None or (invite_row[0],invite_row[1],invite_row[3],invite_row[4])!=(account_id,guild_id,inviter,session):
        raise ValueError('Guild invitation actor, session or source mismatch')
    if (type(inviter_session) is not str or not inviter_session
            or invite_row[5] != inviter_session
            or _actor(db,invite_row[2],inviter_account_id) != inviter):
        raise ValueError('Guild original inviter identity or generation changed')
    source = snapshot(db,invite_row[2],inviter_account_id)
    if source is None or source['id'] != guild_id or source['grade'] != 1:
        raise ValueError('Guild original inviter lost membership or authority')
    master=db.execute('SELECT master_uid FROM native_guilds WHERE id=?',(guild_id,)).fetchone()
    if master!=(invite_row[2],):raise ValueError('Guild inviter authority changed')
    if db.execute('SELECT COUNT(*) FROM native_guild_members WHERE guild_id=?',(guild_id,)).fetchone()[0]>=20:
        raise ValueError('Guild filled before acceptance')
    db.execute('INSERT INTO native_guild_members VALUES(?,?,?,?,?,?)',(owner,account_id,guild_id,6,now,operation))
    if db.execute('UPDATE native_guilds SET revision=revision+1 WHERE id=? AND revision<9223372036854775807',(guild_id,)).rowcount!=1:
        raise ValueError('Guild revision overflow')
    db.execute('DELETE FROM native_guild_invitations WHERE target_uid=?',(owner,))
    return _finish(db,owner,account_id,0x288,operation,digest,now,encode,guard)
