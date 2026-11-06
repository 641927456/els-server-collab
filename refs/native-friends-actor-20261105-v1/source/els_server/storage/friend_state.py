"""Owned bilateral friendships and per-character groups, in one SQL writer."""
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import sqlite3
import time
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character


def exists(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS native_friend_edges(
        owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
        target INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
        status INTEGER NOT NULL CHECK(status BETWEEN 0 AND 2),
        blocked INTEGER NOT NULL CHECK(blocked IN(0,1)),
        group_id INTEGER NOT NULL CHECK(group_id>=0), message TEXT NOT NULL,
        created_at INTEGER NOT NULL, PRIMARY KEY(owner,target), CHECK(owner<>target))''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_friend_groups(
        id INTEGER PRIMARY KEY AUTOINCREMENT CHECK(id BETWEEN 1 AND 2147483647),
        owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE, name TEXT NOT NULL,
        active INTEGER NOT NULL CHECK(active IN(0,1)))''')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS native_friend_group_names '
               'ON native_friend_groups(owner,name) WHERE active=1')
    db.execute('''CREATE TABLE IF NOT EXISTS native_friend_operations(
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
        kind INTEGER NOT NULL,digest TEXT NOT NULL,result TEXT NOT NULL,
        current_state TEXT NOT NULL)''')


def character(db, uid=None, name=None):
    where, key = ('c.uid=?', uid) if uid is not None else ('c.name_key=?', name.casefold())
    row = db.execute('SELECT c.uid,c.name,c.unit_type,c.unit_class,c.level,o.account_id '
                     'FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE ' + where, (key,)).fetchone()
    if row is None:
        raise ValueError('Friend character does not exist')
    return dict(zip(('uid', 'name', 'unit_type', 'unit_class', 'level', 'account_id'), row))


def edge(db, owner, target):
    return db.execute('SELECT status,blocked,group_id,message,created_at '
                      'FROM native_friend_edges WHERE owner=? AND target=?', (owner, target)).fetchone()


def profile(db, row, group, status, live):
    value = dict(row, group=group, status=status, online=int(live is not None),
                 rank=0, guild_name='', channel=0, map=0, context_flag=0)
    if live is not None:
        value.update(channel=1, map=live.active_map or 0)
    if exists(db, 'native_guild_members') and exists(db, 'native_guilds'):
        guild = db.execute('SELECT g.name FROM native_guild_members m JOIN native_guilds g '
                           'ON g.id=m.guild_id WHERE m.owner=? AND m.account_id=?',
                           (row['uid'], row['account_id'])).fetchone()
        if guild:
            value['guild_name'] = guild[0]
    if exists(db, 'official_pvp_profiles'):
        from els_server.domain.pvp_official_1v1_policy import Profile, POLICY
        saved = db.execute('SELECT account_id,policy,profile_json FROM official_pvp_profiles '
                           'WHERE uid=?', (row['uid'],)).fetchone()
        if saved is not None:
            if saved[:2] != (row['account_id'], POLICY):
                raise ValueError('Unknown public friend PvP profile')
            value['rank'] = Profile(**json.loads(saved[2])).checked().rank
    return value


def snapshot(db, owner, account, online):
    require_owner(db, owner, account)
    result = dict(friends=[], groups={}, pending=[])
    if not exists(db, 'native_friend_edges'):
        return result
    result['groups'] = dict(db.execute('SELECT id,name FROM native_friend_groups '
                                       'WHERE owner=? AND active=1 ORDER BY id', (owner,)))
    for target, status, blocked, group, message, created in db.execute(
            'SELECT target,status,blocked,group_id,message,created_at '
            'FROM native_friend_edges WHERE owner=? ORDER BY target', (owner,)):
        target_row = character(db, uid=target)
        live = online.get(target) if status == 0 and not blocked else None
        # A peer's block also suppresses that peer's presence subscription.
        peer = edge(db, target, owner)
        if peer is None or peer[0] != 0 or peer[1]:
            live = None
        result['friends'].append(profile(db, target_row, group, 3 if blocked else status, live))
        if status == 2:
            stamp = datetime.fromtimestamp(created, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
            result['pending'].append(dict(uid=target, name=target_row['name'], message=message, date=stamp))
    return result


def state_for(db, owner, target, group):
    pairs = [] if not target else [edge(db, owner, target), edge(db, target, owner)]
    saved_group = None if not group else db.execute(
        'SELECT owner,name,active FROM native_friend_groups WHERE id=?', (group,)).fetchone()
    return json.dumps([pairs, saved_group], separators=(',', ':'))


def perform(path, owner, account, kind, payload, parsed, operation, guard, encode):
    if type(operation) is not str or not 1 <= len(operation) <= 160:
        raise ValueError('Friend operation identity')
    digest = hashlib.sha256(str(account).encode() + b':' + str(kind).encode() + b':' + payload).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        guard(db)
        require_owner(db, owner, account)
        require_active_character(db, owner)
        ensure(db)
        previous = db.execute('SELECT owner,kind,digest,result,current_state '
                              'FROM native_friend_operations WHERE operation=?', (operation,)).fetchone()
        if previous:
            if previous[:3] != (owner, kind, digest):
                raise ValueError('Conflicting friendship replay')
            result = json.loads(previous[3])
            if state_for(db, owner, result['target'], result['group']) != previous[4]:
                raise ValueError('Friendship changed after the original operation')
            answer = encode(db, result, [], True)
            guard(db)
            return answer
        result = dict(target=0, name='', group=0)
        notices = []
        if kind <= 0x25a:
            target = character(db, name=parsed['name']) if kind == 0x248 else character(db, uid=parsed['target'])
            if target['account_id'] == account or target['uid'] == owner:
                raise ValueError('A different owned account is required for friendship')
            other = target['uid']
            current, peer = edge(db, owner, other), edge(db, other, owner)
            result.update(target=other, name=target['name'])
            if kind == 0x248:
                require_active_character(db, other)
                if current is not None or peer is not None:
                    raise ValueError('Existing friendship or pending request')
                stamp = int(time.time())
                message = parsed['message']
                db.executemany('INSERT INTO native_friend_edges VALUES(?,?,?,0,0,?,?)',
                               ((owner, other, 1, message, stamp), (other, owner, 2, message, stamp)))
                notices.append((other, 'invitation'))
            elif kind in (0x24b, 0x24e):
                if kind == 0x24b:
                    require_active_character(db, other)
                if current is None or peer is None or current[:2] != (2, 0) or peer[:2] != (1, 0):
                    raise ValueError('This character has no matching incoming friendship request')
                if kind == 0x24b:
                    db.execute('UPDATE native_friend_edges SET status=0,message=? '
                               'WHERE (owner=? AND target=?) OR (owner=? AND target=?)',
                               ('', owner, other, other, owner))
                else:
                    db.execute('DELETE FROM native_friend_edges '
                               'WHERE (owner=? AND target=?) OR (owner=? AND target=?)',
                               (owner, other, other, owner))
                notices.append((other, 'accepted' if kind == 0x24b else 'denied'))
            else:
                if current is None or peer is None:
                    raise ValueError('Owned friendship is required')
                if kind in (0x251, 0x254):
                    if current[0] != 0 or current[1] == int(kind == 0x251):
                        raise ValueError('Friend block state is unchanged or not an accepted friend')
                    db.execute('UPDATE native_friend_edges SET blocked=?,group_id=0 WHERE owner=? AND target=?',
                               (int(kind == 0x251), owner, other))
                    notices.append((other, 'blocked' if kind == 0x251 else 'unblocked'))
                elif kind == 0x257:
                    db.execute('DELETE FROM native_friend_edges '
                               'WHERE (owner=? AND target=?) OR (owner=? AND target=?)',
                               (owner, other, other, owner))
                    notices.append((other, 'deleted'))
                elif kind == 0x25a:
                    group = parsed['group']
                    if group != 0 and not db.execute('SELECT 1 FROM native_friend_groups '
                            'WHERE id=? AND owner=? AND active=1', (group, owner)).fetchone():
                        raise ValueError('Owned active friend group is required')
                    if current[0] != 0 or current[1]:
                        raise ValueError('Only an accepted unblocked friend can move groups')
                    db.execute('UPDATE native_friend_edges SET group_id=? WHERE owner=? AND target=?', (group, owner, other))
                    result['group'] = group
        else:
            group = parsed.get('group', 0)
            if kind in (0x25c, 0x25e):
                name = parsed['name']
                if not name or name != name.strip() or '\0' in name:
                    raise ValueError('Friend group name')
            if kind == 0x25c:
                group = db.execute('INSERT INTO native_friend_groups(owner,name,active) VALUES(?,?,1)', (owner, name)).lastrowid
            else:
                if not db.execute('SELECT 1 FROM native_friend_groups WHERE owner=? AND id=? AND active=1', (owner, group)).fetchone():
                    raise ValueError('Owned active non-default group is required')
                if kind == 0x25e:
                    db.execute('UPDATE native_friend_groups SET name=? WHERE id=?', (name, group))
                elif kind == 0x260:
                    db.execute('UPDATE native_friend_groups SET active=0 WHERE id=?', (group,))
                    db.execute('UPDATE native_friend_edges SET group_id=0 WHERE owner=? AND group_id=?', (owner, group))
            result.update(group=group, name='' if kind == 0x260 else name)
        answer = encode(db, result, notices, False)
        guard(db)
        state = state_for(db, owner, result['target'], result['group'])
        db.execute('INSERT INTO native_friend_operations VALUES(?,?,?,?,?,?)',
                   (operation, owner, kind, digest, json.dumps(result, sort_keys=True), state))
        return answer
