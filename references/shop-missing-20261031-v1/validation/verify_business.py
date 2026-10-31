"""Owned SQLite purchase/use/rollback checks; no player or account databases."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import collections,functools,hashlib,json,sqlite3,struct,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;R=W.parents[1];mode=sys.argv[1]
C=W/('local-candidate' if mode=='local_smoke' else 'candidate')
sys.dont_write_bytecode=True;sys.path[:0]=[str(C),str(R/'tools'),str(R/'tools/pylibs')]
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage.shop_state import catalog,purchase
from els_server.storage import shop_state
# The catalog depends only on frozen input files, not on this fixture's state.
# Reuse each exact role catalog; all purchase/qualification/storage code is real.
shop_state.catalog=functools.lru_cache(maxsize=16)(shop_state.catalog)
catalog=shop_state.catalog
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import discard
from els_server.domain.fashion_state import move_fashion
from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
from els_server.domain import character_custom as custom
from els_server.storage import character_custom as storage
from els_server.protocol import character_custom_messages as wire
from els_server.domain.shop_listing import ice_equipment
from role_native_replay import Replay,IMAGE_SHA
from verify_role_progression_offline import check_unit

scope=json.loads((W/'candidate-scope.json').read_bytes());checks=[];rows=[]
def check(name,condition=True):
    assert condition,name
    checks.append(name)
def req(t):return struct.pack('>IIH',1,1200000000+t,1)
def sql(query,args=()):
    with closing(sqlite3.connect(DB))as db,db:return db.execute(query,args).fetchall()
def dump():
    with closing(sqlite3.connect(DB))as db:return tuple(db.iterdump())
def items(uid):
    with closing(sqlite3.connect(DB))as db:return load_items(db,uid)
def deny(call):
    before=dump()
    try:call()
    except ValueError:pass
    else:raise AssertionError('Expected rejection')
    assert dump()==before
def actor(role,index=0):
    account_id=role+100*index
    a=LocalAccount(LocalState(DB),account_id=account_id);a.enable_characters()
    c=a.characters.create('ShopOwn'+str(role)+'x'+str(index),role,'create:'+str(account_id))
    sql('UPDATE reward_balances SET ed=200000 WHERE uid=?',(c['uid'],))
    return dict(account=a,account_id=account_id,character=c,uid=c['uid'])
def buy(t,actor,op):
    uid=actor['uid'];before=items(uid);old={i['uid']for i in before};ed=sql('SELECT ed FROM reward_balances WHERE uid=?',(uid,))[0][0]
    ack=purchase(DB,req(t),op,uid);after=items(uid);new=[i for i in after if i['uid']not in old]
    assert sql('SELECT ed FROM reward_balances WHERE uid=?',(uid,))==[(ed-50,)]
    snapshot=(items(uid),sql('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)),sql('SELECT COUNT(*) FROM shop_purchase_receipts'))
    assert purchase(DB,req(t),op,uid)==ack
    assert (items(uid),sql('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)),sql('SELECT COUNT(*) FROM shop_purchase_receipts'))==snapshot
    return before,new,ack

folder=tempfile.TemporaryDirectory(dir=W,prefix='business-'+mode+'-');DB=Path(folder.name)/'own.sqlite3'
try:
    if mode=='packages':
        actors={role:actor(role)for role in range(1,16)};native=Replay();native_units=[]
        for n,p in enumerate(scope['added_packages']):
            role=min(map(int,p['contents_by_role']));a=actors[role];uid=a['uid']
            before,new,ack=buy(p['template'],a,'package:'+str(p['template']))
            assert collections.Counter(i['template']for i in new)==collections.Counter(p['contents_by_role'][str(role)])
            assert all(i['count']==1 for i in new)
            # All32 PureHoliday ordinary sets traverse actual wear/cold state;
            # other packages share the identical allocation/record consumers.
            if '纯粹假日'in p['name']:
                native=Replay()
                for i in new:
                    bag=(i['group'],i['slot']);slot=FASHION_EQUIP_SLOTS[i['template']]
                    move_fashion(DB,struct.pack('>BiBiB',*bag,9,slot,0),uid)
                    c=Characters(DB,a['account_id']).get(uid);native_units.append(check_unit(native,c,items(uid)))
                    move_fashion(DB,struct.pack('>BiBiB',9,slot,*bag,0),uid)
            for i in new:discard(DB,uid,struct.pack('>Qi',i['uid'],1),'discard:'+str(p['template'])+':'+str(i['uid']))
            assert items(uid)==before
            rows.append(dict(template=p['template'],role=role,delivered=len(new),price=50,passed=True))
            if (n+1)%128==0:print('Purchase/replay/cold verified',n+1,flush=True)
        check('all1971added packages purchased through shared transactional shop',len(rows)==1971)
        check('all32PureHoliday sets:192actual wear/cold original unit reads',len(native_units)==192)
        check('genuine role ice pools remain excluded',not {r['template']for r in json.loads((C/'analysis/client-6c6b5180/role-ice-catalog.json').read_bytes())['rewards']}-ice_equipment())
    elif mode=='eyes':
        actors={role:actor(role)for role in range(1,16)};repeat=collections.Counter();native=Replay();native_values=[]
        for product in scope['listed_heart_eyes']:
            t=product['template'];rule=custom.catalog()[t];role=rule['units'][0]
            a=actors[role]if not repeat[role]else actor(role,repeat[role]);repeat[role]+=1
            uid=a['uid'];before,new,ack=buy(t,a,'eye:'+str(t));assert len(new)==1 and new[0]['template']==t
            body=struct.pack('>QQiiIB',new[0]['uid'],rule['custom_id'],2,0,0,0)
            out=storage.use_book(DB,uid,a['account_id'],body,'use:'+str(t));assert not out['replayed']
            assert not any(i['uid']==new[0]['uid']for i in items(uid))
            saved=dump();assert storage.use_book(DB,uid,a['account_id'],body,'use:'+str(t))['replayed']and saved==dump()
            for value in custom.book_values(rule):
                raw=wire.selection_map({2:value});storage.select(DB,uid,a['account_id'],raw,'select:'+str(t)+':'+str(value['custom_id']))
                with closing(sqlite3.connect(DB))as db:state=storage.snapshot(db,uid)
                assert value in state['owned'][2]and state['selected'][2]==value
                character=Characters(DB,a['account_id']).get(uid);check_unit(native,character,items(uid))
                native_values.append(value)
            rows.append(dict(template=t,role=role,registered_ids=rule['custom_ids'],price=50,passed=True))
        check('all17HeartEyes books actual shop purchase/registration/Apply/replay/cold',len(rows)==17)
        # Execute original4CD reader/updater with every newly registered tuple.
        native=Replay();root=native.alloc(0x1600);manager=root+0xdc8;flat=native.alloc(76*64)
        native.write(manager+0x270,struct.pack('<QQQ',flat,flat,flat+76*64));native.write(native.base+0x4817e80,struct.pack('<Q',root))
        for value in native_values:
            raw=wire.registered(value).payload;p=native.alloc(len(raw));native.write(p,raw)
            buf=native.alloc(48);native.write(buf+8,struct.pack('<QQQ',p,p+len(raw),p+len(raw)))
            stream=native.alloc(40);native.call(0x3b6d140,stream);native.call(0x3b6d1c0,stream,buf,0)
            native.write(native.stack-8+0x28,struct.pack('<Q',buf));assert native.call(0xbb7f30,0,0,0,0)&255==1
            assert struct.unpack('<I',native.read(buf+32,4))[0]==len(raw)
        check('allHeartEyes registration notices accepted by originalBB7F30 including Lu/Ciel variants')
        a=actor(1,50);uid=a['uid'];t=460045;before,new,_=buy(t,a,'boundary-eye');item=new[0]
        body=struct.pack('>QQiiIB',item['uid'],12006,2,0,0,0)
        saved=dump()
        with patch.object(storage,'encode_event',side_effect=RuntimeError('own injected encoder failure')):
            try:storage.use_book(DB,uid,a['account_id'],body,'encode-failure')
            except RuntimeError:pass
            else:raise AssertionError('encoder failure not raised')
        check('registration encoding failure atomically preserves book and ownership',saved==dump())
        sql("CREATE TRIGGER fail_custom_registration BEFORE INSERT ON character_custom_permanent BEGIN SELECT RAISE(ABORT,'own injected failure');END")
        saved=dump()
        try:storage.use_book(DB,uid,a['account_id'],body,'sql-failure')
        except sqlite3.IntegrityError:pass
        else:raise AssertionError('SQL failure not raised')
        check('registration SQL failure atomically preserves book and ownership',saved==dump())
        sql('DROP TRIGGER fail_custom_registration')
        deny(lambda:storage.use_book(DB,uid,a['account_id'],struct.pack('>QQiiIB',item['uid'],22006,2,0,0,0),'wrong-source'))
        deny(lambda:purchase(DB,req(460046),'wrong-role-eye',uid))
        check('foreign book/custom source rejected without increments')
    elif mode=='local_smoke':
        offered=catalog();check('LOCAL catalog contains32PureHoliday/17HeartEyes and962onepieces',
            sum('纯粹假日'in p['name']for p in offered)==32 and sum('爱心瞳'in p['name']for p in offered)==17 and sum(p['category']==17 for p in offered)==962)
        a=actor(1);before,new,_ack=buy(303576,a,'local-pure')
        check('LOCAL actual permanent six-piece purchase',len(new)==6)
        _before,new,_ack=buy(460045,a,'local-eye');rule=custom.catalog()[460045]
        body=struct.pack('>QQiiIB',new[0]['uid'],rule['custom_id'],2,0,0,0)
        storage.use_book(DB,a['uid'],a['account_id'],body,'local-use')
        value=custom.book_values(rule)[0];storage.select(DB,a['uid'],a['account_id'],wire.selection_map({2:value}),'local-select')
        with closing(sqlite3.connect(DB))as db:state=storage.snapshot(db,a['uid'])
        check('LOCAL eye registration/Apply/cold state',state['selected'][2]==value)
        deny(lambda:purchase(DB,req(460046),'local-wrong-role',a['uid']))
        check('LOCAL wrong-role eye purchase rejected')
        native=Replay();check_unit(native,Characters(DB,a['account_id']).get(a['uid']),items(a['uid']))
        check('LOCAL actual cold unit accepted by original native reader')
    elif mode=='extras':
        a=actor(1)
        for p in json.loads((W/'extra-accessories.json').read_bytes()):
            before,new,_ack=buy(p['template'],a,'extra:'+str(p['template']))
            assert len(new)==1 and new[0]['template']==p['template']
            discard(DB,a['uid'],struct.pack('>Qi',new[0]['uid'],1),'discard-extra:'+str(p['template']))
            assert items(a['uid'])==before
            rows.append(dict(template=p['template'],price=50,passed=True))
        check('all5restored ordinary accessories purchase/replay/cold',len(rows)==5)
    elif mode=='boundaries':
        a=actor(1);uid=a['uid'];t=303576
        deny(lambda:purchase(DB,req(303578),'wrong-role-package',uid))
        saved=dump()
        with patch('els_server.storage.shop_state.ed_purchase_ack',side_effect=RuntimeError('own injected encoder failure')):
            try:purchase(DB,req(t),'encode-failure',uid)
            except RuntimeError:pass
            else:raise AssertionError('encoder failure not raised')
        check('purchase encoding failure rolls back ED/all members/receipt',dump()==saved)
        sql("CREATE TRIGGER fail_bundle_item BEFORE INSERT ON inventory_items WHEN NEW.template=303345 BEGIN SELECT RAISE(ABORT,'own injected member failure');END")
        saved=dump()
        try:purchase(DB,req(t),'sql-failure',uid)
        except sqlite3.IntegrityError:pass
        else:raise AssertionError('SQL failure not raised')
        check('middle-member failure rolls back whole bundle and payment',dump()==saved)
        sql('DROP TRIGGER fail_bundle_item');sql('UPDATE reward_balances SET ed=49 WHERE uid=?',(uid,))
        deny(lambda:purchase(DB,req(t),'insufficient',uid));check('insufficient ED no increments')
        sql('UPDATE reward_balances SET ed=200000 WHERE uid=?',(uid,))
        _before,new,_ack=buy(t,a,'once');saved=dump()
        deny(lambda:purchase(DB,struct.pack('>IIH',1,1200000000+t,2),'once',uid));check('conflicting replay denied')
        # Exhaust the actual character allowance, then reject the next bundle.
        from els_server.storage.bag_capacity import allowances
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        group=TEMPLATE_BAG_GROUPS[303342]
        with closing(sqlite3.connect(DB))as db:limit=allowances(db,uid)[group]
        while sum(i['group']==group for i in items(uid))<limit:
            with closing(sqlite3.connect(DB))as db,db:grant_items(db,[dict(template=303342,metadata=VERIFIED_TEMPLATES[303342],group=group,quantity=1)],uid)
        deny(lambda:purchase(DB,req(t),'full-bag',uid));check('full bag whole purchase rejected without ED or receipt')
    else:raise ValueError(mode)
except BaseException as error:
    report=dict(ok=False,mode=mode,checks=checks,rows=rows,error=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc()),fixture=str(DB))
    (W/('business-'+mode+'-failure.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(report['error'],ensure_ascii=False));raise
else:
    report=dict(ok=True,mode=mode,checks=checks,rows=rows,live_process=False,formal_database_written=False,natural_GUI=False,image_sha256=IMAGE_SHA)
    (W/('business-'+mode+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    folder.cleanup();print(json.dumps(dict(ok=True,mode=mode,cases=len(rows),checks=checks),ensure_ascii=False))
