"""Weekly Chaos progress for the selected character and its owned reward drops."""
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass, replace
import json
import secrets
import sqlite3
import time
from uuid import uuid4

from els_server.storage.item_actor import require_active_character
from els_server.storage.manufacture_quota import window


NORMAL_STAGES = 29
ROUNDS = 10
HIDDEN_STAGE = 29
REWARD_STAGE = 30
RESET_TICKETS = frozenset((62260,62261))


@dataclass(frozen=True)
class Progress:
    owner: int
    week: int
    generation: str
    normal: tuple
    hidden: int
    cursor: int
    grade: int
    selected: int

    @property
    def stages(self):
        result = []
        for index, stage in enumerate(self.normal):
            if self.hidden & (1 << index):
                result.append(HIDDEN_STAGE)
            result.append(stage)
        return (*result, REWARD_STAGE)

    @property
    def completed(self):
        return sum(stage < HIDDEN_STAGE for stage in self.stages[:self.cursor])


def period(now=None):
    return window(int(time.time()) if now is None else now, region='CN')[0]


def read(db, owner, week):
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='henir_chaos_progress'").fetchone() is None:
        return None
    row = db.execute('''SELECT owner,week,generation,normal,hidden,cursor,grade,selected
                        FROM henir_chaos_progress WHERE owner=? AND week=?''', (owner, week)).fetchone()
    return Progress(*row[:3], tuple(json.loads(row[3])), *row[4:]) if row else None


def authority(db, owner, account):
    require_active_character(db, owner)
    if db.execute('SELECT account_id FROM character_owners WHERE uid=?', (owner,)).fetchone() != (account,):
        raise ValueError('Chaos selected character owner')


@contextmanager
def writer(path, owner, account):
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        authority(db, owner, account)
        yield db


def admit(path, owner, account, prepare):
    with writer(path, owner, account) as db:
        week = period()
        db.execute('''CREATE TABLE IF NOT EXISTS henir_chaos_progress(
            owner INTEGER NOT NULL REFERENCES characters(uid), week INTEGER NOT NULL,
            generation TEXT NOT NULL UNIQUE, normal TEXT NOT NULL, hidden INTEGER NOT NULL,
            cursor INTEGER NOT NULL, grade INTEGER NOT NULL CHECK(grade BETWEEN 1 AND 5),
            selected INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(owner,week))''')
        progress = read(db, owner, week)
        if progress is None:
            normal = tuple(secrets.SystemRandom().sample(range(NORMAL_STAGES), ROUNDS))
            # Player-approved compatibility probabilities.
            hidden = sum((1 << i) for i in range(ROUNDS) if secrets.randbelow(100) < 5)
            progress = Progress(owner, week, str(uuid4()), normal, hidden, 0, 1, 0)
            db.execute('INSERT INTO henir_chaos_progress VALUES(?,?,?,?,?,?,?,?)',
                       (owner, week, progress.generation, json.dumps(normal), hidden, 0, 1, 0))
        if progress.selected:
            raise ValueError('Chaos weekly reward already selected')
        return prepare(progress)


def advance(path, owner, account, progress, prepare):
    with writer(path, owner, account) as db:
        if progress.week != period() or read(db, owner, progress.week) != progress or progress.selected:
            raise ValueError('Chaos checkpoint is no longer current')
        stage = progress.stages[progress.cursor]
        if stage == REWARD_STAGE:
            raise ValueError('Chaos reward stage cannot raise the grade')
        roll = secrets.randbelow(100)
        if stage == HIDDEN_STAGE:
            increase = 1 if roll < 75 else 2
        else:
            increase = int(roll >= 80) + int(roll >= 98)
        saved = replace(progress, cursor=progress.cursor+1, grade=min(5, progress.grade+increase))
        result = prepare(saved, saved.grade-progress.grade)
        db.execute('UPDATE henir_chaos_progress SET cursor=?,grade=? WHERE owner=? AND week=?',
                   (saved.cursor, saved.grade, owner, saved.week))
        return saved, result


def select(path, owner, account, progress, template, prepare):
    with writer(path, owner, account) as db:
        now = int(time.time())
        if progress.week != period(now) or read(db, owner, progress.week) != progress:
            raise ValueError('Chaos claim checkpoint is no longer current')
        if progress.stages[progress.cursor] != REWARD_STAGE or progress.selected:
            raise ValueError('Chaos weekly reward is not available')
        saved = replace(progress, selected=template)
        db.execute('UPDATE henir_chaos_progress SET selected=? WHERE owner=? AND week=?',
                   (template, owner, saved.week))
        prepared, drops = prepare(db, saved, now)
        db.execute('''CREATE TABLE IF NOT EXISTS henir_chaos_drops(
            generation TEXT NOT NULL REFERENCES henir_chaos_progress(generation),
            template INTEGER NOT NULL, run_id TEXT NOT NULL, drop_id INTEGER NOT NULL,
            picked INTEGER NOT NULL DEFAULT 0 CHECK(picked IN (0,1)),
            PRIMARY KEY(generation,template))''')
        db.executemany('INSERT INTO henir_chaos_drops(generation,template,run_id,drop_id) VALUES(?,?,?,?)',
                       ((saved.generation, drop['template'], drop['run_id'], drop['drop_id']) for drop in drops))
        return saved, prepared, drops


