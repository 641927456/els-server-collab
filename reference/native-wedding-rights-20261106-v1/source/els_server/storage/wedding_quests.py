"""Weekly marriage task generations in the existing quest/reward transactions."""
import json,time
from els_server.domain import wedding_quests as rules
from els_server.domain.guild_rules import week
from els_server.storage.titles import exists


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def visible(db,owner,now):
    from els_server.storage.bank_state import account_for
    saved=rules.current(db,owner,account_for(db,owner),now)
    if saved is None or not exists(db,'native_wedding_quest_sources'):return False
    source=db.execute('SELECT pair_id,generation FROM native_wedding_quest_sources WHERE owner=?',(owner,)).fetchone()
    active=db.execute('SELECT generation FROM character_quests WHERE owner=?AND quest=?',(owner,rules.QUEST)).fetchone()
    return source is not None and active is not None and source==(saved['pair_id'],active[0])


def initialize(db):
    if not db.in_transaction:raise ValueError('Wedding task requires caller writer')
    db.execute('''CREATE TABLE IF NOT EXISTS native_wedding_quest_sources(
        owner INTEGER PRIMARY KEY REFERENCES characters(uid),pair_id TEXT NOT NULL,generation INTEGER NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_wedding_quest_history(
        owner INTEGER NOT NULL,week INTEGER NOT NULL,completed_at INTEGER NOT NULL,reward_json TEXT NOT NULL,
        PRIMARY KEY(owner,week))''')
    db.execute('''CREATE TABLE IF NOT EXISTS native_wedding_quest_operations(
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,kind TEXT NOT NULL,week INTEGER NOT NULL,pair_id TEXT NOT NULL)''')


def before_action(store,db,operation,kind,now):
    if not callable(store.account_source_guard):raise ValueError('Wedding task requires current actor')
    store.account_source_guard(db)
    saved=rules.current(db,store.uid,store.account_id,now)
    if kind!='abandon' and saved is None:raise ValueError('Wedding task requires current marriage within365days')
    initialize(db);period=week(now)
    old=db.execute('SELECT owner,kind,week,pair_id FROM native_wedding_quest_operations WHERE operation=?',(operation,)).fetchone()
    if old is not None and old!=(store.uid,kind,period,saved['pair_id']if saved else ''):
        raise ValueError('Wedding request belongs to another week or relationship')
    done=db.execute('SELECT completed_at,reward_json FROM completed_quests WHERE owner=?AND quest=?',(store.uid,rules.QUEST)).fetchone()
    if done is not None and week(done[0])!=period:
        if week(done[0])>period:raise ValueError('Wedding weekly clock moved backwards')
        db.execute('INSERT INTO native_wedding_quest_history VALUES(?,?,?,?)',(store.uid,week(done[0]),*done))
        db.execute('DELETE FROM completed_quests WHERE owner=?AND quest=?',(store.uid,rules.QUEST))
    active=db.execute('SELECT generation FROM character_quests WHERE owner=?AND quest=?',(store.uid,rules.QUEST)).fetchone()
    source=db.execute('SELECT pair_id,generation FROM native_wedding_quest_sources WHERE owner=?',(store.uid,)).fetchone()
    if active is not None and (saved is None or source!=(saved['pair_id'],active[0])):
        if kind=='claim':raise ValueError('Wedding progress belongs to another spouse generation')
        db.execute('DELETE FROM character_quests WHERE owner=?AND quest=?',(store.uid,rules.QUEST))
        db.execute('DELETE FROM native_wedding_quest_sources WHERE owner=?',(store.uid,))


def after_action(store,db,operation,kind,now):
    store.account_source_guard(db);saved=rules.current(db,store.uid,store.account_id,now)
    if kind!='abandon'and saved is None:raise ValueError('Wedding task marriage changed before commit')
    active=db.execute('SELECT generation FROM character_quests WHERE owner=?AND quest=?',(store.uid,rules.QUEST)).fetchone()
    if active is None:db.execute('DELETE FROM native_wedding_quest_sources WHERE owner=?',(store.uid,))
    elif kind=='accept':
        db.execute('INSERT OR IGNORE INTO native_wedding_quest_sources VALUES(?,?,?)',(store.uid,saved['pair_id'],active[0]))
    db.execute('INSERT OR IGNORE INTO native_wedding_quest_operations VALUES(?,?,?,?,?)',
               (operation,store.uid,kind,week(now),saved['pair_id']if saved else ''))


def grant(store,db,operation,now):
    from els_server.domain.raid_reward_items import _issue_source
    from els_server.storage.inventory_state import grant_items
    saved=rules.current(db,store.uid,store.account_id,now)
    if saved is None or not visible(db,store.uid,now):raise ValueError('Wedding reward source ended')
    plan=rules.reward_plan()
    def guard(writer):
        store.account_source_guard(writer)
        if rules.current(writer,store.uid,store.account_id,now)!=saved:raise ValueError('Wedding reward spouse changed')
        return True
    source=_issue_source(db,store.uid,operation,'ordinary',dict(policy=rules.POLICY,
        owner=store.uid,quest=rules.QUEST,week=week(now),pair_id=saved['pair_id'],definition_sha256=rules.DATA_SHA),plan,guard)
    return grant_items(db,plan,store.uid,raid_reward_source=source)


def record(db,owner,account,operation,dungeon,level,roster,guard,*,now=None):
    if not db.in_transaction:raise ValueError('Wedding progress requires original clear writer')
    guard(db);now=int(time.time())if now is None else now
    saved=rules.current(db,owner,account,now)
    if saved is None or saved['peer_uid']not in roster or owner not in roster or not visible(db,owner,now):return []
    from els_server.domain.seal_quests import objective_increment
    sub=rules.catalog()['subquests'][str(rules.QUEST)]
    event=dict(kind='clear',dungeon=dungeon,level=level)
    if not objective_increment(sub,event,b''):return []
    row=db.execute('SELECT generation,objectives FROM character_quests WHERE owner=?AND quest=?',(owner,rules.QUEST)).fetchone()
    fact=_json(dict(pair=saved['pair_id'],dungeon=dungeon,level=level,roster=sorted(roster),generation=row[0]))
    db.execute('''CREATE TABLE IF NOT EXISTS native_wedding_quest_facts(
        operation TEXT PRIMARY KEY,owner INTEGER NOT NULL,fact_json TEXT NOT NULL)''')
    old=db.execute('SELECT owner,fact_json FROM native_wedding_quest_facts WHERE operation=?',(operation,)).fetchone()
    if old is not None:
        if old!=(owner,fact):raise ValueError('Wedding clear source changed')
        return []
    counts=json.loads(row[1]);counts[str(rules.QUEST)]=min(3,counts[str(rules.QUEST)]+1)
    db.execute('UPDATE character_quests SET objectives=?WHERE owner=?AND quest=?',(_json(counts),owner,rules.QUEST))
    db.execute('INSERT INTO native_wedding_quest_facts VALUES(?,?,?)',(operation,owner,fact))
    from els_server.protocol.quest_messages import progress
    from els_server.protocol.protocol_codec import encode_event
    value=dict(id=rules.QUEST,owner=owner,generation=row[0],objectives={int(k):v for k,v in counts.items()})
    events=[progress([value])]
    for event in events:encode_event(event)
    guard(db);return events
