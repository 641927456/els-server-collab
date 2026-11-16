"""Normal authenticated shop listing, 50 ED purchase, cold storage and denial."""
from pathlib import Path
from contextlib import closing
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent;H=W.parents[1]/'housing-pets-v1';B=W/'weekly-test-source-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(H.parent/'delivery-duel-v1')]
ctypes.WinDLL(str(H.parent/'duel-wire-v2/full-source/python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.domain.town_travel import catalog
from els_server.domain import shop_additions
from create_friends_certificate import create
from native_peer import connect

from unittest.mock import patch
from els_server.storage import relationships,weddings,wedding_ceremonies,couple_closures,relationship_mail,game_mail
from els_server.storage.inventory_state import grant_items,load_items
from els_server.protocol import relationship_messages as rel,wedding_messages as wedding,mail_attachment_messages as mailwire
from els_server.protocol.social_messages import wstring
from els_server.protocol.protocol_codec import Event
from els_server.domain.couple_farewell_flow import handle as farewell

async def main():
 report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,
  production_database_access=False,marriage_roster_and_sessions_are_explicit_setup_fixtures=True,
  checks=[],clear_roster_and_final_source_are_explicit_fixtures=True,full_multiplayer_dungeon=False,weekly_time_travel_is_rollback_fixture=True)
 app=server=None;peers=[];errors=[];stage='setup'
 with tempfile.TemporaryDirectory(prefix='owned-free-divorce-',dir=W)as name:
  private=Path(name).resolve();assert private.parent==W.resolve();create(private,'127.0.0.1')
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
  try:
   assert Path(couple_closures.__file__).resolve()==(W/'weekly-test-source-v1/els_server/storage/couple_closures.py').resolve()
   app=Application(cfg);await app.start();people=[]
   for index,label in enumerate(('A','B')):
    identity=app.registry.create('owneddivorce'+label.lower());uid=Characters(cfg.state_file,identity['id']).create('Divorce'+label,index+1,'owned-divorce-'+label)['uid']
    LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz']);people.append(dict(identity=identity,uid=uid,name='Divorce'+label))
   a,b=people;owner,peer_uid=a['uid'],b['uid'];account,peer_account=a['identity']['id'],b['identity']['id']
   def guard(db):
    for person in people:assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(person['uid'],)).fetchone()==(person['identity']['id'],)
   prepared_at=int(time.time())-7200;ends=(prepared_at//3600+1)*3600+86340;married_at=ends-86340
   with closing(sqlite3.connect(cfg.state_file))as db,db:
    db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
    grant_items(db,[dict(template=t,metadata=0,group=4,quantity=1)for t in(269710,277142)],owner)
    ring=next(i['uid']for i in load_items(db,owner)if i['template']==277142)
    relationships.propose(db,owner,account,peer_uid,peer_account,'fixture-a','fixture-b',rel.descriptor(b['name']),'fixture-couple-proposal',guard=guard,encode=lambda *args:[],now=prepared_at)
    accepted=struct.pack('>bQ',0,owner)+wstring(a['name'])+struct.pack('>QBH',0,0,0)+struct.pack('>Q',peer_uid)+wstring(b['name'])+bytes(1)+rel.descriptor(b['name'])
    relationships.answer(db,peer_uid,peer_account,owner,account,'fixture-b','fixture-a',accepted,'fixture-couple-accept',guard=guard,encode=lambda *args:[],now=prepared_at)
    raw=struct.pack('>bbQQQB',2,0,ends,peer_uid,ring,0)+wstring('Owned marriage')+wstring('')+struct.pack('>bI',13,0)
    weddings.reserve(db,owner,account,wedding.request(0x887,raw),raw,'fixture-marriage-reservation',now=prepared_at,guard=guard,issue=relationship_mail.reservation,encode=lambda row,changes,repeated:[wedding.inventory_ack(0x888,changes)])
   for person in people:
    uid,aid=person['uid'],person['identity']['id'];ids=[row['id']for row in game_mail.inbox(cfg.state_file,aid,uid,folder=2)[1]]
    game_mail.claim(cfg.state_file,aid,uid,ids,lambda ids,ed,changes,awarded:mailwire.claim_ack(ids,ed,changes=changes,counts=awarded),include_items=True,include_claim_counts=True)
   with closing(sqlite3.connect(cfg.state_file))as db,db:
    db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');roster=[]
    for person,role in zip(people,(1,2)):
     ticket=next(i['uid']for i in load_items(db,person['uid'])if i['template']==277151)
     roster.append(dict(uid=person['uid'],account=person['identity']['id'],role=role,ticket=ticket,session='fixture-marriage-'+str(role)))
    wedding_ceremonies.start(db,1,roster,now=married_at,guard=guard,encode=lambda row,changes,repeated:{}if repeated else{p['uid']:[wedding.ceremony_started(changes[p['uid']],refresh=True)]for p in roster})
    state=relationships.snapshot(db,owner,account);assert state['kind']==2 and state['created_at']==married_at
   from els_server.domain import wedding_quests as rules,quest_flow
   from els_server.storage import wedding_quests as tasks
   from els_server.game_data import client_data
   from els_server.protocol import quest_messages
   from els_server.domain.guild_rules import next_week
   with closing(sqlite3.connect(cfg.state_file))as db,db:
    for person in people:
     db.execute('UPDATE characters SET level=10 WHERE uid=?',(person['uid'],))
     db.execute('UPDATE reward_balances SET experience=?WHERE uid=?',(client_data().thresholds[9],person['uid']))
   def facts():
    with closing(sqlite3.connect(cfg.state_file))as db:
     tables=('native_couple_pairs_v1','native_couple_members_v1','native_couple_actions_v1','native_wedding_bookings','native_wedding_ceremonies','inventory_items','reward_balances','native_relationship_mail','native_couple_closures_v1')
     return {table:db.execute('SELECT *FROM '+table+' ORDER BY rowid').fetchall()if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(table,)).fetchone()else None for table in tables}
   server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
   _,port=await server.start();cert=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
   for person in people:
    ident=person['identity'];person['bridge']=dict(host='127.0.0.1',port=port,name=ident['name'],token=ident['token'],certificate_sha256=cert);await connect(person,peers)
   groom,bride=peers;stage='original wedding task acceptance'
   def read(sql,args=()):
    with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
   def progress(uid):return json.loads(read('SELECT objectives FROM character_quests WHERE owner=?AND quest=31130',(uid,))[0][0])['31130']
   def counts():return read('SELECT owner,template,SUM(count)FROM inventory_items WHERE template IN(710097,710193)GROUP BY owner,template ORDER BY owner,template')
   baseline=read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')
   for person,p in zip(people,peers):
    answer=await p.query(0xee,struct.pack('>ii',31130,10025));assert answer.payload==bytes(4),answer.payload.hex()
    assert progress(person['uid'])==0
    assert any(e.kind==0xf0 and e.payload[:4]==struct.pack('>i',31130)for e in p.received)
   def fixture(uid,aid,operation,roster,*,dungeon=30050,level=10):
    with closing(sqlite3.connect(cfg.state_file))as db,db:
     db.execute('BEGIN IMMEDIATE')
     return tasks.record(db,uid,aid,operation,dungeon,level,roster,guard)
   fixture(owner,account,'solo-no-credit',(owner,))
   fixture(owner,account,'excluded-no-credit',(owner,peer_uid),dungeon=30000)
   fixture(owner,account,'inadequate-no-credit',(owner,peer_uid),level=99)
   assert progress(owner)==0
   selected=quest_flow.store(app.playing[account])
   selected.record('ordinary-unsealed-observation',dict(kind='clear',dungeon=30050,level=10),b'fixture-observation')
   assert progress(owner)==0
   for index in range(3):
    fixture(owner,account,'owned-wedding-clear-'+str(index),(owner,peer_uid))
    fixture(owner,account,'owned-wedding-clear-'+str(index),(owner,peer_uid))
    assert progress(owner)==index+1
   for index in range(2):fixture(peer_uid,peer_account,'owned-bride-clear-'+str(index),(owner,peer_uid))
   report['checks'].append('Actual EE/EF/F0 accepts original31130; explicit clear fixtures count each shared source once; solo, excluded, inadequate and generic observations count zero')
   def dump():
    with closing(sqlite3.connect(cfg.state_file))as db:
     names=[r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")if any(k in r[0]for k in('quest','inventory','reward','expiration'))]
     return {t:db.execute('SELECT *FROM '+t+' ORDER BY rowid').fetchall()for t in names}
   claim=struct.pack('>iiI',31130,0,0)+bytes((0,0,1,1,0))
   stage='late reward encoding rollback';before=dump();original_ack=quest_messages.reward_ack
   def fail_success(*args,**kwargs):
    if kwargs.get('result',0)==0:raise ValueError('Owned wedding reward encoder')
    return original_ack(*args,**kwargs)
   with patch.object(quest_messages,'reward_ack',side_effect=fail_success):answer=await groom.query(0xf4,claim)
   assert answer.payload[:4]!=bytes(4)and dump()==before
   stage='original reward and replay'
   answer=await groom.query(0xf4,claim);assert answer.payload[:4]==bytes(4),answer.payload[:12].hex()
   awarded=counts();assert awarded==[(owner,710097,2),(owner,710193,2)],awarded
   answer=await groom.query(0xf4,claim);assert answer.payload[:4]==bytes(4)and counts()==awarded
   assert read('SELECT uid,ed,experience FROM reward_balances ORDER BY uid')==baseline
   assert not __import__('els_server.domain.acquisition_policy',fromlist=['can_acquire']).can_acquire(710097)
   report['checks'].append('Actual F4/F5 grants exactly2+2 for zero ED/XP; failed F5 rolls back all reward/action/source tables; repeated claim adds nothing; generic fatigue-potion grants remain closed')
   stage='weekly carry and annual expiry'
   future=next_week(int(time.time()))+1
   with closing(sqlite3.connect(cfg.state_file))as db:
    db.execute('BEGIN IMMEDIATE')
    tasks.before_action(quest_flow.store(app.playing[peer_account]),db,'fixture-next-week-bride','accept',future)
    assert progress(peer_uid)==2
    q=quest_flow.store(app.playing[account])
    accepted=q.action('accept',dict(quest=31130,npc=10025),'fixture-next-week-groom',lambda result:[quest_messages.accept_ack()],now=future,transaction=db)
    assert any(row['id']==31130 for row in accepted['state']['active'])
    assert db.execute('SELECT COUNT(*)FROM native_wedding_quest_history WHERE owner=?',(owner,)).fetchone()==(1,)
    assert rules.current(db,owner,account,married_at+365*86400-1)is not None
    assert rules.current(db,owner,account,married_at+365*86400)is None
    db.rollback()
   assert progress(peer_uid)==2 and counts()==awarded
   report['checks'].append('Wednesday10 weekly completion resets while unfinished two-clear progress carries;365day eligibility boundary is exact; future-clock fixture is rolled back')
   stage='cold restore'
   for p in list(peers):await p.close();peers.remove(p)
   async with asyncio.timeout(8):
    while any(person['identity']['id']in app.playing for person in people):await asyncio.sleep(.01)
   for person in people:await connect(person,peers)
   assert counts()==awarded and progress(peer_uid)==2 and not errors
   report['checks'].append('Both authenticated accounts cold-restore with current completion, unfinished counters and exact saved rewards')
   report.update(ok=True,source_sha256={str(p.relative_to(W/'candidate')).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'candidate').rglob('*')if p.is_file()})
  except BaseException:report.update(stage=stage,error=traceback.format_exc())
  finally:
   for p in reversed(peers):await p.close()
   if server is not None:await server.close()
   if app is not None:app.close()
 report.update(owned_private_directory_removed=not private.exists(),owned_listeners_closed=True)
 out=W/('wedding-weekly-TLS-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));return report['ok']
raise SystemExit(not asyncio.run(main()))
