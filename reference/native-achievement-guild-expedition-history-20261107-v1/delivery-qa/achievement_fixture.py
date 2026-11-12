"""Explicit owned retained guild history; the next signup uses ordinary TLS."""
from contextlib import closing
import sqlite3,struct,time
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import achievements as state,achievement_history as history
from els_server.storage import guild_membership_state as members,guild_system_state as system
from els_server.domain import guild_expedition as expedition,guild_rules as rules
from els_server.domain.guild_initial_profile import profile
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data
from els_server.protocol import guild_membership_profile as wire
from els_server.protocol.local_messages import wstring


def retained_signup(actor,stage,stamp):
    exp=expedition._new(stamp);exp['stage']=stage
    for number in range(1,stage):expedition._stage(exp,number,stamp).update(hp=0,cleared=stamp-1)
    st=expedition._stage(exp,stage,stamp)
    st['participants'][str(actor['uid'])]=dict(uid=actor['uid'],account=actor['account_id'],joined=stamp,
        until=stamp+rules.expedition_rules()['LimitExpeditionSec'],combat=1000,class_id=actor['unit_class'],
        name=actor['name'],damage=0,claimed=False,rank=0,rewards={},source='owned-fixture')
    exp['charge_starts'][str(actor['uid'])]=stamp
    return expedition.snapshot(dict(id=77,owner=actor['uid'],system=dict(expedition=exp)),stamp,0xabd)


def seed(path,values):
    assert len(values)==3 and len({v['account_id']for v in values})==3
    first,second,other=values;first['alt_name']=first['character_name']+'Alt'
    first['alt_uid']=Characters(path,first['account_id']).create(first['alt_name'],4,'owned-expedition-alternative')['uid']
    for value in[*values,dict(uid=first['alt_uid'])]:LocalState(path,value['uid']).save(20001,0,0,catalog()['towns']['20001']['xyz'])
    actor=Characters(path,first['account_id']).get(first['uid']);now=int(time.time());joined=now-86401
    with closing(sqlite3.connect(path))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        for value in[*values,dict(uid=first['alt_uid'])]:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(value['uid'],))
            db.execute('UPDATE reward_balances SET ed=6000000,experience=?WHERE uid=?',(client_data().thresholds[98],value['uid']))
        license=grant_items(db,[dict(template=110845,metadata=VERIFIED_TEMPLATES[110845],group=TEMPLATE_BAG_GROUPS[110845],quantity=1)],first['uid'])[0]
        name='Exp'+str(first['uid']);message='Owned retained history';guard=lambda:None
        def create_encoder(saved,changes,repeat):
            p=profile(saved,db=db,now=joined);return wire.create_ack(p['basic'],changes),wire.full_notification(p)
        members.create(db,first['uid'],first['account_id'],license['uid'],name,message,
            struct.pack('>Q',license['uid'])+wstring(name)+wstring(message),'owned-expedition-create',joined,encode=create_encoder,guard=guard)
        guild=members.snapshot(db,first['uid'],first['account_id'])['id'];first['guild']=guild
        members.invite(db,first['uid'],first['account_id'],second['uid'],second['account_id'],
            'owned-source','owned-target',wstring(second['character_name'])+struct.pack('>Q',second['uid']),
            'owned-expedition-invite',joined,encode=lambda saved,inviter,target:(wire.invite_ack(second['character_name']),),guard=guard)
        def accept_encoder(saved,changes,repeat):return wire.accepted_ack(),wire.full_notification(profile(saved,db=db,now=joined),joined=True)
        members.accept(db,second['uid'],second['account_id'],guild,first['character_name'],'owned-target',
            struct.pack('>i',guild)+wstring(first['character_name'])+bytes(4),'owned-expedition-accept',joined,
            encode=accept_encoder,guard=guard,inviter_account_id=first['account_id'],inviter_session='owned-source')
        saved=system.read(db,guild);exp=expedition._new(now);exp['stage']=12
        for number in range(1,12):expedition._stage(exp,number,now).update(hp=0,cleared=now-1)
        expedition._stage(exp,12,now);saved['expedition']=exp;system.write(db,guild,saved)
        for turn in range(99):
            stamp=now-(100-turn)*86400;event=retained_signup(actor,7,stamp)
            system.record(db,'owned-history:'+str(turn),'owned-fixture',guild,first['uid'],0xabc,
                dict(events=[(event.kind,event.payload.hex())]),stamp)


def snapshot(path,values):
    with closing(sqlite3.connect(path))as db:
        db.execute('BEGIN');result=[];guild=values[0]['guild'];exp=system.read(db,guild)['expedition']
        for value in values:
            owner,account=value['uid'],value['account_id'];counts=history.counts(db,account,{57,58})
            player=exp['stages']['12']['participants'].get(str(owner))
            row=dict(achievement=state.snapshot(db,account,owner),level=counts.get((57,0),0),
                participations=counts.get((58,0),0),stage_cleared=bool(exp['stages']['12']['cleared']),
                participating=player is not None,frozen_CP=None if player is None else player['combat'])
            if 'alt_uid'in value:row['alt_achievement']=state.snapshot(db,account,value['alt_uid'])
            result.append(row)
        return result
