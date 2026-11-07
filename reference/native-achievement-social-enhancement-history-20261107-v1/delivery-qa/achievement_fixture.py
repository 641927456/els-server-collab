"""Own retained couple/requests/enhancements, using existing producer schemas."""
from contextlib import closing
import sqlite3,struct,time
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage.inventory_actions import _commit
from els_server.storage.equipment_enhancement import replace as enhancement
from els_server.storage.enhancement_progress import replace as gauge
from els_server.storage import relationships,achievements as state,achievement_history as history,profession_state
from els_server.protocol import relationship_messages as rel
from els_server.protocol.profession_messages import ProfessionState
from els_server.domain.blacksmith_enhancement_rules import materials
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data
import json


def retained_couple(db,a,b,stamp):
    au,aa,an=a['uid'],a['account_id'],a['character_name'];bu,ba,bn=b['uid'],b['account_id'],b['character_name']
    guard=lambda db:None
    grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=1)],au)
    relationships.propose(db,au,aa,bu,ba,'owned-a','owned-b',rel.descriptor(bn),
        'own-couple-propose:'+str(au),guard=guard,
        encode=lambda left,right,replay,changes:[rel.proposed(right['name'])],now=stamp)
    body=(struct.pack('>bQ',0,au)+rel.wstring(an)+struct.pack('>QBH',0,0,0)+struct.pack('>Q',bu)+rel.wstring(bn)+bytes(1)+rel.descriptor(bn))
    relationships.answer(db,bu,ba,au,aa,'owned-b','owned-a',body,'own-couple-accept:'+str(au),
        guard=guard,encode=lambda left,right,replay,changes:[rel.answered(left,stamp,changes,target_name=right['name'])],now=stamp)


def seed(path,values):
    assert len(values)==3 and len({v['account_id']for v in values})==3
    first=values[0];first['alt_name']=first['character_name']+'Alt'
    first['alt_uid']=Characters(path,first['account_id']).create(first['alt_name'],4,'owned-social-enhancement-alternative')['uid']
    all_actors=[*values,dict(uid=first['alt_uid'])]
    for value in all_actors:LocalState(path,value['uid']).save(20001,0,0,catalog()['towns']['20001']['xyz'])
    now=int(time.time());prefix='owned-social-enhancement:'+str(first['uid'])+':'
    with closing(sqlite3.connect(path))as db,db:
        db.execute('BEGIN IMMEDIATE')
        for value in all_actors:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(value['uid'],))
            db.execute('UPDATE reward_balances SET ed=100000000,experience=?WHERE uid=?',(client_data().thresholds[98],value['uid']))
        retained_couple(db,values[0],values[1],now-100*86400-1)
        profession_state.replace(db,first['alt_uid'],first['account_id'],0,ProfessionState(2,1,0,{},0,400))
        def grant(owner,template,quantity=1):return grant_items(db,[dict(template=template,
            metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)],owner)[0]
        gear=grant(first['uid'],60100);smith=grant(first['alt_uid'],60100)
        enhancement(db,first['uid'],gear['uid'],0,9);gauge(db,first['uid'],dict(gear,enhancement=9),180,0)
        enhancement(db,first['alt_uid'],smith['uid'],0,7)
        grant(first['alt_uid'],163284);template,matrix=materials();grant(first['alt_uid'],template,matrix[8][1])
        first.update(gear_uid=gear['uid'],smith_gear_uid=smith['uid'])
        _commit(db,prefix+'schema','fixture',first['uid'],0x555,[],[],[])
        snapshot=json.dumps([dict(gear,enhancement=9)])
        for n in range(99):
            db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?,?,?)',(prefix+'enhance:'+str(n),
                'retained-fixture',first['uid'],0x5ff,'[]',snapshot,snapshot))
        state.ensure(db)
        for n in range(9):state._save(db,first['account_id'],first['uid'],'duel-invite','0'*64,prefix+'invite:'+str(n),dict(target=values[1]['uid'],created_at=now-100+n))


def snapshot(path,values):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');result=[];now=int(time.time())
        for value in values:
            owner,account=value['uid'],value['account_id'];counts=history.counts(db,account,{29,30})
            row=dict(achievement=state.snapshot(db,account,owner),requests=counts.get((29,0),0),
                attempts=counts.get((30,0),0),duration=history.couple_duration(db,account,now)[0])
            if 'alt_uid'in value:row['alt_achievement']=state.snapshot(db,account,value['alt_uid'])
            result.append(row)
        return result
