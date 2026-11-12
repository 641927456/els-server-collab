"""Finite material/progress authority and unfinished weekly rotation, owned SQL fixture."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import hashlib,json,sqlite3,sys,time,traceback
K=Path(__file__).resolve().parent;S=K/'reward-source-v1';R=Path('G:/els');sys.dont_write_bytecode=True;sys.path[:0]=[str(S),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
from els_server.storage.seal_quests import QuestState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.pet_battle_quest_scope import record
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.protocol.quest_messages import initialization
report=dict(ok=False,native_Game=False,production_database_access=False,checks=[])
try:
    pins=json.loads((K/'reward-composition-v5.json').read_bytes())['source_pins']
    assert all(hashlib.sha256((S/rel).read_bytes()).hexdigest()==sha for rel,sha in pins.items())
    directories=sorted((p for p in(K/'tls-network-v1').iterdir()if p.name.isdecimal()and int(p.name)<1793975911287632500),key=lambda p:int(p.name));path=directories[-1]/'game.sqlite3'
    with closing(sqlite3.connect(path))as db:
        uid=db.execute("SELECT uid FROM characters WHERE name='PetWeeklyAlt'").fetchone()[0];identity=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()[0]
        assert db.execute('SELECT COUNT(*)FROM pet_battle_results').fetchone()[0]==3
        period=db.execute('SELECT week FROM account_pet_battle_quest_bindings WHERE account=?',(identity,)).fetchone()[0]
        foreign=db.execute('SELECT match_id FROM pet_battle_results WHERE winner!=?LIMIT 1',(uid,)).fetchone()[0]
    def guard(db):
        assert Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()==path.resolve()
        require_active_character(db,uid);require_owner(db,uid,identity)
    def saved():
        with closing(sqlite3.connect(path))as db:return db.execute('SELECT objectives FROM character_quests WHERE owner=? AND quest=54620',(uid,)).fetchone()[0],sum(i['count']for i in load_items(db,uid)if i['template']==324815)
    before=saved();assert before==('{"54620": 0}',7)
    try:
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE');guard(db)
            grant_items(db,[dict(template=324815,metadata=2,group=4,quantity=1)],uid)
    except ValueError:pass
    else:raise AssertionError('Generic new material grant must fail')
    assert saved()==before
    now=int(time.time())+7*86400
    try:
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE');guard(db);record(db,uid,identity,foreign,guard,now)
    except ValueError:pass
    else:raise AssertionError('Another winner receipt cannot advance this task')
    assert saved()==before
    selected=QuestState(path,uid,account_id=identity,account_source_guard=guard)
    with patch('els_server.storage.seal_quests.time.time',return_value=now):
        assert any(r['id']==54620 for r in selected.snapshot()['active'])
        selected.record('owned-pet-false-pve-clear',dict(kind='clear',dungeon=30000,level=99),b'owned unrelated PVE source',validate=guard)
    assert saved()==before
    report['checks'].append('Unqualified generic324815 grant, another winner receipt and ordinary PVE clear cannot grant tokens or advance54620')
    next_period=now+7*86400
    result=selected.action('accept',dict(quest=54620,npc=10025),'owned-pet-second-week-accept',lambda result:[initialization(result['state'])],now=next_period)
    row=next(r for r in result['state']['active']if r['id']==54620);assert row['objectives']=={54620:0}and saved()[1]==7
    with closing(sqlite3.connect(path))as db:
        assert db.execute('SELECT COUNT(*)FROM pet_battle_quest_history WHERE account=?',(identity,)).fetchone()[0]==2
        assert db.execute('SELECT week FROM account_pet_battle_quest_bindings WHERE account=?',(identity,)).fetchone()[0]>period
    report['checks'].append('An unfinished previous-week task rotates through the shared acceptance writer and retains reward inventory/history')
    report.update(ok=True,source_pins=pins)
except BaseException:report['error']=traceback.format_exc()
p=K/('weekly-authority-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(dict(ok=report['ok'],checks=report['checks'],report=str(p),error=report.get('error'))))
if not report['ok']:raise SystemExit(1)
