"""Exercise real shop/reset writers in fresh disposable stores, never player data."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import hashlib,json,sqlite3,struct,sys,tempfile,time,uuid
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
R=Path(json.loads((W/'ticket-parent.json').read_bytes())['runtime'])
data_link=W/'candidate/els_server/data'
if not data_link.exists():data_link.symlink_to(R/'els_server/data',target_is_directory=True)
sys.path[:0]=[str(R),str(R/'tools'),str(R/'tools/pylibs')]
import els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(W/'candidate/els_server/domain'))
els_server.storage.__path__.insert(0,str(W/'candidate/els_server/storage'))
from els_server.storage.local_state import ensure_local_tables
from els_server.storage.reward_state import ensure_reward_tables
from els_server.storage.inventory_state import ensure_inventory,load_items,grant_items
from els_server.storage.characters import Characters
from els_server.storage import shop_state as shop,rosso_reset as reset,raid_economy_state as raid
from els_server.domain.dungeon_ticket_shop import TEMPLATES,KEYS,RESETS,offers
from els_server.domain.acquisition_policy import can_acquire
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
checks=[]

def connect(path):return closing(sqlite3.connect(path))
def snapshot(path):
    with connect(path)as db:return list(db.iterdump())
def request(templates):return struct.pack('>I',len(templates))+b''.join(struct.pack('>IH',1200000000+t,n)for t,n in templates)
def fixture(root,label):
    path=root/(label+'.sqlite3')
    with connect(path)as db,db:
        ensure_local_tables(db);ensure_reward_tables(db);ensure_inventory(db)
    uid=Characters(path,1).create('TicketQA',1,'ticket-qa-'+label)['uid']
    with connect(path)as db,db:db.execute('UPDATE reward_balances SET ed=1000 WHERE uid=?',(uid,))
    return path,uid
def buy(path,uid,templates,op):return shop.purchase(path,request(templates),op,uid)

with tempfile.TemporaryDirectory(dir=W,prefix='own-ticket-test-')as temp:
    root=Path(temp);path,uid=fixture(root,'success')
    for role in (1,5,10,15):
        rows=[p for p in shop.catalog(role)if p['template']in TEMPLATES]
        assert len(rows)==6 and all(p['price']==50 and p['quantity']==1 and p['category']==41 for p in rows)
    checks.append('Six permanent products present for all sampled character families at 50 ED each')
    assert all(not can_acquire(t) for t in TEMPLATES)
    raw=request([(t,1)for t in sorted(TEMPLATES)])
    response=shop.purchase(path,raw,'six-products',uid)
    with connect(path)as db:
        items=load_items(db,uid)
        assert all(sum(i['count']for i in items if i['template']==t)==1 for t in TEMPLATES)
        assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(700,)
    before=snapshot(path);assert shop.purchase(path,raw,'six-products',uid)==response;assert snapshot(path)==before
    checks.append('All six real purchases: 300 ED debit, exact items, cold read and unchanged idempotent replay')
    raw=request([(KEYS[0],10)])
    shop.purchase(path,raw,'ten-keys',uid)
    with connect(path)as db:
        assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(200,)
        assert sum(i['count']for i in load_items(db,uid)if i['template']==KEYS[0])==11
    checks.append('Bulk key purchase charges 50 ED per unit')
    before=snapshot(path)
    try:buy(path,uid,[(KEYS[0],5)],'poor')
    except ValueError:pass
    else:raise AssertionError('Insufficient balance accepted')
    assert snapshot(path)==before
    with patch.object(shop,'ed_purchase_ack',side_effect=ValueError('owned encoding fault')):
        try:buy(path,uid,[(KEYS[1],1)],'encode-fault')
        except ValueError as e:assert 'owned encoding fault'in str(e)
        else:raise AssertionError('Encode fault accepted')
    assert snapshot(path)==before
    checks.append('Insufficient ED and injected response-encoding failure roll back wallet/items/source/receipt')

    # Real weekly ledger projection. Keep other mode/family/week/owner rows.
    now=int(time.time());week=raid.week_at(now)
    for template,family,category in((135909,'rosso',1),(136055,'berthe',2)):
        with connect(path)as db,db:
            db.execute('BEGIN IMMEDIATE')
            raid.ensure(db)
            for bucket,owner,wk in((family+':shared',uid,week),(family+':story',uid,week),(family+':shared',uid,week-604800),(family+':shared',uid+1,week)):
                db.execute('INSERT OR REPLACE INTO formal_raid_weeks VALUES(?,?,?,?,?,?)',(owner,bucket,1,1,wk,str(uuid.uuid4())))
            item=next(i for i in load_items(db,uid)if i['template']==template)
            other=list(db.execute('SELECT * FROM formal_raid_weeks WHERE NOT(owner=?AND bucket=?AND week=?)',(uid,family+':shared',week)))
        payload=struct.pack('>QQiiIB',item['uid'],1,0,0,0,0)
        operation='rosso-reset-v1:own-'+family
        before=snapshot(path)
        with patch.object(reset,'encode_event',side_effect=ValueError('owned reset encode fault')):
            try:reset.perform(path,uid,1,payload,operation,prepare=lambda db:True)
            except ValueError as e:assert 'owned reset encode fault'in str(e)
            else:raise AssertionError('Reset encode fault accepted')
        assert snapshot(path)==before
        events=reset.perform(path,uid,1,payload,operation,prepare=lambda db:True)
        assert len(events)==2 and events[1].kind==0x7c1 and struct.unpack_from('>i',events[1].payload)[0]==category
        with connect(path)as db,db:
            assert not db.execute('SELECT 1 FROM inventory_items WHERE owner=?AND uid=?',(uid,item['uid'])).fetchone()
            assert not db.execute('SELECT 1 FROM formal_raid_weeks WHERE owner=?AND bucket=?AND week=?',(uid,family+':shared',week)).fetchone()
            assert list(db.execute('SELECT * FROM formal_raid_weeks WHERE NOT(owner=?AND bucket=?AND week=?)',(uid,family+':shared',week)))==other
            db.execute('INSERT INTO formal_raid_weeks VALUES(?,?,?,?,?,?)',(uid,family+':shared',1,1,week,str(uuid.uuid4())))
        before=snapshot(path);reset.perform(path,uid,1,payload,operation,prepare=lambda db:True);assert snapshot(path)==before
        checks.append(f'{family}: consume one owned ticket, reset selected current week only, correct native category, encode rollback, replay preserves newly earned reward')

    buy(path,uid,[(136055,1)],'berthe-story-ticket')
    with connect(path)as db:
        item=next(i for i in load_items(db,uid)if i['template']==136055)
        normal=list(db.execute("SELECT * FROM formal_raid_weeks WHERE owner=?AND bucket='berthe:shared'",(uid,)))
    payload=struct.pack('>QQiiIB',item['uid'],2,0,0,0,0)
    reset.perform(path,uid,1,payload,'rosso-reset-v1:own-berthe-story',prepare=lambda db:True)
    with connect(path)as db:
        assert not db.execute("SELECT 1 FROM formal_raid_weeks WHERE owner=?AND bucket='berthe:story'AND week=?",(uid,week)).fetchone()
        assert list(db.execute("SELECT * FROM formal_raid_weeks WHERE owner=?AND bucket='berthe:shared'",(uid,)))==normal
    checks.append('Berthe story-mode reset preserves independently earned normal rewards')

    cap_path,cap_uid=fixture(root,'capacity')
    with connect(cap_path)as db,db:
        used={i['slot']for i in load_items(db,cap_uid)if i['group']==4}
        next_uid=db.execute('SELECT COALESCE(MAX(uid),0)+1 FROM inventory_items').fetchone()[0]
        for slot in set(range(36))-used:
            db.execute('INSERT INTO inventory_items(uid,owner,template,metadata,count,bag_group,slot)VALUES(?,?,?,?,?,?,?)',(next_uid,cap_uid,KEYS[0],2,TEMPLATE_MAX_STACKS[KEYS[0]],4,slot));next_uid+=1
    before=snapshot(cap_path)
    try:buy(cap_path,cap_uid,[(136055,1)],'full')
    except ValueError:pass
    else:raise AssertionError('Full bag accepted')
    assert snapshot(cap_path)==before
    checks.append('Full bag rolls back ticket purchase with no debit or new source ledger')
result=dict(passed=True,checks=checks,player_data_used=False,production_installed=False,natural_GUI=False)
(W/'ticket-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(result,ensure_ascii=False))
