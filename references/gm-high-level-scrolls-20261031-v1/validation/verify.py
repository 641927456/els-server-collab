from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import ast,hashlib,json,sqlite3,struct,sys,tempfile,uuid

ROOT=Path('G:/els');WORK=Path(__file__).resolve().parent
binding=json.loads((WORK/'binding.json').read_bytes());BASE=Path(binding['parent_root']);SOURCE=WORK/'source'
sys.dont_write_bytecode=True
sys.path[:0]=[str(BASE),str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
import els_server,els_server.domain,els_server.storage
els_server.__path__.insert(0,str(SOURCE/'els_server'))
els_server.domain.__path__.insert(0,str(SOURCE/'els_server/domain'))
els_server.storage.__path__.insert(0,str(SOURCE/'els_server/storage'))
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_MAX_STACKS,item_body,fixture
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.seal_quests import load_character
from els_server.storage import wisdom_potions as experience
from els_server.storage import enhancement_scroll as enhancement
from els_server.protocol.dungeon_messages import return_user_sync
from els_server.game_data import client_data
from role_native_replay import Replay,IMAGE_SHA

checks=[];native=[];replay=Replay();data=client_data()
for t in (117534,117535,163313,710092):
    assert t in VERIFIED_TEMPLATES and TEMPLATE_MAX_STACKS[t]==300
    raw=data.item(t)['record'];at=replay.alloc(len(raw));replay.write(at,raw)
    assert replay.call(0x19803a0,0,at)==4
    item=dict(uid=1001001,template=t,metadata=2,count=3,group=4,slot=20)
    body=item_body(item);read=replay.item(body)
    assert read['ok']==1 and read['consumed']==len(body)
    native.append(dict(template=t,bag=4,item_bytes=len(body),native_reader=True))
checks.append('four grantable templates match native bag classification and item reader')

with tempfile.TemporaryDirectory(prefix='gm-scroll-',dir=WORK) as tmp:
    path=Path(tmp)/'private.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters();account.get_inventory_snapshot();uid=1001
    def dump():
        with closing(sqlite3.connect(path))as db:return list(db.iterdump())
    def give(t,count=1):
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            changed=grant_items(db,[dict(template=t,metadata=2,group=4,quantity=count)],uid)
            return next(i['uid']for i in changed if i['template']==t)
    def level(n,xp=None):
        with closing(sqlite3.connect(path))as db,db:
            db.execute('UPDATE characters SET level=? WHERE uid=?',(n,uid))
            db.execute('UPDATE reward_balances SET experience=? WHERE uid=?',(data.thresholds[n-1]if xp is None else xp,uid))
    def notice(db,items,wallet):return return_user_sync(account.get_location(),account.get_skills(),wallet,items,load_character(db,uid,1))
    def prepare(db):assert db.in_transaction
    def use(item,quantity=1,op=None,*,single=False,aid=1,body=None):
        payload=body or struct.pack('>QQiiIB',item,0 if single else quantity,0,0,0,0 if single else 1)
        return experience.perform(path,uid,aid,payload,op or str(uuid.uuid4()),account.reward_store,prepare=prepare,notice=notice)
    def check_unit(event,expected_level,expected_exp):
        ok,used,dto,_,_=replay.unit(event.payload)
        assert ok==1 and used==len(event.payload)-9
        assert replay.read(dto+0x65,1)[0]==expected_level
        assert struct.unpack('<i',replay.read(dto+0x66,4))[0]==expected_exp
    level(4,data.thresholds[3]+100)
    scroll=give(710092,6);before=account.reward_store.balances()
    for target in ('encode_event','_commit'):
        frozen=dump()
        with patch.object(experience,target,side_effect=ValueError('controlled failure')):
            try:use(scroll)
            except ValueError:pass
            else:raise AssertionError('missing EXP rollback')
        assert dump()==frozen
    op='sage-batch';events=use(scroll,3,op)
    assert [e.kind for e in events]==[0x21a,0xd9]
    assert account.reward_store.balances()['experience']==data.thresholds[6]
    assert account.reward_store.balances()['ed']==before['ed']
    with closing(sqlite3.connect(path))as db:
        assert db.execute('SELECT count FROM inventory_items WHERE uid=?',(scroll,)).fetchone()==(3,)
        assert db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()==(7,)
    check_unit(events[1],7,data.thresholds[6])
    frozen=dump();use(scroll,3,op);assert dump()==frozen
    # An older response must display the current slot after another valid use.
    use(scroll,single=True);frozen=dump();retry=use(scroll,3,op);assert dump()==frozen
    check_unit(retry[1],8,data.thresholds[7])
    checks.append('single and batch sage use, exact debit/level/EXP, native D9, current-state replay')
    for n,q,aid in ((99,1,1),(98,2,1),(4,3,1),(4,1,2)):
        level(n);frozen=dump()
        try:use(scroll,q,aid=aid)
        except ValueError:pass
        else:raise AssertionError('missing EXP refusal')
        assert dump()==frozen
    level(98);use(scroll)
    assert account.reward_store.balances()['experience']==data.thresholds[98]
    level(4,0);frozen=dump()
    try:use(scroll)
    except ValueError:pass
    else:raise AssertionError('inconsistent EXP accepted')
    assert dump()==frozen
    checks.append('maximum level, excessive batch, insufficient stack, wrong account and inconsistent EXP refuse without writes')
    # Existing retained wisdom potions retain their original reader and receipts.
    from els_server.domain.wisdom_potions import TEMPLATES,definitions
    for t in TEMPLATES:
        level(4)
        with closing(sqlite3.connect(path))as db,db:
            item_uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
            slot=next(i for i in range(20,60)if not db.execute('SELECT 1 FROM inventory_items WHERE owner=? AND bag_group=4 AND slot=?',(uid,i)).fetchone())
            db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(item_uid,uid,t,0,1,4,slot))
            db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(item_uid+1,))
        op='wisdom-'+str(t);events=use(item_uid,op=op,single=True)
        amount=(data.thresholds[4]-data.thresholds[3])*definitions()[t]['percent']//100
        assert account.reward_store.balances()['experience']==data.thresholds[3]+amount
        frozen=dump();use(item_uid,op=op,single=True);assert dump()==frozen
    checks.append('all four retained wisdom potions and legacy receipts remain compatible')
    # Existing fixed-scroll business, including downgrade refusals and rollback.
    from els_server.domain.normal_equipment import definitions as equipment_definitions
    target=dict(template=next(iter(equipment_definitions())),uid=1009001,metadata=1,count=1,group=1,slot=20)
    with closing(sqlite3.connect(path))as db,db:
        db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(target['uid'],uid,target['template'],target['metadata'],1,1,20))
    for t,value in ((117534,11),(117535,12),(163313,13)):
        material=give(t,2);body=struct.pack('>QQ',target['uid'],material);op='high-'+str(t)
        assert data.enchanting.scroll(t)['activation_implemented']
        if value==11:
            frozen=dump()
            with patch.object(enhancement,'_commit',side_effect=ValueError('controlled failure')):
                try:enhancement.apply(path,uid,body,op,account_id=1)
                except ValueError:pass
                else:raise AssertionError('missing enhancement rollback')
            assert dump()==frozen
        events=enhancement.apply(path,uid,body,op,account_id=1)
        with closing(sqlite3.connect(path))as db:
            assert db.execute('SELECT level FROM equipment_enhancement WHERE item_uid=?',(target['uid'],)).fetchone()==(value,)
            assert db.execute('SELECT count FROM inventory_items WHERE uid=?',(material,)).fetchone()==(1,)
            item=next(i for i in load_items(db,uid)if i['uid']==target['uid'])
        assert replay.item(item_body(item))['ok']==1
        frozen=dump();enhancement.apply(path,uid,body,op,account_id=1);assert dump()==frozen
        try:enhancement.apply(path,uid,body,op+'-same',account_id=1)
        except ValueError:pass
        else:raise AssertionError('same enhancement accepted')
        assert dump()==frozen
    checks.append('+11/+12/+13 existing transaction, single debit, native equipment reader, refusal, rollback and replay')

for row in binding['changes']:
    file=SOURCE/row['path'];ast.parse(file.read_text('utf8'))
    row.update(sha256=hashlib.sha256(file.read_bytes()).hexdigest(),size=file.stat().st_size)
(WORK/'binding.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
result=dict(ok=True,checks=checks,native=native,native_image_sha256=IMAGE_SHA,private_database=True,natural_GUI=False,installed=False)
(WORK/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(result,ensure_ascii=False))
