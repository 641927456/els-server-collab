"""Focused new search/qualification/finalization paths on one owned save."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import hashlib,json,sqlite3,sys,tempfile,time,traceback
R=Path('G:/els');W=Path(__file__).resolve().parent
B=R/'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca';C=W/'candidate/els_server'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(B/'vendor'),str(R/'tools/pylibs')]
import els_server,els_server.protocol,els_server.storage
els_server.protocol.__path__.insert(0,str(C/'protocol'));els_server.storage.__path__.insert(0,str(C/'storage'))
from els_server.storage import mentor_relations as store,mentor45000_scope,character_lifecycle as lifecycle
from els_server.storage.characters import Characters,DEFAULT_CHARACTER
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.domain.character_rules import CLASSES
from els_server.protocol import mentor_messages as wire
from els_server.protocol.protocol_codec import encode_event

root=Path(tempfile.mkdtemp(prefix='owned-mentor-edges-',dir=W)).resolve();assert root.parent==W.resolve()
path=root/'game.sqlite3'
report=dict(ok=False,checks=[],fixture=str(root),fixture_cleaned=False,explicit_existing_relation_fixture=True,
    current_lease_tested=False,natural_GUI=False,production_database_access=False)
def dump():
    with closing(sqlite3.connect(path))as db:return list(db.iterdump())
try:
    account=LocalAccount(LocalState(path));account.enable_characters()
    with closing(sqlite3.connect(path))as db,db:
        db.execute('INSERT INTO characters VALUES(1001,?,?,?, ?,1,0,0,0)',
            ('MentorOwnA','mentorowna',DEFAULT_CHARACTER['unit_type'],DEFAULT_CHARACTER['unit_class']))
        db.execute('INSERT INTO character_owners VALUES(1001,1)')
    student=Characters(path,2).create('MentEdgeStu',1,'mentor-edge-student')['uid']
    alternate=Characters(path,2).create('MentEdgeAlt',1,'mentor-edge-alternate')['uid']
    for uid in(student,alternate):LocalState(path,uid)
    def guard(db):assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(student,)).fetchone()==(2,)
    messages=[]
    def encoder(db,result,repeated):
        acknowledgement=wire.acknowledgement(0x714);encode_event(acknowledgement)
        if not repeated:
            notice=wire.search_notice(store.character(db,uid=student));encode_event(notice);messages.append(notice)
        return dict(result,replayed=repeated)
    now=1800000000;before=dump()
    def fail(db,result,repeated):encoder(db,result,repeated);raise RuntimeError('Owned late search encoding failure')
    try:store.search(path,student,2,'search0',guard,fail,now=now)
    except RuntimeError:pass
    else:raise AssertionError('Late search encoder must fail')
    assert dump()==before;messages.clear()
    first=store.search(path,student,2,'search1',guard,encoder,now=now)
    assert first['next_at']==now+60 and len(messages)==1
    before=dump()
    assert store.search(path,student,2,'search1',guard,encoder,now=now+1)['replayed']
    assert dump()==before and len(messages)==1
    try:store.search(path,student,2,'search2',guard,encoder,now=now+59)
    except store.MentorError as error:assert error.code==1959
    else:raise AssertionError('Search must wait60seconds')
    assert dump()==before
    assert not store.search(path,student,2,'search2',guard,encoder,now=now+60)['replayed'] and len(messages)==2
    report['checks'].append('Search encoder rollback; one broadcast per operation; cold persisted60s cooldown;59 denies and exact60 succeeds')
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE');store.ensure(db)
        db.executemany('INSERT INTO native_mentor_relations VALUES(?,?,?,?,?)',
            ((1001,student,0,'owned-existing-relation',now),(student,1001,1,'owned-existing-relation',now)))
        db.execute('UPDATE characters SET level=99 WHERE uid IN(?,?)',(student,alternate))
        def alternate_guard(db):assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(alternate,)).fetchone()==(2,)
        try:mentor45000_scope._actor(db,alternate,2,alternate_guard)
        except ValueError as error:assert 'no student' in str(error)
        else:raise AssertionError('An alternate cannot qualify while this account has a student')
    report['checks'].append('Another current99 role cannot qualify while any character on that account remains a student')
    from els_server.storage.character_selection import save as save_selection
    save_selection(path,1,[0]*5,[1001])
    with patch.object(lifecycle,'current_time',return_value=now):
        scheduled=lifecycle.change(path,1,1001,'schedule')
    assert scheduled['until']==now+3*lifecycle.DAY
    with patch.object(lifecycle,'current_time',return_value=scheduled['until']):
        finalized=lifecycle.change(path,1,1001,'finalize')
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        assert store.relation(db,student)is None
        assert not store.account_has_student(db,2)
        assert db.execute('SELECT uid FROM characters WHERE uid=1001').fetchone()==(1001,)
        mentor45000_scope._actor(db,alternate,2,alternate_guard)
        assert not store.exists(db,'native_mentor_graduations')
    report['checks'].append('Actual schedule/finalize API removes both social rows in its transaction, retains tombstone data, creates no graduation award and releases account qualification')
    report.update(ok=True,source_files={p.relative_to(C).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in C.rglob('*.py')})
except BaseException:report['error']=traceback.format_exc()
if report['ok']:
    entries=list(root.rglob('*'))
    assert all(p.resolve().is_relative_to(root)and not p.is_symlink()and not p.is_junction()for p in entries)
    for p in sorted(entries,key=lambda p:len(p.parts),reverse=True):p.unlink()if p.is_file()else p.rmdir()
    root.rmdir();report['fixture_cleaned']=True
out=W/('storage-edges-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));raise SystemExit(not report['ok'])
