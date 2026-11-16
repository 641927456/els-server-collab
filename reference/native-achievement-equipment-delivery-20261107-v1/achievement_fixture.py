"""Explicit threshold fixtures for three exactly enrolled QA accounts only."""
from contextlib import closing
from pathlib import Path
import json,sqlite3,struct


TYPES={32,35,36,45,51,52,53,60}


def seed(path,actors):
    from els_server.storage.characters import Characters
    from els_server.storage.local_state import LocalState
    from els_server.storage import profession_state,anvil
    from els_server.storage.inventory_state import grant_items
    from els_server.storage.inventory_actions import _commit
    from els_server.storage.equipment_enhancement import replace as enhancement
    from els_server.storage.enhancement_progress import replace as progress
    from els_server.protocol.profession_messages import ProfessionState
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    from els_server.domain.equipment_spell_rules import catalog as spells
    from els_server.domain.acquisition_policy import can_acquire
    from els_server.domain.town_travel import catalog as towns
    from els_server.game_data import client_data
    assert len(actors)==3 and len({a['account_id']for a in actors})==3
    for a,profession in zip(actors,(1,2,3)):
        uid,account=a['uid'],a['account_id']
        LocalState(path,uid).save(20001,0,0,towns()['towns']['20001']['xyz'])
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
            db.execute('UPDATE reward_balances SET ed=100000000,experience=?WHERE uid=?',(client_data().thresholds[98],uid))
            profession_state.replace(db,uid,account,0,ProfessionState(profession,1,0,{},0,400))
            def grant(t,n=1):
                return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)],uid)[0]
            _commit(db,'owned-equipment-schema:'+str(uid),'fixture',uid,0x555,[],[],[])
            def retained(key,kind,before,after):
                db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?,?,?)',
                    ('owned-equipment-retained:'+str(uid)+':'+key,'owned-retained-fixture',uid,kind,'[]',json.dumps(before),json.dumps(after)))
            if profession==1:
                gear=grant(60100);target=grant(11006011);stone=grant(135184,2);coin=grant(117527)
                template=next(int(t)for t,row in spells()['targets'].items()if row['tag64']and int(t)in VERIFIED_TEMPLATES and can_acquire(int(t)))
                weapon=grant(template);mystic=grant(136109)
                enhancement(db,uid,gear['uid'],0,9);progress(db,uid,dict(gear,enhancement=9),180,0)
                for n in range(4):retained('enhance:'+str(n),0x5ff,[dict(gear,enhancement=9)],[dict(gear,enhancement=10)])
                retained('socket',0x1c4,[dict(stone,count=998)],[])
                retained('mystic',0x6e7,[dict(mystic,count=99)],[])
                for n in range(99):retained('sphere:'+str(n),0x705,[coin],[])
                a['fixture']=dict(gear=gear['uid'],socket_target=target['uid'],stone=stone['uid'],weapon=weapon['uid'],mystic=mystic['uid'])
            elif profession==2:
                anvil.create_schema(db)
                db.executemany('INSERT INTO profession_anvil_receipts VALUES(?,?,?,?,?,?,?,?,?)',
                    [('owned-equipment-anvil:'+str(uid)+':'+str(n),'owned-retained-fixture',uid,account,100000,1,100,n+1,n+1)for n in range(9)])
            else:
                ingredients=[grant(60100)for _ in range(5)]
                for n in range(99):retained('flask:'+str(n),0x707,ingredients,[])
                a['fixture']=dict(ingredients=[i['uid']for i in ingredients])
    first=actors[0];name=first['character_name']+'Alt';assert len(name)<=12
    first['alt']=dict(uid=Characters(path,first['account_id']).create(name,4,'owned-equipment-alt:'+str(first['uid']))['uid'],
        account_id=first['account_id'],character_name=name,bridge=first['bridge'])
    LocalState(path,first['alt']['uid']).save(20001,0,0,towns()['towns']['20001']['xyz'])
    from els_server.storage.known_resurrection import _set as set_stones
    from els_server.storage.quick_slots import save_request,encode,empty
    from els_server.domain.quick_bindings import item_binding
    import uuid
    uid=first['uid']
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(first['account_id'],)
        potion=grant_items(db,[dict(template=77010,metadata=2,group=6,quantity=1)],uid)[0]
        set_stones(db,uid,1)
        db.execute('CREATE TABLE IF NOT EXISTS consumable_uses(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,item_uid INTEGER NOT NULL,template INTEGER NOT NULL,used_at REAL NOT NULL)')
        db.executemany('INSERT INTO consumable_uses VALUES(?,?,?,?,?,?)',
            [('owned-equipment-potion:'+str(uid)+':'+str(n),'owned-retained-fixture',uid,potion['uid'],77010,1000+n)for n in range(999)])
        db.execute('CREATE TABLE IF NOT EXISTS known_resurrection_spends(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,run TEXT NOT NULL,life INTEGER NOT NULL,UNIQUE(owner,run,life))')
        epoch=str(uuid.uuid4())
        db.executemany('INSERT INTO known_resurrection_spends VALUES(?,?,?,?,?)',
            [('owned-equipment-revival:'+str(uid)+':'+str(n),'owned-retained-fixture',uid,epoch,n+1)for n in range(99)])
    save_request(path,struct.pack('>i',1)+encode({**empty(),5:item_binding(77010)}),uid)


def snapshot(path,actors):
    from els_server.storage import achievements,achievement_history as history
    from els_server.storage.inventory_state import load_items
    from els_server.storage.npc_trade import balances
    rows=[]
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:
        db.execute('BEGIN')
        for a in[*actors,actors[0]['alt']]:
            uid,account=a['uid'],a['account_id']
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            operations=db.execute('SELECT COUNT(*)FROM native_achievement_operations WHERE account_id=?',(account,)).fetchone()[0]if achievements.exists(db)else 0
            rows.append(dict(uid=uid,achievement=achievements.snapshot(db,account,uid),items=load_items(db,uid),
                money=balances(db,uid),operations=operations,history={str(k):v for k,v in history.counts(db,account,TYPES).items()}))
    return rows
