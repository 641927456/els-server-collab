"""Shared persistent guild state. Every writer uses its caller's real SQL transaction."""
import hashlib
import json
from els_server.domain import guild_rules as rules


def exists(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()is not None


def read(db, guild):
    row=db.execute('SELECT document FROM native_guild_system_v2 WHERE guild_id=?',(guild,)).fetchone()if exists(db,'native_guild_system_v2')else None
    state=json.loads(row[0])if row else rules.initial()
    if state['version']!=2:raise ValueError('Unsupported guild system version')
    return state


def schema(db):
    if not db.in_transaction:raise ValueError('Guild system requires caller transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_system_v2(
        guild_id INTEGER PRIMARY KEY REFERENCES native_guilds(id),document TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_operations_v2(
        operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,guild_id INTEGER NOT NULL,
        owner INTEGER NOT NULL,kind INTEGER NOT NULL,result TEXT NOT NULL,created_at INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_currency_entries_v2(
        operation TEXT PRIMARY KEY REFERENCES native_guild_operations_v2(operation),
        guild_id INTEGER NOT NULL REFERENCES native_guilds(id),coins INTEGER NOT NULL,
        banner_points INTEGER NOT NULL,source TEXT NOT NULL,created_at INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_departures_v2(
        owner INTEGER PRIMARY KEY,account_id INTEGER NOT NULL,guild_id INTEGER NOT NULL,
        departed_at INTEGER NOT NULL,operation TEXT NOT NULL UNIQUE)''')


def write(db, guild, state):
    schema(db)
    db.execute('INSERT INTO native_guild_system_v2 VALUES(?,?) ON CONFLICT(guild_id) DO UPDATE SET document=excluded.document',
        (guild,json.dumps(state,ensure_ascii=False,sort_keys=True,separators=(',',':'))))


def receipt(db, owner, kind, payload, operation):
    digest=hashlib.sha256(str(owner).encode()+b':'+str(kind).encode()+b':'+payload).hexdigest()
    row=db.execute('SELECT request_hash,guild_id,owner,kind,result FROM native_guild_operations_v2 WHERE operation=?',(operation,)).fetchone()if exists(db,'native_guild_operations_v2')else None
    if row and (row[0],row[2],row[3])!=(digest,owner,kind):raise ValueError('Conflicting guild operation')
    return digest,None if row is None else (row[1],json.loads(row[4]))


def record(db, operation, digest, guild, owner, kind, result, now):
    schema(db)
    db.execute('INSERT INTO native_guild_operations_v2 VALUES(?,?,?,?,?,?,?)',
        (operation,digest,guild,owner,kind,json.dumps(result,sort_keys=True,separators=(',',':')),now))


def finish(db,operation,result):
    if db.execute('UPDATE native_guild_operations_v2 SET result=? WHERE operation=?',(json.dumps(result,sort_keys=True,separators=(',',':')),operation)).rowcount!=1:raise ValueError('Guild operation lost its producer')


def currency_delta(db, guild):
    if not exists(db,'native_guild_currency_entries_v2'):return 0,0,0
    return db.execute('SELECT coalesce(sum(coins),0),coalesce(sum(banner_points),0),count(*) FROM native_guild_currency_entries_v2 WHERE guild_id=?',(guild,)).fetchone()


def currency(db, guild):
    from els_server.storage.guild_coin_state import snapshot
    return snapshot(db,guild),currency_delta(db,guild)[1]


def change_currency(db, guild, coins, banner_points, operation, source, now):
    from els_server.storage import guild_coin_state as coin
    old_coins,old_banner=currency(db,guild)
    if not 0<=old_coins+coins<2**31 or not 0<=old_banner+banner_points<2**31:
        raise ValueError('Insufficient or overflowing guild currency')
    schema(db);coin._schema(db)
    db.execute('INSERT INTO native_guild_currency_entries_v2 VALUES(?,?,?,?,?,?)',
        (operation,guild,coins,banner_points,source,now))
    db.execute('INSERT INTO native_guild_coin_v1 VALUES(?,?,1,1) ON CONFLICT(guild_id) DO UPDATE SET balance=excluded.balance,revision=revision+1',
        (guild,old_coins+coins))
    return old_coins+coins,old_banner+banner_points


def member(state, owner):
    return state['member_details'].setdefault(str(owner),dict(message='',page=1,
        honor=0,weekly_honor=0,honor_week=None,last_login=0))


def honor(state, owner, amount, now):
    if type(amount)is not int or amount<0:raise ValueError('Guild honor amount')
    value=member(state,owner);period=rules.week(now)
    if value['honor_week']!=period:value.update(honor_week=period,weekly_honor=0)
    weekly,total=rules.calls('SetGuildHonorPointLimit')[0]
    added=min(amount,max(0,weekly-value['weekly_honor']),max(0,total-value['honor']))
    value['weekly_honor']+=added;value['honor']+=added;state['experience']=min(total,state['experience']+added)
    return added


def grade(db, saved, target, new_grade):
    if new_grade not in range(1,7):raise ValueError('Unknown current guild grade')
    current=db.execute('SELECT grade FROM native_guild_members WHERE owner=? AND guild_id=?',(target,saved['id'])).fetchone()
    if current is None:raise ValueError('Guild member is absent')
    if target==saved['owner'] or saved['grade']not in(1,2)or saved['grade']!=1 and (new_grade<=saved['grade']or current[0]<=saved['grade']):
        raise ValueError('Guild grade authority')
    if target==saved['master_uid']:raise ValueError('Use master transfer for the current master')
    if new_grade==1:
        if saved['grade']!=1:raise ValueError('Only master transfers ownership')
        db.execute('UPDATE native_guild_members SET grade=2 WHERE owner=?',(saved['master_uid'],))
        db.execute('UPDATE native_guilds SET master_uid=?,revision=revision+1 WHERE id=?',(target,saved['id']))
    else:db.execute('UPDATE native_guilds SET revision=revision+1 WHERE id=?',(saved['id'],))
    db.execute('UPDATE native_guild_members SET grade=? WHERE owner=?',(new_grade,target))


def leave(db, saved, target, operation, now):
    if target==saved['master_uid']:raise ValueError('Guild master must transfer ownership or disband')
    if target!=saved['owner'] and (saved['grade']not in(1,2)or target==saved['owner']):
        raise ValueError('Guild expulsion authority')
    row=db.execute('SELECT account_id,grade FROM native_guild_members WHERE owner=? AND guild_id=?',(target,saved['id'])).fetchone()
    if row is None or target!=saved['owner']and row[1]<=saved['grade']:raise ValueError('Guild expulsion hierarchy')
    state=read(db,saved['id']);saved['system']=state
    from els_server.domain.guild_expedition import depart
    depart(db,saved,target,now)
    from els_server.storage.guild_quests import depart as abandon_tasks
    abandon_tasks(db,target)
    schema(db)
    db.execute('INSERT INTO native_guild_departures_v2 VALUES(?,?,?,?,?) ON CONFLICT(owner) DO UPDATE SET account_id=excluded.account_id,guild_id=excluded.guild_id,departed_at=excluded.departed_at,operation=excluded.operation',
        (target,row[0],saved['id'],now,operation))
    db.execute('DELETE FROM native_guild_invitations WHERE target_uid=?',(target,))
    db.execute('DELETE FROM native_guild_members WHERE owner=? AND guild_id=?',(target,saved['id']))
    state['member_details'].pop(str(target),None)
    state['plots'].pop(str(target),None)
    state['watering'].pop(str(target),None)
    write(db,saved['id'],state)
    db.execute('UPDATE native_guilds SET revision=revision+1 WHERE id=?',(saved['id'],))
    return state
