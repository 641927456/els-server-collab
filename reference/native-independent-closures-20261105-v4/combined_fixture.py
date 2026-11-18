"""Finite fixtures and readbacks for exactly three separately allocated QA owners."""
from contextlib import closing
from pathlib import Path
import sqlite3,json

def seed(path,actors):
    from els_server.storage.local_state import LocalState
    from els_server.storage.seal_quests import QuestState
    from els_server.storage.inventory_state import grant_items
    from els_server.storage import housing_access,game_mail
    from els_server.domain.town_travel import catalog
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    from els_server.game_data import client_data
    import struct
    assert len(actors)==3 and len({a['account_id']for a in actors})==3 and len({a['uid']for a in actors})==3
    for index,a in enumerate(actors):
        uid=a['uid'];account=a['account_id']
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
        QuestState(path,uid,account_id=account).snapshot()
        LocalState(path,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            db.execute('UPDATE reward_balances SET ed=?,experience=? WHERE uid=?',(6_000_000,client_data().thresholds[98],uid))
            if index==0:
                grant_items(db,[dict(template=288495,metadata=0,group=4,quantity=1),
                    dict(template=81650,metadata=0,group=4,quantity=1),
                    dict(template=77000,metadata=VERIFIED_TEMPLATES[77000],group=TEMPLATE_BAG_GROUPS[77000],quantity=7),
                    dict(template=500051,metadata=VERIFIED_TEMPLATES[500051],group=TEMPLATE_BAG_GROUPS[500051],quantity=1),
                    dict(template=135974,metadata=VERIFIED_TEMPLATES[135974],group=TEMPLATE_BAG_GROUPS[135974],quantity=3)],uid)
                contract=grant_items(db,[dict(template=136034,metadata=0,group=4,quantity=1)],uid)[0]
        if index==0:
            housing_access.use(path,uid,account,struct.pack('>QQiiIB',contract['uid'],0,0,0,0,0),
                               'owned-closure-housing-contract:'+str(uid),lambda db:None)
    seed_ice_decomposition(path,actors)
    game_mail.initialize(path)

def snapshot(path,actors):
    from els_server.storage.inventory_state import load_items
    from els_server.storage.npc_trade import balances
    from els_server.storage import photo_zone_state,titles
    result=[]
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:
        db.execute('BEGIN')
        tables={r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for a in actors:
            uid=a['uid'];account=a['account_id']
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            pets=[dict(uid=r[0],name=r[1])for r in db.execute("SELECT uid,name FROM companions WHERE owner=?AND kind='pet' ORDER BY uid",(uid,))]if 'companions'in tables else[]
            pet_equipment=[dict(pet=r[0],slot=r[1],item_uid=r[2],item=json.loads(r[3]),socket=r[4])for r in db.execute('SELECT pet,slot,item_uid,item,socket FROM pet_accessories WHERE owner=? ORDER BY pet,slot',(uid,))]if 'pet_accessories'in tables else[]
            result.append(dict(uid=uid,pets=pets,pet_equipment=pet_equipment,items=load_items(db,uid),money=balances(db,uid),
                location=db.execute('SELECT town,board,progress,x,y,z FROM location WHERE uid=?',(uid,)).fetchone(),
                unlocked=sorted(photo_zone_state.snapshot(db,uid,account)),titles=titles.snapshot(db,uid)['owned'],
                mails=[dict(id=r[0],ed=r[1],claimed_at=r[2])for r in db.execute(
                    'SELECT id,ed,claimed_at FROM game_mail WHERE account_id=? ORDER BY id',(account,))]))
    return result


def seed_ice_decomposition(path, actors):
    from els_server.domain.inventory_items import role_ice_catalog
    from els_server.domain.decomposition_rules import quote
    from els_server.storage.inventory_state import grant_items, load_items
    assert len(actors) == 3
    assert len({a['uid'] for a in actors}) == len({a['account_id'] for a in actors}) == 3
    actor = actors[0]
    catalog = role_ice_catalog()
    # Pinned original machine800000, role1 output; the existing modern
    # box800006 mapping independently identifies the same Elsword weapon.
    assert 800018 in catalog['pools']['800000']['1']
    definition, = (r for r in catalog['rewards'] if r['template'] == 800018)
    assert (definition['metadata'], definition['group'], definition['max_stack']) == (0, 27, 1)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',
                          (actor['uid'],)).fetchone() == (actor['account_id'],)
        assert db.execute('SELECT unit_type FROM characters WHERE uid=?',
                          (actor['uid'],)).fetchone() == (1,)
        assert not any(i['template'] == 800018 for i in load_items(db, actor['uid']))
        item, = grant_items(db, [dict(template=800018, metadata=0, group=27, quantity=1)], actor['uid'])
        quoted = quote(item)
        assert (quoted['template'], quoted['quantity']) == (130047, 45)
    return dict(uid=item['uid'], template=800018, owner=actor['uid'], role=1)
