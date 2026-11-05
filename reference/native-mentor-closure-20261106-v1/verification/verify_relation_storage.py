"""Owned SQL fixtures: consent result, rollback,48h boundary and one graduation letter."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,struct,sys,tempfile,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor'),str(R/'tools/pylibs')]
import els_server,els_server.protocol,els_server.storage
els_server.protocol.__path__.insert(0,str(W/'candidate/els_server/protocol'))
els_server.storage.__path__.insert(0,str(W/'candidate/els_server/storage'))
from els_server.storage import mentor_relations as store
from els_server.protocol import mentor_messages as wire,quest_messages
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.characters import Characters,DEFAULT_CHARACTER
from els_server.storage.seal_quests import QuestState
from els_server.domain.mentor45000 import LIMITS
from els_server.domain.character_rules import CLASSES
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.player_mail import require_recipient
from els_server.storage.game_mail import inbox,MailError
from els_server.storage.mail_attachments import pending

root=Path(tempfile.mkdtemp(prefix='owned-mentor-storage-',dir=W)).resolve()
assert root.parent==W.resolve() and not root.is_symlink() and not root.is_junction()
path=root/'game.sqlite3'
report=dict(ok=False,checks=[],fixture=str(root),fixture_cleaned=False,natural_GUI=False,
    current_lease_tested=False,qualification_objectives_are_explicit_fixture=True,
    production_database_access=False)

def dump():
    with closing(sqlite3.connect(path)) as db:
        return list(db.iterdump())

def owned(db):
    assert db.execute('SELECT account_id FROM character_owners WHERE uid=1001').fetchone()==(1,)

def encoder(db,result,repeated):
    events=[]
    if result['action']=='accepted':
        for uid in result['owners']:
            saved=store.relation(db,uid)
            row=store.public_info(db,saved['partner'],None,saved=saved)
            events.append(wire.partner(row))
    else:
        events=[wire.removed(uid,'师徒关系已解除。') for uid in result['owners']]
    for event in events:encode_event(event)
    return dict(result,replayed=repeated)

def perform(kind,owner,account,payload,operation,now,invitation=None,fail=False):
    def guard(db):
        assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()==(account,)
    def encode(db,result,repeated):
        answer=encoder(db,result,repeated)
        if fail:raise RuntimeError('Injected failure after native result encoding')
        return answer
    return store.perform(path,owner,account,kind,payload,operation,guard,encode,
                         now=now,invitation=invitation)

try:
    account=LocalAccount(LocalState(path));account.enable_characters()
    # LocalState's legacy1001 containers predate a character roster. Supply
    # this isolated fixture's matching role before normal new-character APIs.
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('INSERT INTO characters VALUES(1001,?,?,?, ?,1,0,0,0)',
            ('MentorOwnTeacher','mentorownteacher',DEFAULT_CHARACTER['unit_type'],DEFAULT_CHARACTER['unit_class']))
        db.execute('INSERT INTO character_owners VALUES(1001,1)')
    students=[Characters(path,i).create('MentorOwn'+str(i),1,'mentor-own-create-'+str(i))['uid'] for i in (2,3)]
    alt=Characters(path,2).create('MentorOwnAlt',1,'mentor-own-alt')['uid']
    for uid in [*students,alt]:LocalState(path,uid)
    career=next(k for k,v in CLASSES.items() if v['base_class']==1 and v['stage']==2)
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE characters SET level=99,unit_class=?,revision=revision+1 WHERE uid=1001',(career,))
    quest=QuestState(path,1001,account_id=1,account_source_guard=owned)
    quest.action('accept',dict(quest=45000,npc=10025),'mentor-owned-qualification',lambda r:[])
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE character_quests SET objectives=? WHERE owner=1001 AND quest=45000',
                   (json.dumps({str(k):v for k,v in LIMITS.items()},sort_keys=True),))
        grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=20)
                        for t in (701000,78150,78250)],1001)
    request=quest_messages.request(0xf4,struct.pack('>iiI5B',45000,0,0,0,0,0,0,0))
    def claim(r):
        message=quest_messages.initialization(r['state']);encode_event(message);return [message]
    quest.action('claim',request,'mentor-owned-qualification-claim',claim)
    with closing(sqlite3.connect(path)) as db:
        assert store.role(db,1001,1)==0
        assert store.role(db,students[0],2)==store.role(db,students[1],3)==1
    report['checks'].append('Canonical account45000 completion and second-job teacher; new student account eligibility')
    now=1800000000
    invitation=dict(teacher=1001,student=students[0],recipient=students[0],generation='owned-mentor-generation1')
    raw=struct.pack('>Q',1001)+wire.EMPTY_ANSWER_INFO+b'\1'+struct.pack('>i',1964)
    before=dump()
    try:perform(0x1eb,students[0],2,raw,'accept1',now,invitation,True)
    except RuntimeError:pass
    else:raise AssertionError('Late accept encoder must fail')
    assert dump()==before
    accepted=perform(0x1eb,students[0],2,raw,'accept1',now,invitation)
    assert accepted['action']=='accepted' and not accepted['replayed']
    before=dump()
    assert perform(0x1eb,students[0],2,raw,'accept1',now)['replayed'] and dump()==before
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*)FROM native_mentor_relations').fetchone()==(2,)
    report['checks'].append('Late accept rollback includes new DDL; exactly two mirrored rows; exact replay has no writes')
    invitation2=dict(teacher=1001,student=students[1],recipient=students[1],generation='owned-mentor-conflict')
    before=dump()
    try:perform(0x1eb,students[1],3,raw,'conflict',now,invitation2)
    except store.MentorError:pass
    else:raise AssertionError('One teacher cannot have two student characters')
    assert dump()==before
    target=struct.pack('>Q',1001)
    try:perform(0x1e4,students[0],2,target,'remove1',now+store.MIN_RELATION_SECONDS-1)
    except store.MentorError as error:assert error.code==1974
    else:raise AssertionError('48h boundary not reached')
    assert dump()==before
    removed=perform(0x1e4,students[0],2,target,'remove1',now+store.MIN_RELATION_SECONDS)
    assert removed['action']=='removed' and removed['mail_id']is None
    before=dump()
    assert perform(0x1e4,students[0],2,target,'remove1',now+store.MIN_RELATION_SECONDS)['replayed'] and dump()==before
    invitation['generation']='owned-mentor-generation2'
    perform(0x1eb,students[0],2,raw,'accept2',now+store.MIN_RELATION_SECONDS,invitation)
    report['checks'].append('Second student rejected;48h-1 denies; exact48h removes; immediate rebind has no reenrollment penalty')
    before=dump()
    try:perform(0x1e4,students[0],2,target,'remove1',now+store.MIN_RELATION_SECONDS)
    except store.MentorError:pass
    else:raise AssertionError('Old removal replay must not erase a new generation')
    assert dump()==before
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(students[0],))
        assert store.role(db,students[0],2)==1
    before=dump()
    deadline=now+2*store.MIN_RELATION_SECONDS
    try:perform(0x1e4,students[0],2,target,'graduate',deadline,fail=True)
    except RuntimeError:pass
    else:raise AssertionError('Late graduation encoder must fail')
    assert dump()==before
    result=perform(0x1e4,students[0],2,target,'graduate',deadline)
    assert result['action']=='graduated' and result['mail_id']
    before=dump()
    assert perform(0x1e4,students[0],2,target,'graduate',deadline)['replayed'] and dump()==before
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*)FROM native_mentor_graduations').fetchone()==(1,)
        assert db.execute('SELECT COUNT(*)FROM native_mentor_relations').fetchone()==(0,)
        assert pending(db,result['mail_id'],now=deadline)['template']==189801
        require_recipient(db,result['mail_id'],students[0])
        try:require_recipient(db,result['mail_id'],alt)
        except MailError:pass
        else:raise AssertionError('Same-account alt cannot claim the graduation letter')
        assert store.role(db,students[0],2)==2
    assert inbox(path,2,students[0],now=deadline)[0]==1
    assert inbox(path,2,alt,now=deadline)[0]==0
    report['checks'].append('Old generation replay rejected;99 does not auto graduate; atomic one-time letter and relation end; same-account alt hidden/denied')
    report.update(ok=True,source_files={p.relative_to(W/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (W/'candidate').rglob('*.py')})
except BaseException:
    report['error']=traceback.format_exc()
if report['ok']:
    entries=list(root.rglob('*'))
    assert all(p.resolve().is_relative_to(root) and not p.is_symlink() and not p.is_junction() for p in entries)
    for p in sorted(entries,key=lambda p:len(p.parts),reverse=True):p.unlink() if p.is_file() else p.rmdir()
    root.rmdir();report['fixture_cleaned']=True
out=W/('relation-storage-'+str(time.time_ns())+'.json')
out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
