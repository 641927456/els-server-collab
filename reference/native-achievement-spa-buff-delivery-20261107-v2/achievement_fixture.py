"""Explicit retained99-spa-grant history for three owned QA accounts."""
from contextlib import closing
import sqlite3,struct,time
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import environment_buffs as buffs,achievement_history as history,achievements as state,relationships,weddings
from els_server.storage.inventory_state import grant_items
from els_server.protocol import relationship_messages as rel
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data


def seed(path,values):
    assert len(values)==3 and len({v['account_id']for v in values})==3
    first=values[0];first['alt_name']=first['character_name']+'Alt'
    first['alt_uid']=Characters(path,first['account_id']).create(first['alt_name'],4,'owned-spa-alternative:'+str(first['uid']))['uid']
    actors=[*values,dict(uid=first['alt_uid'],town=1500)]
    for i,value in enumerate(values):value['town']=1500 if i<2 else 20001
    for value in actors:
        town=value['town'];xyz=(0.,0.,0.)if town==1500 else catalog()['towns'][str(town)]['xyz']
        LocalState(path,value['uid']).save(town,0,0,xyz)
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        for value in actors:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(value['uid'],))
            db.execute('UPDATE reward_balances SET ed=6000000,experience=?WHERE uid=?',(client_data().thresholds[98],value['uid']))
        db.execute('UPDATE reward_balances SET ed=0 WHERE uid=?',(values[1]['uid'],))
        for n in range(99):buffs.put(db,first['uid'],'spa','owned-spa-retained:'+str(first['uid'])+':'+str(n),1700000000+n)
        a,b=values[:2];stamp=int(time.time());guard=lambda db:None
        grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=1),dict(template=277142,metadata=0,group=4,quantity=1)],a['uid'])
        relationships.propose(db,a['uid'],a['account_id'],b['uid'],b['account_id'],'owned-a','owned-b',rel.descriptor(b['character_name']),
            'owned-spa-propose:'+str(a['uid']),guard=guard,encode=lambda *args:[],now=stamp)
        body=(struct.pack('>bQ',0,a['uid'])+rel.wstring(a['character_name'])+struct.pack('>QBH',0,0,0)+struct.pack('>Q',b['uid'])+rel.wstring(b['character_name'])+bytes(1)+rel.descriptor(b['character_name']))
        relationships.answer(db,b['uid'],b['account_id'],a['uid'],a['account_id'],'owned-b','owned-a',body,
            'owned-spa-answer:'+str(a['uid']),guard=guard,encode=lambda *args:[],now=stamp)


def snapshot(path,values):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');result=[];reservation=None;reservation_open=False
        if weddings.present(db):
            row=db.execute('SELECT id,pair_id,finished_at,canceled_at FROM native_wedding_bookings WHERE owner=?ORDER BY id DESC LIMIT 1',(values[0]['uid'],)).fetchall()
            if row:
                reservation=row[0][0]
                reservation_open=row[0][2:] == (None,None)and db.execute('SELECT COUNT(*)FROM native_couple_members_v1 WHERE pair_id=?',(row[0][1],)).fetchone()[0]==2
        for value in values:
            row=dict(count=history.counts(db,value['account_id'],{7}).get((7,964),0),
                requests=history.counts(db,value['account_id'],{29}).get((29,0),0),
                ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(value['uid'],)).fetchone()[0],
                achievement=state.snapshot(db,value['account_id'],value['uid']),reservation=reservation,reservation_open=reservation_open,
                couple_current=relationships.snapshot(db,value['uid'],value['account_id'])is not None,
                ring=[r[0]for r in db.execute('SELECT uid FROM inventory_items WHERE owner=?AND template=277142',(value['uid'],))],
                wedding_tickets=[r[0]for r in db.execute('SELECT uid FROM inventory_items WHERE owner=?AND template IN(277151,277152)',(value['uid'],))],
                wedding_mail=[]if reservation is None else[r[0]for r in db.execute('SELECT mail_id FROM native_relationship_mail WHERE reservation=?AND recipient_uid=?ORDER BY mail_id',(reservation,value['uid']))])
            if 'alt_uid'in value:row['alt_achievement']=state.snapshot(db,value['account_id'],value['alt_uid'])
            result.append(row)
        return result
