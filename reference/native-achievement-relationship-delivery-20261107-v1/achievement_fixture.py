"""Finite owned rings and one alternative role; no fabricated relationship history."""
from contextlib import closing
import sqlite3
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.local_state import LocalState
from els_server.storage import achievements as state,achievement_history as history
from els_server.domain.town_travel import catalog


def seed(path,values):
    assert len(values)==3 and len({v['account_id']for v in values})==3
    for value in values:
        LocalState(path,value['uid']).save(20001,0,0,catalog()['towns']['20001']['xyz'])
    first=values[0]
    first['alt_name']=first['character_name']+'Alt'
    first['alt_uid']=Characters(path,first['account_id']).create(first['alt_name'],4,'owned-relationship-alternative')['uid']
    LocalState(path,first['alt_uid']).save(20001,0,0,catalog()['towns']['20001']['xyz'])
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        for value in values:
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(value['uid'],)).fetchone()==(value['account_id'],)
            assert not history.counts(db,value['account_id'],{18}).get((18,0),0)
        grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=2),
            dict(template=277142,metadata=0,group=4,quantity=1)],first['uid'])


def snapshot(path,values):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');result=[]
        exists=lambda name:db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(name,)).fetchone()
        booking=db.execute('SELECT id FROM native_wedding_bookings WHERE owner=?ORDER BY id DESC LIMIT 1',
            (values[0]['uid'],)).fetchone()if exists('native_wedding_bookings')else None
        reservation=booking[0]if booking else None
        for value in values:
            uid=value['uid'];counts=history.counts(db,value['account_id'],{18,19})
            mails=[r[0]for r in db.execute('SELECT mail_id FROM native_relationship_mail WHERE reservation=?AND recipient_uid=?ORDER BY mail_id',
                (reservation,uid))]if reservation is not None and exists('native_relationship_mail')else[]
            row=dict(items=load_items(db,uid),achievement=state.snapshot(db,value['account_id'],uid),
                couples=counts.get((18,0),0),ceremonies=counts.get((19,0),0),reservation=reservation,mail_ids=mails)
            if 'alt_uid'in value:row['alt_achievement']=state.snapshot(db,value['account_id'],value['alt_uid'])
            result.append(row)
        return result
