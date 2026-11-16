"""Production wedding parcel callback in the real accepted-couple writer."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import hashlib,json,shutil,sqlite3,struct,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;B=W/'test-source-v1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),'G:/els/tools/pylibs','G:/els']
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.characters import Characters,DEFAULT_CHARACTER
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage import relationships,weddings,relationship_mail,game_mail
from els_server.protocol import relationship_messages as rel,wedding_messages as wire,mail_attachment_messages as mailwire
from els_server.protocol.social_messages import wstring

root=Path(tempfile.mkdtemp(prefix='owned-reservation-mail-',dir=W)).resolve();path=root/'game.sqlite3'
report=dict(ok=False,fixture=str(root),fixture_cleaned=False,production_database_access=False,native_Game=False,checks=[])
def dump():
    with closing(sqlite3.connect(path))as db:return list(db.iterdump())
def guard(db):assert db.execute('SELECT account_id FROM character_owners WHERE uid=1001').fetchone()==(1,)
def book():
    with closing(sqlite3.connect(path))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        return weddings.reserve(db,1001,1,wire.request(0x887,raw),raw,'owned-mail-reservation',now=now,
            guard=guard,issue=relationship_mail.reservation,encode=lambda row,changes,replayed:[wire.inventory_ack(0x888,changes)])
try:
    account=LocalAccount(LocalState(path));account.enable_characters()
    with closing(sqlite3.connect(path))as db,db:
        db.execute('INSERT INTO characters VALUES(1001,?,?,?,?,1,0,0,0)',
                   ('ParcelGroom','parcelgroom',DEFAULT_CHARACTER['unit_type'],DEFAULT_CHARACTER['unit_class']))
        db.execute('INSERT INTO character_owners VALUES(1001,1)')
    bride=Characters(path,2).create('ParcelBride',2,'owned-bride')['uid']
    guest=Characters(path,3).create('ParcelGuest',3,'owned-guest')['uid']
    alt=Characters(path,1).create('ParcelAlt',4,'owned-alt')['uid']
    for uid in(bride,guest,alt):LocalState(path,uid)
    with closing(sqlite3.connect(path))as db,db:
        grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=1),dict(template=277142,metadata=0,group=4,quantity=1)],1001)
        ring=next(i for i in load_items(db,1001)if i['template']==277142)
    now=int(time.time())
    with closing(sqlite3.connect(path))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        relationships.propose(db,1001,1,bride,2,'groom','bride',rel.descriptor('ParcelBride'),'owned-proposal',guard=guard,encode=lambda *args:[],now=now)
        accepted=struct.pack('>bQ',0,1001)+wstring('ParcelGroom')+struct.pack('>QBH',0,0,0)+struct.pack('>Q',bride)+wstring('ParcelBride')+bytes(1)+rel.descriptor('ParcelBride')
        relationships.answer(db,bride,2,1001,1,'bride','groom',accepted,'owned-acceptance',guard=guard,encode=lambda *args:[],now=now)
    ends=(now//3600+1)*3600+86340
    raw=struct.pack('>bbQQQB',2,0,ends,bride,ring['uid'],0)+wstring('自有婚礼')+wstring('private77')+struct.pack('>bIQ',13,1,guest)
    before=dump()
    with patch.object(wire,'inventory_ack',side_effect=ValueError('Owned late reservation ACK failure')):
        try:book()
        except ValueError as error:assert str(error)=='Owned late reservation ACK failure'
        else:raise AssertionError('Late ACK failure accepted')
    assert dump()==before
    calls=0;original=mailwire.detail
    def third(row):
        global calls
        calls+=1
        if calls==3:raise ValueError('Owned third parcel encoding failure')
        return original(row)
    with patch.object(mailwire,'detail',side_effect=third):
        try:book()
        except ValueError as error:assert str(error)=='Owned third parcel encoding failure'
        else:raise AssertionError('Partial parcel error accepted')
    assert dump()==before
    report['checks'].append('Real parcel factory: third-mail and final-ACK encoding failures roll back all mail/escrow, schema, reservation, invitations and exact ring debit')
    answer=book();assert answer[0].payload[:4]==bytes(4)
    with closing(sqlite3.connect(path))as db:
        assert db.execute('SELECT COUNT(*)FROM native_relationship_mail').fetchone()==(8,)
        assert not any(i['template']==277142 for i in load_items(db,1001))
    expected={1001:{277144:1,277147:1,277151:1,277150:30},bride:{277146:1,277147:1,277151:1},guest:{277152:1}}
    for uid,account in((1001,1),(bride,2),(guest,3)):
        count,letters=game_mail.inbox(path,account,uid,folder=2)
        assert count==len(expected[uid])and {r['item']['template']:r['item']['count']for r in letters}==expected[uid]
        assert all(r['mail_type']==(23 if uid==guest else 24)for r in letters)
        ids=[r['id']for r in letters]
        game_mail.claim(path,account,uid,ids,lambda ids,ed,changes,awarded:mailwire.claim_ack(ids,ed,changes=changes,counts=awarded),include_items=True,include_claim_counts=True)
        with closing(sqlite3.connect(path))as db:
            assert {t:sum(i['count']for i in load_items(db,uid)if i['template']==t)for t in expected[uid]}==expected[uid]
    assert game_mail.inbox(path,1,alt,folder=2)==(0,[])
    before=dump();assert book()[0].payload==bytes(8)and dump()==before
    report['checks'].append('One consumed ring produces exactly8 source-bound letters: both spouses each robe/celebrity/ticket, proposer30 blanks, guest1 personalized ticket; actual mailbox claims preserve exact quantities and replay adds nothing')
    report['ok']=True
except Exception:
    report['error']=traceback.format_exc();print(report['error'],flush=True)
finally:
    report['candidate_files']={p.relative_to(W/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'candidate').rglob('*')if p.is_file()}
    if report['ok']:
        assert root.parent==W.resolve()and root.name.startswith('owned-reservation-mail-')and not root.is_symlink()
        assert not any(p.is_symlink()for p in root.rglob('*'));shutil.rmtree(root);report['fixture_cleaned']=not root.exists()
    out=W/('reservation-mail-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(dict(ok=report['ok'],checks=report['checks'],error=report.get('error'),evidence=str(out)),ensure_ascii=False))
if not report['ok']:raise SystemExit(1)
