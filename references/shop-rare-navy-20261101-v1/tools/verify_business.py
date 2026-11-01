"""Owned full-set purchase, registration, rollback and cold/native checks."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import collections,functools,json,sqlite3,struct,sys,tempfile,traceback

W=Path(__file__).resolve().parent
R=W.parents[1]
mode=sys.argv[1]
C=W/('local-candidate'if mode=='local'else'candidate')
sys.dont_write_bytecode=True
sys.path[:0]=[str(C),str(R/'tools'),str(R/'tools/pylibs')]
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage import shop_state
shop_state.catalog=functools.lru_cache(maxsize=16)(shop_state.catalog)
catalog=shop_state.catalog
purchase=shop_state.purchase
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import discard
from els_server.domain.fashion_state import move_fashion
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain import character_custom as custom
from els_server.storage import character_custom as storage
from els_server.protocol import character_custom_messages as wire
from els_server.domain.shop_listing import ice_equipment
from role_native_replay import Replay,IMAGE_SHA
from verify_role_progression_offline import check_unit

scope=json.loads((W/'candidate-scope.json').read_bytes())
checks=[];rows=[]
def check(name,value=True):assert value,name;checks.append(name)
def sql(q,args=()):
    with closing(sqlite3.connect(DB))as db,db:return db.execute(q,args).fetchall()
def items(uid):
    with closing(sqlite3.connect(DB))as db:return load_items(db,uid)
def dump():
    with closing(sqlite3.connect(DB))as db:return tuple(db.iterdump())
def deny(call):
    before=dump()
    try:call()
    except ValueError:pass
    else:raise AssertionError('Expected rejection')
    assert dump()==before
def actor(role,index=0):
    aid=role+100*index
    account=LocalAccount(LocalState(DB),account_id=aid);account.enable_characters()
    c=account.characters.create('Rare'+str(role)+'x'+str(index),role,'create:'+str(aid))
    sql('UPDATE reward_balances SET ed=200000 WHERE uid=?',(c['uid'],))
    return dict(account_id=aid,uid=c['uid'])
def request(t,n=1):return struct.pack('>IIH',1,1200000000+t,n)
def buy(t,a,op):
    uid=a['uid'];before=items(uid);ids={i['uid']for i in before}
    ed=sql('SELECT ed FROM reward_balances WHERE uid=?',(uid,))[0][0]
    ack=purchase(DB,request(t),op,uid)
    new=[i for i in items(uid)if i['uid']not in ids]
    assert sql('SELECT ed FROM reward_balances WHERE uid=?',(uid,))==[(ed-50,)]
    saved=(items(uid),sql('SELECT ed,revision FROM reward_balances WHERE uid=?',(uid,)),sql('SELECT count(*)FROM shop_purchase_receipts'))
    assert purchase(DB,request(t),op,uid)==ack
    assert saved==(items(uid),sql('SELECT ed,revision FROM reward_balances WHERE uid=?',(uid,)),sql('SELECT count(*)FROM shop_purchase_receipts'))
    return before,new

folder=tempfile.TemporaryDirectory(dir=W,prefix='business-'+mode+'-')
DB=Path(folder.name)/'own.sqlite3'
try:
    listed={r['template']for r in catalog()}
    added={p['template']for p in scope['added_packages']}
    check('all1630new packages are offered',added<=listed and len(added)==1630)
    ice_rows=json.loads((C/'analysis/client-6c6b5180/role-ice-catalog.json').read_bytes())['rewards']
    check('true ice outputs still excluded',not {r['template']for r in ice_rows} - ice_equipment())
    if mode=='packages':
        actors={n:actor(n)for n in range(1,16)}
        native=None;native_cases=0;navy_cases=0
        for n,p in enumerate(scope['added_packages']):
            role=int(next(iter(p['contents_by_role'])));a=actors[role];uid=a['uid']
            before,new=buy(p['template'],a,'pack:'+str(p['template']))
            assert collections.Counter(i['template']for i in new)==collections.Counter(p['contents_by_role'][str(role)])
            assert all(i['count']==1 for i in new)
            if any(s in p['name']for s in('海军服特别','沙滩床','水手泳装')):
                navy_cases+=1
                for i in new:
                    if i['template']not in FASHION_EQUIP_SLOTS:continue
                    bag=(i['group'],i['slot']);slot=FASHION_EQUIP_SLOTS[i['template']]
                    move_fashion(DB,struct.pack('>BiBiB',*bag,9,slot,0),uid)
                    if native_cases%32==0:native=Replay()
                    check_unit(native,Characters(DB,a['account_id']).get(uid),items(uid));native_cases+=1
                    move_fashion(DB,struct.pack('>BiBiB',9,slot,*bag,0),uid)
            for i in new:discard(DB,uid,struct.pack('>Qi',i['uid'],1),'discard:'+str(p['template'])+':'+str(i['uid']))
            assert items(uid)==before
            rows.append(dict(template=p['template'],role=role,delivered=len(new),price_ED=50,passed=True))
            if (n+1)%256==0:print('Purchased/replayed/cold',n+1,flush=True)
        check('all1630packages purchase/replay/cold',len(rows)==1630)
        check('all78new navy variants wear/unwear and native cold unit reads',navy_cases==78 and native_cases>500)
    elif mode=='books':
        native_values=[]
        prior=W/'business-books-failure.json'
        passed={r['book']:r for r in json.loads(prior.read_bytes())['rows']}if prior.exists()else{}
        for n,t in enumerate(scope['added_books']):
            rule=custom.catalog()[t]
            if t in passed:
                rows.append(passed[t]);native_values.extend(custom.book_values(rule));continue
            role=rule['units'][0];a=actor(role,n+1);uid=a['uid']
            p=next(p for p in scope['added_packages']if t in p['contents']and str(role)in p['contents_by_role'])
            _before,new=buy(p['template'],a,'book-pack:'+str(t))
            book=next(i for i in new if i['template']==t)
            body=struct.pack('>QQiiIB',book['uid'],rule['custom_id'],rule['type'],0,0,0)
            out=storage.use_book(DB,uid,a['account_id'],body,'use:'+str(t));assert not out['replayed']
            assert not any(i['uid']==book['uid']for i in items(uid))
            saved=dump();assert storage.use_book(DB,uid,a['account_id'],body,'use:'+str(t))['replayed']and dump()==saved
            for value in custom.book_values(rule):
                storage.select(DB,uid,a['account_id'],wire.selection_map({rule['slot']:value}),'apply:'+str(t)+':'+str(value['custom_id']))
                with closing(sqlite3.connect(DB))as db:state=storage.snapshot(db,uid)
                assert state['selected'][rule['slot']]==value
                check_unit(Replay(),Characters(DB,a['account_id']).get(uid),items(uid))
                native_values.append(value)
            rows.append(dict(book=t,package=p['template'],role=role,registered=rule['custom_ids'],passed=True))
        native=Replay();root=native.alloc(0x1600);manager=root+0xdc8;flat=native.alloc(76*256)
        native.write(manager+0x270,struct.pack('<QQQ',flat,flat,flat+76*256));native.write(native.base+0x4817e80,struct.pack('<Q',root))
        for value in native_values:
            raw=wire.registered(value).payload;p=native.alloc(len(raw));native.write(p,raw)
            buf=native.alloc(48);native.write(buf+8,struct.pack('<QQQ',p,p+len(raw),p+len(raw)))
            stream=native.alloc(40);native.call(0x3b6d140,stream);native.call(0x3b6d1c0,stream,buf,0)
            native.write(native.stack-8+0x28,struct.pack('<Q',buf));assert native.call(0xbb7f30,0,0,0,0)&255==1
            assert struct.unpack('<I',native.read(buf+32,4))[0]==len(raw)
        check('all44new books purchased via actual package/register/Apply/replay/cold',len(rows)==44)
        check('original4CD native consumer accepts every new registered value')
    elif mode=='masks':
        import uuid
        from els_server.storage.wear_moves import move
        from els_server.domain.ordinary_accessories import definitions
        a=actor(10);uid=a['uid'];session=str(uuid.uuid4());sequence=1
        for t in (110003559,110003560,110003561,110003562):
            before,new=buy(t,a,'mask:'+str(t));mask=next(i for i in new if i['group']==2)
            bag=(mask['group'],mask['slot']);slot=definitions()[mask['template']]['slots'][0]
            body=struct.pack('>BiBiB',*bag,9,slot,0)
            move(DB,body,uid,account_id=a['account_id'],session_id=session,sequence=sequence)
            saved=dump();move(DB,body,uid,account_id=a['account_id'],session_id=session,sequence=sequence)
            assert dump()==saved;sequence+=1
            check_unit(Replay(),Characters(DB,a['account_id']).get(uid),items(uid))
            move(DB,struct.pack('>BiBiB',9,slot,*bag,0),uid,account_id=a['account_id'],session_id=session,sequence=sequence);sequence+=1
            for i in new:discard(DB,uid,struct.pack('>Qi',i['uid'],1),'discard-mask:'+str(t)+':'+str(i['uid']))
            assert items(uid)==before
            rows.append(dict(package=t,mask=mask['template'],slot=slot,passed=True))
        check('fourLu/Ciel normal masks purchase/wear/replay/cold/native unit/unwear',len(rows)==4)
    elif mode in('boundaries','local'):
        a=actor(1);uid=a['uid'];t=303114
        before,new=buy(t,a,'once');check('sailor rare delivers both alternate top and hair',len(new)==8)
        deny(lambda:purchase(DB,request(303116),'foreign',uid))
        deny(lambda:purchase(DB,request(t,2),'once',uid))
        check('wrong role and conflicting replay reject without writes')
        if mode=='boundaries':
            before=dump()
            with patch('els_server.storage.shop_state.ed_purchase_ack',side_effect=RuntimeError('own encoder failure')):
                try:purchase(DB,request(t),'encode-failure',uid)
                except RuntimeError:pass
                else:raise AssertionError('Encoder failure absent')
            check('encoding failure rolls back ED/items/receipt',dump()==before)
            child=next(p for p in scope['added_packages']if p['template']==t)['contents'][3]
            sql("CREATE TRIGGER fail_member BEFORE INSERT ON inventory_items WHEN NEW.template="+str(child)+" BEGIN SELECT RAISE(ABORT,'own member failure');END")
            before=dump()
            try:purchase(DB,request(t),'member-failure',uid)
            except sqlite3.IntegrityError:pass
            else:raise AssertionError('SQL failure absent')
            check('middle member failure rolls back entire package',dump()==before);sql('DROP TRIGGER fail_member')
            sql('UPDATE reward_balances SET ed=49 WHERE uid=?',(uid,));deny(lambda:purchase(DB,request(t),'poor',uid))
            sql('UPDATE reward_balances SET ed=200000 WHERE uid=?',(uid,))
            from els_server.storage.bag_capacity import allowances
            from els_server.domain.fashion_bundles import ordinary_accessory_members
            from els_server.domain.acquisition_policy import can_acquire
            from els_server.domain.ordinary_accessories import definitions
            check('only4explicit normal mask source members admitted',ordinary_accessory_members()==frozenset((250003175,250003176,250003189,250003190)))
            other=next(t for t,r in definitions().items()if r['compatibility_only']and t not in ordinary_accessory_members())
            check('unrelated retained-only accessory remains blocked',not can_acquire(other))
            group=new[0]['group']
            with closing(sqlite3.connect(DB))as db:limit=allowances(db,uid)[group]
            while sum(i['group']==group for i in items(uid))<limit:
                i=new[0]
                with closing(sqlite3.connect(DB))as db,db:grant_items(db,[dict(template=i['template'],metadata=i['metadata'],group=group,quantity=1)],uid)
            deny(lambda:purchase(DB,request(t),'full',uid));check('full bag no ED/item/receipt increments')
        else:
            check('LOCAL loaded same15517offers',len(listed)==15517)
            check_unit(Replay(),Characters(DB,a['account_id']).get(uid),items(uid));check('LOCAL native cold unit accepted')
    else:raise ValueError(mode)
except BaseException as error:
    result=dict(ok=False,mode=mode,checks=checks,rows=rows,error=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()),fixture=str(DB))
    failure=W/f'business-{mode}-failure.json'
    if failure.exists():
        import time
        failure=W/f'business-{mode}-failure-{time.time_ns()}.json'
    failure.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(result['error']['traceback']);raise
else:
    result=dict(ok=True,mode=mode,checks=checks,rows=rows,native_image_sha256=IMAGE_SHA,live_process=False,formal_database_written=False,natural_GUI=False)
    (W/f'business-{mode}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    folder.cleanup();print(json.dumps(dict(ok=True,mode=mode,cases=len(rows),checks=checks),ensure_ascii=False))
