"""Prepare two explicitly owned attendance accounts before the game starts."""
from contextlib import closing
from pathlib import Path
import sqlite3,time

TOWN=20000

def enroll(row,index,path,operation):
    from els_server.storage.characters import Characters
    from els_server.storage.local_state import LocalState
    from els_server.storage.reward_state import RewardState
    from els_server.storage.inventory_state import grant_items
    from els_server.storage import ariel_attendance as store
    from els_server.domain.ariel_attendance_rules import grant_plan
    from els_server.domain.reward_rules import item_plan
    from els_server.game_data import client_data
    from els_server.storage import life_stamina
    from els_server.storage.equipment_durability import ensure_durability
    name='A197'+format(row['account_id'],'x')
    uid=Characters(path,row['account_id']).create(name,1,operation+':'+str(index))['uid']
    RewardState(path,uid,account_id=row['account_id']);LocalState(path,uid).save(TOWN,0,0,(1.,2.,3.))
    row.update(uid=uid,unit=1,town=TOWN,character_name=name)
    with closing(sqlite3.connect(path,timeout=60))as db,db:
        db.execute('BEGIN IMMEDIATE')
        assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
        db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
        db.execute('UPDATE reward_balances SET ed=?,experience=? WHERE uid=?',(5000000 if index==0 else 500,client_data().thresholds[98],uid))
        from els_server.domain.dungeon_routes import route_catalog
        db.execute('INSERT OR IGNORE INTO dungeon_records VALUES(?,?,?)',(uid,route_catalog().entry_identity(30090),60))
        ensure_durability(db)
        import uuid
        db.execute('CREATE TABLE IF NOT EXISTS account_life_stamina (account INTEGER PRIMARY KEY CHECK(account>0),current INTEGER NOT NULL CHECK(current BETWEEN 0 AND 4800),maximum INTEGER NOT NULL CHECK(maximum=4800),reset_day INTEGER NOT NULL,last_connection TEXT NOT NULL)')
        db.execute('INSERT INTO account_life_stamina VALUES(?,?,?,?,?)',(row['account_id'],4800,4800,life_stamina.day(time.time()),str(uuid.uuid4())))
        template=321149 if index==0 else 135995
        rod=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
        db.execute('UPDATE inventory_sequence SET next_uid=next_uid+1 WHERE id=1')
        db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(rod,uid,template,1,1,22,0))
        db.execute('INSERT INTO equipment_durability VALUES(?,10000)',(rod,))
        bait=grant_items(db,[item_plan(99809,10)],uid)[0]
        db.execute('UPDATE inventory_items SET bag_group=23,slot=0 WHERE uid=?',(bait['uid'],))
        row.update(rod=rod,bait=bait['uid'])
        if index==0:
            grant_items(db,[item_plan(135937,10),item_plan(99809,10)],uid)
        if index==1:
            now=int(time.time());start=now-2*86400
            store.initialize(db)
            db.execute('INSERT INTO ariel_attendance_periods VALUES (?,?,?,?,?,?,1)',(operation+':'+str(row['account_id']),row['account_id'],start,start+store.DURATION,0,None))
            item=grant_items(db,[grant_plan(721051,1,now)],uid)[0];row['coupon']=item['uid']
            vip=grant_items(db,[item_plan(721056,1)],uid)[0];row['vip']=vip['uid']
            db.execute('UPDATE account_life_stamina SET current=0 WHERE account=?',(row['account_id'],))
            from els_server.storage.bag_capacity import allowances
            from els_server.storage.inventory_state import load_items
            limit=allowances(db,uid)[21]
            used=sum(i['group']==21 for i in load_items(db,uid))
            from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
            for _ in range(limit-used):grant_items(db,[item_plan(135937,min(999,TEMPLATE_MAX_STACKS[135937]))],uid)

def cold(rows,path,*,retired=False):
    from els_server.storage import ariel_attendance as store
    result=[]
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=60))as db:
        db.execute('PRAGMA query_only=ON')
        for i,row in enumerate(rows):
            uid=row['uid'];assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(row['account_id'],)
            state=store.snapshot(path,row['account_id'])
            assert state['active']and state['attended']==(1 if i==0 else 2)and state['claimed']==[1]+[0]*14
            if i==0:
                import json
                from els_server.domain.equipment_repair import template_quote
                receipts=db.execute('SELECT evidence_json FROM equipment_repair_receipts WHERE owner=?',(uid,)).fetchall()
                assert len(receipts)==1
                cost=json.loads(receipts[0][0])['ed_cost']
                assert cost==template_quote(321149,9960)['subtotal_ed']
                expected_ed=5000000-50-cost
                attempts=db.execute('SELECT caught,fish,life_after FROM fishing_attempts WHERE owner=?',(uid,)).fetchall()
                assert len(attempts)==1 and attempts[0][2]==4780
                assert db.execute('SELECT current FROM equipment_durability WHERE item_uid=?',(row['rod'],)).fetchone()==(10000,)
                assert db.execute('SELECT count FROM inventory_items WHERE uid=?',(row['bait'],)).fetchone()==(9,)
                from els_server.domain.fish_exchange_rules import recipe
                from els_server.protocol.fish_exchange_messages import request
                import struct
                exchange=struct.pack('>iQiiiiiBi',40256,0,135937,10,135949,3,1,1,0)
                expected_award=recipe(request(exchange))[0]['quantity']
                assert db.execute('SELECT sum(count) FROM inventory_items WHERE owner=? AND template=135949',(uid,)).fetchone()==(expected_award,)
                assert db.execute('SELECT count(*) FROM completed_quests WHERE owner=? AND quest=25600',(uid,)).fetchone()==(1,)
                assert db.execute('SELECT count(*) FROM character_quests WHERE owner=? AND quest=25601',(uid,)).fetchone()==(1,)
                assert db.execute('SELECT count(*) FROM account_fishing_followup_bindings WHERE account=?',(row['account_id'],)).fetchone()[0]>=1
            else:
                expected_ed=500
                assert db.execute('SELECT current FROM equipment_durability WHERE item_uid=?',(row['rod'],)).fetchone()==(10000,)
                assert db.execute('SELECT count FROM inventory_items WHERE uid=?',(row['vip'],)).fetchone()==(1,)
                assert db.execute('SELECT current FROM account_life_stamina WHERE account=?',(row['account_id'],)).fetchone()==(0,)
                assert db.execute('SELECT count(*) FROM fishing_attempts WHERE owner=?',(uid,)).fetchone()==(0,)
            assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(expected_ed,)
            assert db.execute('SELECT sum(count) FROM inventory_items WHERE owner=? AND template=721053',(uid,)).fetchone()==(200,)
            assert db.execute('SELECT count(*) FROM ariel_attendance_claims WHERE owner=?',(uid,)).fetchone()==(1,)
            if i==1:assert db.execute('SELECT count(*) FROM inventory_items WHERE uid=?',(row['coupon'],)).fetchone()==(0,)
            result.append(dict(attended=state['attended'],claims=1,reward_count=200,ed=expected_ed,coupon_consumed=i==1))
    return dict(ok=True,read_only=True,retired=retired,roles=result)
