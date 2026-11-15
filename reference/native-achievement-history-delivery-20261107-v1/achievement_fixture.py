"""Only the three exactly enrolled test identities receive these explicit inputs."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,struct,time


def seed(path,actors):
    from els_server.domain.owned_growth_items import install as install_owned_growth
    install_owned_growth()
    from els_server.storage.characters import Characters
    from els_server.storage.local_state import LocalState
    from els_server.storage import resonance_state,game_mail
    from els_server.storage.inventory_state import grant_items
    from els_server.domain.resonance_allocation_flow import definitions
    from els_server.domain.town_travel import catalog
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    from els_server.game_data import client_data
    assert len(actors)==3 and len({a['account_id']for a in actors})==3
    for a in actors:
        uid,account=a['uid'],a['account_id']
        LocalState(path,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
            db.execute('UPDATE reward_balances SET ed=?,experience=?WHERE uid=?',(6000000,client_data().thresholds[98],uid))
            if a is not actors[0]:continue
            resonance_state.ensure(db)
            db.execute('INSERT INTO account_resonance VALUES(?,1,?,1)',(account,definitions()[0].threshold(150)))
            from els_server.domain import guild_rules,mentor_quests as mentor_rules
            from els_server.domain.raid_reward_items import _issue_source
            plant=guild_rules.plants()[min(guild_rules.plants())]
            grants=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)
                for t,n in((110845,1),(710106,100),(163564,5),(plant['SEED_ITEM_ID'],1))],uid)
            stamp=int(time.time());plan=mentor_rules.reward_plan(45001,stamp)
            def guard(writer):return writer is db and writer.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            for i in range(5):
                identity=dict(policy=mentor_rules.POLICY,owner=uid,quest=45001,at=stamp,cycle=i,definition_sha256=mentor_rules.DATA_SHA)
                source=_issue_source(db,uid,'owned-history-mentor:'+str(uid)+':'+str(i),'ordinary',identity,plan,guard)
                grants+=grant_items(db,plan,uid,raid_reward_source=source)
            a['fixture']=dict(license_uid=next(i['uid']for i in grants if i['template']==110845),
                seed_uid=next(i['uid']for i in grants if i['template']==plant['SEED_ITEM_ID']),
                crop_template=plant['RESULT_ITEM_ID'],crop_quantity=plant['DEFAULT_RESULT_AMOUNT'])
    first=actors[0];name=first['character_name']+'Alt';assert len(name)<=12
    first['alt']=dict(uid=Characters(path,first['account_id']).create(name,4,'owned-history-alt:'+str(first['uid']))['uid'],
        account_id=first['account_id'],character_name=name,bridge=first['bridge'])
    LocalState(path,first['alt']['uid']).save(20001,0,0,catalog()['towns']['20001']['xyz'])
    game_mail.initialize(path)


def prime(path,actors):
    """Retained threshold/time fixtures for their newly created owned guild only."""
    from els_server.storage import guild_system_state as system
    from els_server.domain import guild_rules
    from els_server.protocol import guild_system_messages as wire
    from els_server.protocol.guild_farm_messages import changed
    from els_server.domain.guild_farm import empty
    first=actors[0];uid,account=first['uid'],first['account_id'];stamp=int(time.time())
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True))as db,db:
        db.execute('BEGIN IMMEDIATE')
        assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
        guild=db.execute('SELECT g.id FROM native_guilds g JOIN native_guild_members m ON m.guild_id=g.id WHERE m.owner=?AND g.master_uid=?',(uid,uid)).fetchone()[0]
        assert set(r[0]for r in db.execute('SELECT owner FROM native_guild_members WHERE guild_id=?',(guild,)))<={a['uid']for a in actors}
        saved=system.read(db,guild);plot=saved['plots'][str(uid)]['1'];plant=guild_rules.plants()[plot['plant']]
        assert plant['SEED_ITEM_ID']==next(i['SEED_ITEM_ID']for i in guild_rules.plants().values()if i['RESULT_ITEM_ID']==first['fixture']['crop_template'])
        plot.update(planted=stamp-plant['TIME']-1,matures=stamp-1);system.write(db,guild,saved)
        for kind,amount,ack in((0x27d,99,0x27e),(0x803,9,0x804)):
            for i in range(amount):
                key='owned-history-retained:'+str(uid)+':'+str(kind)+':'+str(i)
                event=wire.reply(ack,struct.pack('>iB',0,9))if kind==0x27d else changed(ack,uid,1,empty())
                system.record(db,key,hashlib.sha256(key.encode()).hexdigest(),guild,uid,kind,
                    dict(events=[(event.kind,event.payload.hex())]),stamp-(i//10+1)*86400-i%10)
        earned=dict(guild_rules.calls('SetGuildHonorPoint'))[2];assert 0<earned<5000
        # Planting creates the actual producer table. Explicit retained facts
        # span two old weeks and each remains within the normal weekly cap.
        for i,quantity in enumerate((5000,5000-earned),1):
            at=stamp-(3-i)*7*86400;key='owned-history-honor:'+str(uid)+':'+str(i)
            raw=json.dumps(dict(guild=guild,activities=[(100,quantity,0)],at=at),sort_keys=True,separators=(',',':'))
            db.execute('INSERT INTO native_guild_quest_facts_v2 VALUES(?,?,?,?)',(key,uid,guild_rules.week(at),raw))
    return dict(ok=True,retained_posts=99,retained_harvests=9,retained_honor=10000-earned,maturity_fixture=True)


def snapshot(path,actors):
    from els_server.storage import achievements
    from els_server.storage.inventory_state import load_items
    from els_server.storage.npc_trade import balances
    result=[]
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True))as db:
        db.execute('BEGIN')
        for a in[*actors,actors[0]['alt']]:
            uid,account=a['uid'],a['account_id']
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()==(account,)
            guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uid,)).fetchone()if db.execute("SELECT 1 FROM sqlite_master WHERE name='native_guild_members'").fetchone()else None
            operations=db.execute('SELECT COUNT(*)FROM native_achievement_operations WHERE account_id=?',(account,)).fetchone()[0]if achievements.exists(db)else 0
            result.append(dict(uid=uid,achievement=achievements.snapshot(db,account,uid),items=load_items(db,uid),money=balances(db,uid),guild=None if guild is None else guild[0],operations=operations))
    return result