def reset(path, owner, account, payload, operation, guard):
    from els_server.protocol.career_messages import use_ack, use_request
    from els_server.protocol.henir_chaos_messages import progress as progress_notice
    from els_server.protocol.protocol_codec import encode_event
    from els_server.storage.ariel_daily_special import notification
    from els_server.storage.equipment_receipt_state import current_changes
    from els_server.storage.inventory_actions import _identity, _previous, _commit
    from els_server.storage.inventory_state import load_items
    from els_server.storage.item_instances import reduce_count, remove
    from els_server.storage.npc_trade import balances
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked

    item_uid = use_request(payload)
    _, digest = _identity(owner, 0x219, payload, operation)
    with writer(path, owner, account) as db:
        guard()
        now = int(time.time())
        old = _previous(db, operation, digest)
        items = load_items(db, owner)
        if old is not None:
            changes = current_changes(db, operation, owner, 0x219, old, items)
            used_template = 0
        else:
            item = next((i for i in items if i['uid'] == item_uid), None)
            if item is None or item['template'] not in RESET_TICKETS or (item['group'],item['metadata']) != (4,2):
                raise ValueError('Chaos reset requires the current owned ticket')
            require_current(item, now=now)
            require_unlocked(item, now=now)
            if item.get('sealed',False) or item.get('seal_used',0):
                raise ValueError('Chaos ticket seal state')
            current = read(db, owner, period(now))
            if current is None or not current.selected:
                raise ValueError('Chaos reset requires exhausted weekly rewards')
            drops = db.execute('SELECT template,run_id,drop_id,picked FROM henir_chaos_drops WHERE generation=? ORDER BY template',
                               (current.generation,)).fetchall()
            if len(drops)!=2:
                raise ValueError('Chaos issued reward pair missing')
            db.execute('''CREATE TABLE IF NOT EXISTS henir_chaos_reset_history(
                generation TEXT PRIMARY KEY, owner INTEGER NOT NULL REFERENCES characters(uid),
                week INTEGER NOT NULL, operation TEXT NOT NULL UNIQUE, state TEXT NOT NULL, drops TEXT NOT NULL)''')
            db.execute('INSERT INTO henir_chaos_reset_history VALUES(?,?,?,?,?,?)',
                       (current.generation,owner,current.week,operation,json.dumps(asdict(current)),json.dumps(drops)))
            db.execute('DELETE FROM henir_chaos_drops WHERE generation=?',(current.generation,))
            db.execute('DELETE FROM henir_chaos_progress WHERE owner=? AND week=?',(owner,current.week))
            position = (item['group'],item['slot'])
            remaining = None
            if item['count']==1:
                remove(db,owner,item)
            else:
                remaining=reduce_count(item,item['count']-1)
                db.execute('UPDATE inventory_items SET count=? WHERE owner=? AND uid=?',
                           (remaining['count'],owner,item_uid))
            _commit(db, operation, digest, owner, 0x219, [position], [item], [remaining] if remaining else [])
            changes = [(position,remaining)]
            used_template = item['template']
        events = [use_ack(changes,used_template,balances(db,owner)['ed']),notification(db,account,owner,now),
                  progress_notice(read(db,owner,period(now)))]
        for event in events:encode_event(event)
        guard()
        return events


def reserve_ticket_exchange(db,owner,template,now):
    week=period(now)
    db.execute('''CREATE TABLE IF NOT EXISTS henir_chaos_ticket_exchanges(
        owner INTEGER NOT NULL REFERENCES characters(uid), template INTEGER NOT NULL,
        week INTEGER NOT NULL, PRIMARY KEY(owner,template,week))''')
    if db.execute('SELECT 1 FROM henir_chaos_ticket_exchanges WHERE owner=? AND template=? AND week>=?',
                  (owner,template,week)).fetchone():
        raise ValueError('Chaos ticket weekly exchange already used')
    db.execute('INSERT INTO henir_chaos_ticket_exchanges VALUES(?,?,?)',(owner,template,week))


def pickup(path, owner, account, progress, drop, guard, prepare):
    from els_server.domain.henir_chaos_flow import POLICY
    from els_server.domain.raid_reward_items import _issue_source
    from els_server.domain.reward_rules import item_plan
    from els_server.storage.inventory_state import grant_items

    with writer(path, owner, account) as db:
        if read(db, owner, progress.week) != progress or not progress.selected or not guard():
            raise ValueError('Chaos pickup actor or weekly claim changed')
        identity = (progress.generation, drop['template'])
        row = db.execute('SELECT run_id,drop_id,picked FROM henir_chaos_drops WHERE generation=? AND template=?',
                         identity).fetchone()
        if row is None or row[:2] != (drop['run_id'], drop['drop_id']):
            raise ValueError('Chaos pickup does not match a committed drop')
        if row[2]:
            return prepare(())
        plan = [item_plan(drop['template'], 1)]
        source = _issue_source(db, owner, f'{progress.generation}:chaos:{drop["template"]}', 'ordinary',
                               dict(policy=POLICY, generation=progress.generation, template=drop['template']),
                               plan, lambda db: guard())
        result = prepare(grant_items(db, plan, owner, raid_reward_source=source))
        db.execute('UPDATE henir_chaos_drops SET picked=1 WHERE generation=? AND template=?', identity)
        return result
