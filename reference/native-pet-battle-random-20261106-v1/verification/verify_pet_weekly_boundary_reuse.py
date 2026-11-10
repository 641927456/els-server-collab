"""Finish only the boundary cases on the owned three-win TLS fixture."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,sys,time,traceback
K=Path(__file__).resolve().parent;S=K/'reward-source-v1';R=Path('G:/els');sys.dont_write_bytecode=True
sys.path[:0]=[str(S),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
from els_server.storage.seal_quests import QuestState
from els_server.protocol import quest_messages as wire
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.inventory_state import load_items
from els_server.storage.pet_battle_quest_scope import record
old_report=K/'weekly-task-TLS-1793975911287632500.json';old=json.loads(old_report.read_bytes())
report=dict(ok=False,native_Game=False,actual_authenticated_TLS=True,weekly_clock_test='same SQL action writer with supplied now',checks=list(old['checks']))
try:
    assert old['stage']=='weekly boundary'and 'LIMIT1' in old['error']and len(old['checks'])==3
    pins=json.loads((K/'reward-composition-v5.json').read_bytes())['source_pins']
    assert all(hashlib.sha256((S/rel).read_bytes()).hexdigest()==sha for rel,sha in pins.items())
    # The immediately preceding owned fixture is retained; no player store is inspected.
    directories=sorted((p for p in(K/'tls-network-v1').iterdir()if p.name.isdecimal()and int(p.name)<1793975911287632500),key=lambda p:int(p.name))
    private=directories[-1];path=private/'game.sqlite3'
    with closing(sqlite3.connect(path))as db:
        assert db.execute('SELECT COUNT(*)FROM pet_battle_results').fetchone()[0]==3
        owner,generation=db.execute('SELECT owner,accepted_action FROM account_pet_battle_quest_bindings').fetchone()
        identity=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()[0]
        uid=db.execute("SELECT uid FROM characters WHERE name='PetWeeklyAlt'").fetchone()[0]
        assert db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()==(99,)
        old_operation=db.execute('SELECT operation_id FROM quest_actions WHERE rowid=?',(generation,)).fetchone()[0]
        old_match=db.execute('SELECT match_id FROM pet_battle_results WHERE winner=?ORDER BY rowid DESC LIMIT 1',(uid,)).fetchone()[0]
    def guard(db):
        assert Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()==path.resolve()
        require_active_character(db,uid);require_owner(db,uid,identity)
    selected=QuestState(path,uid,account_id=identity,account_source_guard=guard)
    def facts():
        with closing(sqlite3.connect(path))as db:
            return {t:db.execute('SELECT *FROM '+t+' ORDER BY 1').fetchall()for t in('character_quests','completed_quests','quest_actions','quest_progress_events','account_pet_battle_quest_bindings','pet_battle_results','pet_battle_quest_operations','pet_battle_quest_history')if db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(t,)).fetchone()}
    def count():
        with closing(sqlite3.connect(path))as db:return sum(i['count']for i in load_items(db,uid)if i['template']==324815)
    original=facts();next_week=int(time.time())+7*86400
    def encode(result):return [wire.initialization(result['state'])]
    request=dict(quest=54620,npc=10025)
    try:selected.action('accept',request,old_operation,encode,now=next_week)
    except ValueError:pass
    else:raise AssertionError('Prior-week operation must not reopen task')
    assert facts()==original
    def failed(result):raise ValueError('owned weekly response failure')
    try:selected.action('accept',request,'owned-pet-next-week-rollback',failed,now=next_week)
    except ValueError:pass
    else:raise AssertionError('Late response must roll back')
    assert facts()==original
    result=selected.action('accept',request,'owned-pet-next-week-accept',encode,now=next_week)
    row=next(r for r in result['state']['active']if r['id']==54620)
    assert row['objectives']=={54620:0}and row['owner']==uid and count()==7
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE');guard(db)
        assert record(db,uid,identity,old_match,guard,next_week)==[]
        assert db.execute('SELECT objectives FROM character_quests WHERE owner=? AND quest=54620',(uid,)).fetchone()==('{"54620": 0}',)
        assert db.execute('SELECT result_floor FROM account_pet_battle_quest_bindings WHERE account=?',(identity,)).fetchone()==(3,)
    report['checks'].append('Weekly SQL boundary: stale prior-week operation refused; late response failure preserves prior completion; fresh acceptance starts0; old sealed result cannot count; original7 materials retained')
    report.update(ok=True,reused_authenticated_TLS=dict(report=old_report.name,sha256=hashlib.sha256(old_report.read_bytes()).hexdigest(),three_sealed_matches=True,cross_character_relogin=True),source_pins=pins)
except BaseException:report['error']=traceback.format_exc()
p=K/('weekly-boundary-reuse-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(dict(ok=report['ok'],checks=report['checks'],report=str(p),error=report.get('error'))))
if not report['ok']:raise SystemExit(1)
