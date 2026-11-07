"""One writer transfers both owners' exact instances, money and receipts."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,time
from els_server.domain.bank_rules import player_ed_limit
from els_server.domain.enhancement_progress import transferred
from els_server.storage.inventory_state import load_items
from els_server.storage.inventory_actions import _commit
from els_server.storage.item_instances import remove
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.npc_trade import balances,charge
from els_server.storage.trade_board_state import _normal_sale_item,_new_uid,_place,commission

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))

def source(db,owner,account,now):
    require_owner(db,owner,account);require_active_character(db,owner)
    level=db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]
    limit=player_ed_limit(level)
    # CN board-revamp FAQ:99 personal trade100亿, earlier levels retain7亿.
    # The existing per-level wallet cap is a distinct server limit.
    return dict(owner=owner,account=account,limit=limit,trade_limit=min(limit,10_000_000_000 if level==99 else 700_000_000),money=balances(db,owner),items=load_items(db,owner))

def offered(db,saved,uid,count,now):
    item=next((i for i in saved['items']if i['uid']==uid),None)
    # Same current tradeability, seal, wardrobe, lock, expiry and durability
    # rules as the already qualified player market. Personal trade receives
    # an already sealed instance; it never silently buys or consumes a stamp.
    return _normal_sale_item(db,saved['owner'],item,count,0,saved['items'],now)[0]

def projection(db,ledger):
    result={}
    for row in ledger:
        uid=row['owner'];require_owner(db,uid,row['account'])
        current={(i['group'],i['slot']):i for i in load_items(db,uid)}
        result[uid]=dict(ed=balances(db,uid)['ed'],changes=[(tuple(p),current.get(tuple(p)))for p in row['positions']])
    return result

def perform(path,agreement,operation,guard,encode):
    if type(operation)is not str or not 1<=len(operation)<=130:raise ValueError('Personal trade operation')
    people=agreement['participants']
    if len(people)!=2 or len({p['owner']for p in people})!=2 or len({p['account']for p in people})!=2:
        raise ValueError('Two different current character accounts required')
    digest=hashlib.sha256(canonical(agreement).encode()).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=15))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=int(time.time())
        guard(db,now)
        saved={p['owner']:source(db,p['owner'],p['account'],now)for p in people}
        db.execute('''CREATE TABLE IF NOT EXISTS native_player_trades(
            operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL,agreement_json TEXT NOT NULL,
            ledger_json TEXT NOT NULL,created_at INTEGER NOT NULL)''')
        old=db.execute('SELECT request_hash,agreement_json,ledger_json FROM native_player_trades WHERE operation=?',(operation,)).fetchone()
        if old is not None:
            if old[:2]!=(digest,canonical(agreement)):raise ValueError('Conflicting personal trade replay')
            result=projection(db,json.loads(old[2]));answer=encode(db,result,True);guard(db,now)
            return answer
        outgoing={};fees={};positions={p['owner']:set()for p in people}
        for p in people:
            uid=p['owner'];s=saved[uid];amount=p['ed']
            if type(amount)is not int or not 0<=amount<=s['trade_limit']or amount>s['money']['ed']:
                raise ValueError('Owned personal trade ED amount')
            rows=p['items']
            if len(rows)>10:raise ValueError('Personal trade ten item slot bound')
            if len({r['item']['uid']for r in rows})!=len(rows):raise ValueError('Duplicate personal trade source')
            outgoing[uid]=[];fees[uid]=commission(amount)
            for row in rows:
                item=offered(db,s,row['item']['uid'],row['quantity'],now)
                if item!=row['item']:raise ValueError('Offered instance changed after registration')
                outgoing[uid].append((item,row['quantity']))
        # Remove both sets first so a full-bag item exchange can reuse the
        # just-freed slots. Every operation below remains inside this writer.
        moved={p['owner']:[]for p in people}
        for p in people:
            uid=p['owner']
            for item,count in outgoing[uid]:
                positions[uid].add((item['group'],item['slot']))
                if count==item['count']:
                    remove(db,uid,item);incoming=dict(item)
                else:
                    if db.execute('UPDATE inventory_items SET count=count-? WHERE uid=?AND owner=?AND count=?',
                                  (count,item['uid'],uid,item['count'])).rowcount!=1:
                        raise ValueError('Personal trade source quantity changed')
                    incoming=dict(item,uid=_new_uid(db),count=count)
                if incoming.get('sealed',False):incoming['sealed']=False
                moved[uid].append(transferred(incoming))
        ledger=[];after={};money={}
        for p,other in((people[0],people[1]),(people[1],people[0])):
            uid=p['owner'];peer=other['owner']
            final=saved[uid]['money']['ed']-p['ed']+other['ed']-fees[peer]
            if not 0<=final<=saved[uid]['limit']:raise ValueError('Personal trade final wallet capacity')
            remaining=charge(db,uid,saved[uid]['money'],p['ed'])
            net=other['ed']-fees[peer]
            if db.execute('UPDATE reward_balances SET ed=ed+? WHERE uid=?AND ed=?AND revision=?',
                          (net,uid,remaining,saved[uid]['money']['revision']+1)).rowcount!=1:
                raise ValueError('Personal trade wallet generation changed')
            for item in moved[peer]:
                positions[uid].update(_place(db,uid,item,item['count'],True,load_items(db,uid)))
            after[uid]=load_items(db,uid);money[uid]=balances(db,uid)
            points=sorted(positions[uid])
            _commit(db,operation+':'+str(uid),digest,uid,0x188,points,saved[uid]['items'],after[uid])
            ledger.append(dict(owner=uid,account=p['account'],gross_out=p['ed'],fee=fees[uid],
                net_in=net,before_ed=saved[uid]['money']['ed'],after_ed=final,positions=points))
        assert sum(r['before_ed']-r['after_ed']for r in ledger)==sum(fees.values())
        db.execute('INSERT INTO native_player_trades VALUES(?,?,?,?,?)',
                   (operation,digest,canonical(agreement),canonical(ledger),now))
        result=projection(db,ledger);answer=encode(db,result,False);guard(db,now)
        if any(load_items(db,uid)!=after[uid]or balances(db,uid)!=money[uid]for uid in saved):
            raise ValueError('Personal trade state changed during response preparation')
        return answer
