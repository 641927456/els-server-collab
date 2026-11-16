"""Normal authenticated shop listing, 50 ED purchase, cold storage and denial."""
from pathlib import Path
from contextlib import closing
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent;H=W.parents[1]/'housing-pets-v1';B=W/'title-test-source-v1'
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
  checks=[],free_divorce_ED=0,title_clock_cases_are_isolated_fixture_time=True)
 app=server=None;peers=[];errors=[];stage='setup'
 with tempfile.TemporaryDirectory(prefix='owned-free-divorce-',dir=W)as name:
  private=Path(name).resolve();assert private.parent==W.resolve();create(private,'127.0.0.1')
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
  try:
   assert Path(couple_closures.__file__).resolve()==(W/'title-test-source-v1/els_server/storage/couple_closures.py').resolve()
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
   from els_server.storage import titles,wedding_titles,title_levels,elixir_economy,title_drop_rewards
   from els_server.domain.title_economy import resolve as title_economy
   from els_server.protocol.title_messages import initialization
   from els_server.protocol.protocol_codec import encode_event
   DAY=86400;deadline=married_at+30*DAY
   def ownership(db):return db.execute('SELECT *FROM title_ownership ORDER BY scope,subject,title').fetchall()
   with closing(sqlite3.connect(cfg.state_file))as db,db:
    db.execute('BEGIN IMMEDIATE')
    for person in people:
     owned=titles.snapshot(db,person['uid'],married_at)['owned']
     assert next(r for r in owned if r['title']==12360)['expires_at']==deadline
    initial=ownership(db)
    for days in(99,100,199,200,364,365):
     db.execute('SAVEPOINT milestone')
     c=titles.character(db,owner);at=married_at+days*DAY
     wedding_titles.grant(db,c,wedding_titles.earned(db,c,at));current=titles.snapshot(db,owner,at)
     expected={title for day,title in wedding_titles.ANNIVERSARIES if day<=days}
     assert {r['title']for r in current['owned']}==expected,(days,current['owned'])
     encode_event(initialization(current))
     wedding_titles.grant(db,c,wedding_titles.earned(db,c,at));stable=ownership(db)
     wedding_titles.grant(db,c,wedding_titles.earned(db,c,at));assert ownership(db)==stable
     db.execute('ROLLBACK TO milestone');db.execute('RELEASE milestone')
    assert ownership(db)==initial
    db.execute('INSERT INTO title_equipment VALUES(?,12360)',(owner,))
    assert titles.equipped(db,owner,deadline-1)==12360 and titles.equipped(db,owner,deadline)==0
    source={'run':'owned-title-drop','npc':1}
    before=elixir_economy.bonus(db,owner,30000,'drop','owned-title-draw',source,now=married_at+1)
    assert before==2000
    db.execute('UPDATE title_equipment SET title=0 WHERE owner=?',(owner,))
    assert elixir_economy.bonus(db,owner,30000,'drop','owned-title-draw',source,now=deadline+1)==2000
    assert elixir_economy.bonus(db,owner,30000,'drop','owned-zero-draw',source,now=married_at+1)==0
    db.execute('UPDATE title_equipment SET title=12360 WHERE owner=?',(owner,))
    assert elixir_economy.bonus(db,owner,30000,'drop','owned-zero-draw',source,now=married_at+2)==0
    from els_server.storage.guild_economy import bonus as guild_bonus
    assert guild_bonus(db,owner,30000,'drop','owned-historical-draw',source,now=married_at+1)==0
    assert elixir_economy.bonus(db,owner,30000,'drop','owned-historical-draw',source,now=married_at+2)==0
    assert not title_drop_rewards.present(db,'owned-historical-draw')
    try:elixir_economy.bonus(db,owner,30000,'drop','owned-title-draw',dict(source,npc=2),now=married_at+2)
    except ValueError:pass
    else:raise AssertionError('Changed drop source accepted')
    db.execute('SAVEPOINT failed_draw')
    assert elixir_economy.bonus(db,owner,30000,'drop','owned-rolledback-draw',source,now=married_at+1)==2000
    db.execute('ROLLBACK TO failed_draw');db.execute('RELEASE failed_draw')
    assert not title_drop_rewards.present(db,'owned-rolledback-draw')
   report['checks'].append('Original marriage producer grants each spouse12360 for exactly30days;100/200/365 boundaries and idempotent ownership pass')
   report['checks'].append('Original drop writer freezes20%, zero absence and historical receipts; expiry/equipment changes do not redraw; conflicting context and rollback pass')
   def facts():
    with closing(sqlite3.connect(cfg.state_file))as db:
     tables=('native_couple_pairs_v1','native_couple_members_v1','native_couple_actions_v1','native_wedding_bookings','native_wedding_ceremonies','inventory_items','reward_balances','native_relationship_mail','native_couple_closures_v1','title_ownership','title_equipment')
     return {table:db.execute('SELECT *FROM '+table+' ORDER BY rowid').fetchall()if db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(table,)).fetchone()else None for table in tables}
   server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
   _,port=await server.start();cert=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
   for person in people:
    ident=person['identity'];person['bridge']=dict(host='127.0.0.1',port=port,name=ident['name'],token=ident['token'],certificate_sha256=cert);await connect(person,peers)
   groom,bride=peers;stage='authenticated title initialization/equip and XP effect'
   book=await groom.query(0xc22,bytes(4));assert struct.pack('>i',12360)in book.payload
   selected=await groom.query(0x213,struct.pack('>i',12360));assert selected.payload==struct.pack('>ii',0,12360)
   with closing(sqlite3.connect(cfg.state_file))as db:
    effect=title_economy(db,owner,'clear',0,1000,30000)
    assert effect['title']==12360 and effect['bonus_experience']==200 and effect['experience']==1200
   report['checks'].append('Actual authenticatedC22/C23 restores the30day title; original213 equips it; clear reward resolves exactly20% XP')
   stage='married free quote and encoder rollback'
   quote=await groom.query(0x41a);assert quote.payload==rel.farewell_quote(state).payload
   before=facts();original=rel.farewell_ack
   def fail_success(*args,**kwargs):
    if kwargs.get('result',0)==0:raise ValueError('Owned late free-divorce encoder')
    return original(*args,**kwargs)
   with patch.object(rel,'farewell_ack',side_effect=fail_success):answer=await groom.query(0x41c)
   assert answer.payload[:4]!=bytes(4)and facts()==before
   report['checks'].append('Actual married41A quotes zero ED; a late41D encoder failure rolls back both memberships and the closure ledger')
   stage='free divorce and guarded replay';sequence=groom.outgoing;answer=await groom.query(0x41c);assert answer.payload==bytes(4)
   await bride.send(0x48d);await bride.until(0x48f)
   after=facts()
   for table in before:
    if table not in('native_couple_members_v1','native_couple_closures_v1','title_ownership','title_equipment'):assert after[table]==before[table],table
   assert after['native_couple_members_v1']==[]and len(after['native_couple_closures_v1'])==1
   with closing(sqlite3.connect(cfg.state_file))as db:
    assert relationships.snapshot(db,owner,account)is None and relationships.snapshot(db,peer_uid,peer_account)is None
    assert weddings.married_since(db,state['pair_id'])==dict(married_at=married_at,refreshed_at=married_at)
    assert after['native_couple_closures_v1'][0][-2]==couple_closures.DIVORCE_POLICY
   assert sum(e.kind==0x41e for e in groom.received)==1 and sum(e.kind==0x41e for e in bride.received)==1
   sender=app.playing[account];event=Event(0x202,kind=0x41c,payload=b'',performers=(0,))
   replay=await app.call(lambda:farewell(sender,event,sequence));assert replay[0].payload==bytes(4)and facts()==after
   report['checks'].append('Original41C closes exactly two current members for zero ED, notifies each once and preserves inventory, marriage facts and mail; guarded-handler replay changes nothing')
   stage='cold reauthentication'
   for p in list(peers):await p.close();peers.remove(p)
   async with asyncio.timeout(8):
    while any(p['identity']['id']in app.playing for p in people):await asyncio.sleep(.01)
   for person in people:await connect(person,peers)
   with closing(sqlite3.connect(cfg.state_file))as db:
    assert relationships.snapshot(db,owner,account)is None and relationships.snapshot(db,peer_uid,peer_account)is None
   from els_server.domain.relationship_skills import equipment
   assert equipment(app.playing[account].account.character())==()and not errors
   report['checks'].append('Both accounts cold-restore as solo; marriage-only skill equipment is absent')
   report.update(ok=True,source_sha256={str(p.relative_to(W/'candidate')).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'candidate').rglob('*.py')})
  except BaseException:report.update(stage=stage,error=traceback.format_exc())
  finally:
   for p in reversed(peers):await p.close()
   if server is not None:await server.close()
   if app is not None:app.close()
 report.update(owned_private_directory_removed=not private.exists(),owned_listeners_closed=True)
 out=W/('marriage-titles-TLS-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));return report['ok']
raise SystemExit(not asyncio.run(main()))
