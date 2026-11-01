"""Disposable transaction checks against an explicitly selected runtime root."""
import argparse,json,pathlib,sqlite3,struct,sys,tempfile,time
from contextlib import closing
from unittest.mock import patch

p=argparse.ArgumentParser();p.add_argument('--runtime',type=pathlib.Path,required=True);p.add_argument('--mode',choices=('online','local'),required=True);p.add_argument('--only',default='enhancement,restoration,sage,resonance,failure');args=p.parse_args();selected=set(args.only.split(','))
HERE=pathlib.Path(__file__).resolve().parents[1];SOURCE=HERE/'source';BASE=args.runtime.resolve()
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE)]
import els_server,els_server.domain,els_server.storage,els_server.protocol
for package,suffix in ((els_server,'els_server'),(els_server.domain,'els_server/domain'),(els_server.storage,'els_server/storage'),(els_server.protocol,'els_server/protocol')):
    for group in ('common',args.mode):package.__path__.insert(0,str(SOURCE/group/suffix))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_instances import remove
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS,ADVANCED_TIMED_TEMPLATES
from els_server.domain.owned_scroll_families import catalog
from els_server.game_data import client_data
from els_server.storage import enhancement_scroll, equipment_restoration, wisdom_potions
from els_server.storage.equipment_enhancement import replace as set_enhancement
from els_server.storage.seal_quests import load_character
from els_server.protocol.dungeon_messages import return_user_sync
from els_server.domain.normal_equipment import definitions as normal

data=client_data();rules=catalog();checks=[]
with tempfile.TemporaryDirectory(prefix='scroll-families-',dir=HERE)as folder:
    path=pathlib.Path(folder)/'qa.sqlite3';account=LocalAccount(LocalState(path));account.enable_characters();account.enable_rewards()
    def items():
        with closing(sqlite3.connect(path))as db:return load_items(db,1001)
    def dump():
        with closing(sqlite3.connect(path))as db:return list(db.iterdump())
    def give(t,count=1,*,existing=False):
        with closing(sqlite3.connect(path))as db,db:
            if existing:
                # A retained historical item, not a new acquisition source.
                db.execute('BEGIN IMMEDIATE')
                uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
                group=TEMPLATE_BAG_GROUPS.get(t,4)
                slot=next(n for n in range(36) if all(i['group']!=group or i['slot']!=n for i in load_items(db,1001)))
                db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(uid,1001,t,VERIFIED_TEMPLATES.get(t,data.item(t)['metadata']),count,group,slot))
                db.execute('UPDATE inventory_sequence SET next_uid=next_uid+1 WHERE id=1')
                return next(i for i in load_items(db,1001) if i['uid']==uid)
            plan=dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS.get(t,4),quantity=count)
            if t in ADVANCED_TIMED_TEMPLATES:plan['expires_at']=int(time.time())+3600
            return grant_items(db,[plan],1001)[0]
    def discard(*uids):
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            for item in load_items(db,1001):
                if item['uid']in uids:remove(db,1001,item)
    for t,rule in (rules['enhancement'].items() if 'enhancement'in selected else ()):
        gear=give(60100);scroll=give(t,2 if TEMPLATE_MAX_STACKS[t]>1 else 1);payload=struct.pack('>QQ',gear['uid'],scroll['uid']);op='enhance-'+str(t)
        reply=enhancement_scroll.apply(path,1001,payload,op,account_id=1)
        assert struct.unpack_from('>i',reply[0].payload)[0]==0
        now={i['uid']:i for i in items()};assert now[gear['uid']]['enhancement']==rule['level']
        assert (now[scroll['uid']]['count']==scroll['count']-1 if scroll['count']>1 else scroll['uid']not in now)
        before=dump();enhancement_scroll.apply(path,1001,payload,op,account_id=1);assert dump()==before
        discard(gear['uid'],scroll['uid'])
    if 'enhancement'in selected:checks.append(dict(kind='enhancement',variants=len(rules['enhancement']),normal_result=True,replay=True))

    candidates=[];admitted=normal()
    with data.connect()as db:
        for t,raw,position in db.execute('SELECT id,record,equip_position FROM items WHERE item_type IN(1,2)'):
            if t in admitted and t in VERIFIED_TEMPLATES and TEMPLATE_BAG_GROUPS[t]==1:
                candidates.append((t,raw[0xd1],position))
    for t,rule in (rules['restoration'].items() if 'restoration'in selected else ()):
        target=next((r for r in candidates if rule['minimum_level']<=r[1]<=rule['maximum_level']and(not rule['armor_only']or r[2]in(8,9,10,11))),None)
        assert target is not None,('No legal target fixture',t)
        gear=give(target[0],existing=True);scroll=give(t,1)
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE');set_enhancement(db,1001,gear['uid'],0,-8)
        payload=struct.pack('>QiB',gear['uid'],t,0);op='restore-'+str(t)
        reply=equipment_restoration.restore(path,1001,payload,op,account_id=1)
        assert struct.unpack_from('>i',reply[0].payload)[0]==0
        now={i['uid']:i for i in items()};assert now[gear['uid']]['enhancement']==8 and scroll['uid']not in now
        before=dump();equipment_restoration.restore(path,1001,payload,op,account_id=1);assert dump()==before
        discard(gear['uid'])
    if 'restoration'in selected:checks.append(dict(kind='restoration',variants=len(rules['restoration']),normal_result=True,replay=True))

    if 'reforge'in selected:
        from els_server.storage.reforge_scroll import perform as reforge_scroll
        from els_server.domain.equipment_reforge_rules import target as reforge_target,expected_options
        from els_server.storage.equipment_reforge import replace as save_reforge
        from els_server.storage.equipment_options import replace as save_options
        for source,rule in rules['reforge'].items():
            t=next(t for t in rule['targets']if reforge_target(t)is not None)
            gear=give(t,existing=True);scroll=give(source)
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE');save_options(db,1001,gear['uid'],{}, {'13':expected_options(t,0)})
                save_reforge(db,1001,gear['uid'],[0,100,0],[0,63,1])
            payload=struct.pack('>QQ',gear['uid'],scroll['uid']);op='reforge-'+str(source)
            result=reforge_scroll(path,1001,1,payload,op,prepare=lambda:None)
            current={i['uid']:i for i in items()};assert result[0].kind==0xa23 and current[gear['uid']]['reforge']==[rule['level'],63,0]and scroll['uid']not in current
            assert current[gear['uid']]['option_groups']['13']==expected_options(t,rule['level'])
            before=dump();reforge_scroll(path,1001,1,payload,op,prepare=lambda:None);assert dump()==before
            discard(gear['uid'])
        checks.append(dict(kind='reforge',variants=len(rules['reforge']),normal_result=True,replay=True,durability_preserved=True))
        source=next(iter(rules['reforge']));scroll=give(source);gear=give(60100);payload=struct.pack('>QQ',gear['uid'],scroll['uid']);before=dump()
        try:reforge_scroll(path,1001,1,payload,'wrong-reforge-target',prepare=lambda:None)
        except ValueError:pass
        else:raise AssertionError('Wrong reforge family must fail')
        assert dump()==before;discard(gear['uid'],scroll['uid'])

    def level(n):
        with closing(sqlite3.connect(path))as db,db:
            db.execute('UPDATE characters SET level=? WHERE uid=1001',(n,));db.execute('UPDATE reward_balances SET experience=? WHERE uid=1001',(data.thresholds[n-1],))
    def notice(db,current,wallet):return return_user_sync(account.get_location(),account.get_skills(),wallet,current,load_character(db,1001,1))
    def prepare(db):assert db.in_transaction
    for t,rule in ((t,r)for t,r in rules['sage'].items()if ('sage'in selected and 'destination_level'not in r)or('sage_fixed'in selected and 'destination_level'in r)):
        level(rule['minimum_level']);scroll=give(t);payload=struct.pack('>QQiiIB',scroll['uid'],0,0,0,0,0);op='sage-'+str(t)
        wisdom_potions.perform(path,1001,1,payload,op,account.reward_store,prepare=prepare,notice=notice)
        with closing(sqlite3.connect(path))as db:assert db.execute('SELECT level FROM characters WHERE uid=1001').fetchone()==(rule.get('destination_level',rule['minimum_level']+1),)
        assert scroll['uid']not in{i['uid']for i in items()};before=dump()
        wisdom_potions.perform(path,1001,1,payload,op,account.reward_store,prepare=prepare,notice=notice);assert dump()==before
    if 'sage'in selected:checks.append(dict(kind='sage',variants=sum('destination_level'not in r for r in rules['sage'].values()),normal_result=True,replay=True))

    if 'sage_fixed'in selected:checks.append(dict(kind='sage_fixed',variants=8,normal_result=True,replay=True))

    if 'resonance'in selected:
        from els_server.domain.resonance_allocation_flow import definitions
        from els_server.domain.resonance_category_scroll import scroll_items
        from els_server.storage.resonance_2026_scrolls import ScrollOperations
        from els_server.storage.resonance_2026_resets import initialize
        curve,stats=definitions()
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE');operations=ScrollOperations(db,curve,stats,scroll_items())
            profiles=operations.profiles;profiles.initialize();initialize(db)
            profiles.accounts.record(account=1,character=1001,operation='qa-progress',expected_revision=0,level=10,cumulative_experience=curve.threshold(10))
            profiles.synchronize(account=1,character=1001)
        for t in rules['resonance']:
            scroll=give(t)
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE');operations=ScrollOperations(db,curve,stats,scroll_items());pages=operations.profiles.pages
                state=pages.read(1,1001);stat=next(s for s in pages.rules.stats if s.tab==0)
                request=struct.pack('>IBIiiB',1,0,1,stat.stat_id,1,1)
                allocated=pages.allocate(account=1,character=1001,operation='allocate-'+str(t),expected_revision=state.revision,payload=request,bonus_points=())
                result=operations.edit(account=1,character=1001,operation='reset-'+str(t),expected_revision=allocated.revision,payload=bytes((0,1)),kind=0x613)
                current=pages.read(1,1001);assert current.selected().available_points==state.selected().available_points and current.selected().points==state.selected().points
                assert result.kind==0x614
            assert scroll['uid']not in{i['uid']for i in items()};before=dump()
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE');operations=ScrollOperations(db,curve,stats,scroll_items())
                operations.edit(account=1,character=1001,operation='reset-'+str(t),expected_revision=allocated.revision,payload=bytes((0,1)),kind=0x613)
            assert dump()==before
        from types import SimpleNamespace
        scroll=give(163564);new_items=scroll_items();legacy=SimpleNamespace(groups=new_items.groups,allowed={'scroll':frozenset((163564,))},digest=new_items.legacy_digests[0])
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE');operations=ScrollOperations(db,curve,stats,legacy);pages=operations.profiles.pages;state=pages.read(1,1001)
            stat=next(s for s in pages.rules.stats if s.tab==0)
            allocated=pages.allocate(account=1,character=1001,operation='legacy-allocate',expected_revision=state.revision,payload=struct.pack('>IBIiiB',1,0,1,stat.stat_id,1,1),bonus_points=())
            operations.edit(account=1,character=1001,operation='legacy-reset',expected_revision=allocated.revision,payload=bytes((0,1)),kind=0x613)
        before=dump()
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE');ScrollOperations(db,curve,stats,new_items).edit(account=1,character=1001,operation='legacy-reset',expected_revision=allocated.revision,payload=bytes((0,1)),kind=0x613)
        assert dump()==before
        checks.append(dict(kind='resonance',variants=len(rules['resonance']),normal_result=True,replay=True))

    if 'shadow'in selected:
        from els_server.storage.tenebros_identification import perform,SCROLLS,target_info
        from els_server.domain.tenebros_rules import catalog as shadows
        t=next(int(t)for t in shadows()['templates']if int(t)in VERIFIED_TEMPLATES and TEMPLATE_BAG_GROUPS[int(t)]==1)
        for source in SCROLLS:
            gear=give(t,existing=True);target_info(gear);scroll=give(source)
            payload=struct.pack('>Q',gear['uid']);op='shadow-'+str(source)
            result=perform(path,1001,1,payload,op,prepare=prepare,randbelow=lambda n:0)
            assert result[0].kind==0x9f0
            current={i['uid']:i for i in items()};assert len(current[gear['uid']]['option_groups']['25'])==3 and scroll['uid']not in current
            before=dump();perform(path,1001,1,payload,op,prepare=prepare,randbelow=lambda n:(_ for _ in ()).throw(AssertionError('Replay drew again')));assert dump()==before
            discard(gear['uid'])
        checks.append(dict(kind='shadow',variants=len(SCROLLS),normal_result=True,replay=True,already_supported=True))

    if 'artifact'in selected:
        from els_server.domain.artifact_progression import catalog as artifacts
        from els_server.domain.character_rules import CLASSES
        master_class=next(k for k,v in CLASSES.items() if v['stage']==3 and data.unit(k)['unitType']==1)
        from els_server.storage.artifact_progression import action
        with closing(sqlite3.connect(path))as db,db:
            db.execute('UPDATE characters SET level=99,unit_class=?,master=1,transcendence=1 WHERE uid=1001',(master_class,))
            db.execute('UPDATE reward_balances SET experience=? WHERE uid=1001',(data.thresholds[98],))
            db.execute('INSERT INTO character_artifacts VALUES(1001,1,1,1,0,?) ON CONFLICT(uid) DO UPDATE SET evolution=1,level=1,experience=0,potentials=excluded.potentials',('[0,0,0,0]',))
        for t in artifacts()['level_up_items']:
            with closing(sqlite3.connect(path))as db,db:db.execute('UPDATE character_artifacts SET evolution=1,level=1,experience=0 WHERE uid=1001')
            scroll=give(t,2);payload=struct.pack('>QQiiIB',scroll['uid'],2,0,0,0,1);op='artifact-bulk-'+str(t)
            result=action(path,1001,'potion',payload,op,account_id=1)
            assert result[0].kind==0x21a and scroll['uid']not in {i['uid']for i in items()}
            with closing(sqlite3.connect(path))as db:assert db.execute('SELECT evolution,level FROM character_artifacts WHERE uid=1001').fetchone()==(1,3)
            before=dump();action(path,1001,'potion',payload,op,account_id=1);assert dump()==before
        for t in artifacts()['reset_priority']:
            from els_server.domain.artifact_progression import draw
            with closing(sqlite3.connect(path))as db,db:db.execute('UPDATE character_artifacts SET evolution=3,level=1,experience=0,potentials=? WHERE uid=1001',(json.dumps([draw(0,lambda n:0),0,0,0]),))
            scroll=give(t);payload=struct.pack('>iBi',0,1,0);op='potential-'+str(t)
            result=action(path,1001,'potential',payload,op,account_id=1)
            assert result[0].kind==0x908 and scroll['uid']not in {i['uid']for i in items()}
            with closing(sqlite3.connect(path))as db:assert json.loads(db.execute('SELECT potentials FROM character_artifacts WHERE uid=1001').fetchone()[0])==[0,0,0,0]
            before=dump();action(path,1001,'potential',payload,op,account_id=1);assert dump()==before
        checks.append(dict(kind='artifact',bulk_flag=1,growth_variants=len(artifacts()['level_up_items']),potential_variants=len(artifacts()['reset_priority']),normal_result=True,replay=True))

    if 'magic'in selected:
        from els_server.domain.character_custom import catalog as customs,socket_options
        from els_server.storage.character_custom import use_book,assign_ability,snapshot
        level(99)
        for group in (0,1):
            rule=next(r for r in customs().values()if r['type']==3 and 1 in r['units'] and (r['ability_group']or 0)==group)
            book=give(rule['book'],existing=True);cid=rule['custom_ids'][0]
            result=use_book(path,1001,1,struct.pack('>QQiiIB',book['uid'],0,0,0,0,0),'custom-book-'+str(group))
            assert result['events'][0].payload[:4]==bytes(4)
            source=give(295995,2,existing=True);ability=next(iter(socket_options(group)))
            payload=struct.pack('>QQiiIB',source['uid'],cid,3,ability,0,0);op='magic-first-'+str(group)
            assign_ability(path,1001,1,payload,op)
            assert next(i for i in items()if i['uid']==source['uid'])['count']==(1 if group==0 else 2)
            before=dump();assign_ability(path,1001,1,payload,op);assert dump()==before
            ability=next(v for v in socket_options(group)if v!=ability)
            payload=struct.pack('>QQiiIB',source['uid'],cid,3,ability,0,0);op='magic-reassign-'+str(group)
            assign_ability(path,1001,1,payload,op)
            current={i['uid']:i for i in items()};assert (source['uid']not in current if group==0 else current[source['uid']]['count']==1)
            with closing(sqlite3.connect(path))as db:assert next(v for v in snapshot(db,1001)['owned'][3]if v['custom_id']==cid)['ability']==ability
            before=dump();assign_ability(path,1001,1,payload,op);assert dump()==before
            discard(source['uid'])
        checks.append(dict(kind='magic',first_group0_paid=True,first_group1_free=True,reassign_paid=True,replay=True,already_supported=True))

    if 'wardrobe'in selected:
        from els_server.domain.wardrobe_extensions import catalog as closets,unregister_group
        from els_server.domain.wardrobe import catalog as fashion_catalog,require_owner
        from els_server.storage.wardrobe import change,extension_change,counts
        for source,group in closets()['unregister'].items():
            def suitable(t):
                try:
                    if t not in VERIFIED_TEMPLATES or unregister_group(t)!=group:return False
                    require_owner(t,dict(unit_type=1,unit_class=1));return True
                except ValueError:return False
            t=next(t for t in fashion_catalog()if suitable(t))
            gear=give(t,existing=True);scroll=give(int(source),existing=True)
            change(path,1001,1,0x4af,struct.pack('>Q',gear['uid']),'hanger-'+source,validate=lambda:None)
            assert next(i for i in items()if i['uid']==gear['uid']).get('wardrobe_hanger')
            payload=struct.pack('>QQ',scroll['uid'],gear['uid']);op='unregister-'+source
            result=extension_change(path,1001,1,0x6d7,payload,op,validate=lambda:None)
            current={i['uid']:i for i in items()};assert result[0].kind==0x6d8 and not current[gear['uid']].get('wardrobe_hanger')and scroll['uid']not in current
            with closing(sqlite3.connect(path))as db:assert not counts(db,1001,1).get(t)
            before=dump();retry=extension_change(path,1001,1,0x6d7,payload,op,validate=lambda:None);assert dump()==before
            registry_count=struct.unpack_from('>I',retry[0].payload,4)[0];assert struct.unpack_from('>I',retry[0].payload,8+registry_count*8)[0]==2
            discard(gear['uid'])
        checks.append(dict(kind='wardrobe',variants=len(closets()['unregister']),normal_result=True,replay=True,already_supported=True))

    if 'challenge'in selected:
        import uuid
        from els_server.storage import challenge_scroll
        from els_server.storage.challenge_state import ChallengeState
        from els_server.domain.dungeon_routes import route_catalog
        for index,(source,rule)in enumerate(rules['challenge'].items()):
            now=int(time.time())-index*14*86400;category=rule['category']
            node=next(p['nodes'][0]['dungeon']for p in route_catalog()._data['challenges']if p['challenge']==category)
            attempts=ChallengeState(path,1001,clock=lambda:now)
            if index==0:
                empty=give(source);empty_payload=struct.pack('>QQiiIB',empty['uid'],0,0,0,0,0);before=dump()
                try:challenge_scroll.perform(path,1001,1,empty_payload,'empty-challenge',prepare=prepare,now=now)
                except ValueError:pass
                else:raise AssertionError('Zero progress must not consume a scroll')
                assert dump()==before;discard(empty['uid'])
            def clear():
                saved=attempts.begin(category,1,account_id=1)
                account.reward_store.grant(str(uuid.uuid4()),b'owned-challenge-clear-proof',0,0,lambda *a:bytes(4),dungeon_clear=(node,1),challenge_clear=dict(attempt=saved['attempt'],dungeon=node,now=now))
            clear();scroll=give(source);payload=struct.pack('>QQiiIB',scroll['uid'],0,0,0,0,0);op='challenge-'+str(source)
            before=dump()
            try:challenge_scroll.perform(path,1001,1,payload,op,prepare=prepare,now=now)
            except ValueError:pass
            else:raise AssertionError('Active challenge must refuse reset')
            assert dump()==before;attempts.abandon(account_id=1)
            if index==0:
                before=dump()
                with patch.object(challenge_scroll,'notice',side_effect=ValueError('encoder fixture')):
                    try:challenge_scroll.perform(path,1001,1,payload,op,prepare=prepare,now=now)
                    except ValueError:pass
                    else:raise AssertionError('Challenge encoder rollback')
                assert dump()==before
            result=challenge_scroll.perform(path,1001,1,payload,op,prepare=prepare,now=now)
            assert result[0].payload[:4]==bytes(4)and scroll['uid']not in{i['uid']for i in items()}
            with closing(sqlite3.connect(path))as db:value=challenge_scroll.snapshot(db,1001,category,now)
            assert value['used']==1 and value['clears']==0
            clear();attempts.abandon(account_id=1);before=dump()
            challenge_scroll.perform(path,1001,1,payload,op,prepare=prepare,now=now);assert dump()==before
            with closing(sqlite3.connect(path))as db:assert challenge_scroll.snapshot(db,1001,category,now)['clears']==1
            second=give(source);second_payload=struct.pack('>QQiiIB',second['uid'],0,0,0,0,0)
            challenge_scroll.perform(path,1001,1,second_payload,op+'-second',prepare=prepare,now=now)
            clear();attempts.abandon(account_id=1);third=give(source);third_payload=struct.pack('>QQiiIB',third['uid'],0,0,0,0,0);before=dump()
            try:challenge_scroll.perform(path,1001,1,third_payload,op+'-third',prepare=prepare,now=now)
            except ValueError:pass
            else:raise AssertionError('Challenge two resets per category/week')
            assert dump()==before;discard(third['uid'])
            with closing(sqlite3.connect(path))as db:
                assert challenge_scroll.snapshot(db,1001,category,now)['used']==2
                assert challenge_scroll.snapshot(db,1001,category,now+7*86400)['used']==0
        now=int(time.time());attempts=ChallengeState(path,1001);saved=attempts.begin(5,1,account_id=1)
        account.reward_store.grant(str(uuid.uuid4()),b'owned-other-category',0,0,lambda *a:bytes(4),dungeon_clear=(34960,1),challenge_clear=dict(attempt=saved['attempt'],dungeon=34960,now=now));attempts.abandon(account_id=1)
        scroll=give(136154);challenge_scroll.perform(path,1001,1,struct.pack('>QQiiIB',scroll['uid'],0,0,0,0,0),'other-category',prepare=prepare,now=now)
        with closing(sqlite3.connect(path))as db:
            assert challenge_scroll.snapshot(db,1001,4,now)['used']==2 and challenge_scroll.snapshot(db,1001,5,now)['used']==1
        checks.append(dict(kind='challenge',variants=len(rules['challenge']),both_open=True,normal_result=True,replay_preserves_new_progress=True,two_per_category_week=True,active_refused=True,encoder_rollback=True,synthetic_clear_receipts=True))

    if 'flow'in selected:
        import asyncio,uuid
        from els_server.application import Application
        from els_server.config import ServerConfig
        from els_server.protocol.protocol_codec import Event
        async def flow():
            app=Application(ServerConfig(state_file=path,log_dir=path.parent/'logs'));app.account=account
            session=await app.session()
            try:
                session.role='game';session.phase='town_ready';session.completed.update((0x28,0x225,0x227));level(4)
                scroll=give(710093,2);payload=struct.pack('>QQiiIB',scroll['uid'],2,0,0,0,1)
                result=session.handle(Event(0x202,kind=0x219,payload=payload),100)
                assert next(e for e in result if e.kind==0x21a).payload[:4]==bytes(4)
                with closing(sqlite3.connect(path))as db:assert db.execute('SELECT level FROM characters WHERE uid=1001').fetchone()==(6,)
                level(20)
                from els_server.storage import skill_traits
                skill_traits.choose(path,1001,1,struct.pack('>ii',21000,3),'flow-trait')
                scroll=give(711711);payload=struct.pack('>iiQB',21000,3,scroll['uid'],0)
                result=session.handle(Event(0x202,kind=0x55f,payload=payload),106)
                assert next(e for e in result if e.kind==0x560).payload[:4]==bytes(4)
                with closing(sqlite3.connect(path))as db:assert not skill_traits.saved(db,1001)
                from els_server.domain.character_rules import CLASSES
                from els_server.domain.artifact_progression import catalog as artifacts
                master_class=next(k for k,v in CLASSES.items()if v['stage']==3 and data.unit(k)['unitType']==1)
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('UPDATE characters SET level=99,unit_class=?,master=1,transcendence=1 WHERE uid=1001',(master_class,))
                    db.execute('UPDATE reward_balances SET experience=? WHERE uid=1001',(data.thresholds[98],))
                    db.execute('INSERT INTO character_artifacts VALUES(1001,1,1,1,0,?)',('[0,0,0,0]',))
                scroll=give(artifacts()['level_up_items'][0],2);payload=struct.pack('>QQiiIB',scroll['uid'],2,0,0,0,1)
                result=session.handle(Event(0x202,kind=0x219,payload=payload),105)
                assert next(e for e in result if e.kind==0x21a).payload[:4]==bytes(4)
                with closing(sqlite3.connect(path))as db:assert db.execute('SELECT level FROM character_artifacts WHERE uid=1001').fetchone()==(3,)
                gear=give(118153,existing=True);scroll=give(713423);payload=struct.pack('>QQ',gear['uid'],scroll['uid'])
                result=session.handle(Event(0x202,kind=0xa22,payload=payload),101)
                assert next(e for e in result if e.kind==0xa23).payload[:4]==bytes(4)
                assert next(i for i in items()if i['uid']==gear['uid'])['reforge'][0]==6
                from els_server.storage.challenge_state import ChallengeState
                attempt=ChallengeState(path,1001);saved=attempt.begin(4,1,account_id=1);now=int(time.time())
                account.reward_store.grant(str(uuid.uuid4()),b'owned-flow-clear',0,0,lambda *a:bytes(4),dungeon_clear=(34850,1),challenge_clear=dict(attempt=saved['attempt'],dungeon=34850,now=now))
                from els_server.domain.challenge_flow import notification
                from els_server.domain.raid_reward_flow import synchronize
                notification(session);weekly=synchronize(session,[])
                assert any(e.kind==0x7c1 and struct.unpack_from('>i',e.payload)[0]==4 and struct.unpack_from('>i',e.payload,12)[0]==1 for e in weekly)
                attempt.abandon(account_id=1)
                scroll=give(136153);payload=struct.pack('>QQiiIB',scroll['uid'],0,0,0,0,0)
                result=session.handle(Event(0x202,kind=0x219,payload=payload),102)
                assert next(e for e in result if e.kind==0x21a).payload[:4]==bytes(4)and any(e.kind==0x7c1 for e in result)
                before=dump();session.handle(Event(0x202,kind=0x219,payload=payload),102);assert dump()==before
                scroll=give(710094);payload=struct.pack('>QQiiIB',scroll['uid'],0,0,0,0,0);before=dump();session.phase='dungeon_active'
                assert next(e for e in session.handle(Event(0x202,kind=0x219,payload=payload),103)if e.kind==0x21a).payload[:4]!=bytes(4);assert dump()==before
                session.phase='town_ready';session._chip_reset_local_live=False
                assert next(e for e in session.handle(Event(0x202,kind=0x219,payload=payload),104)if e.kind==0x21a).payload[:4]!=bytes(4);assert dump()==before
            finally:await app.release(session);app.close()
        asyncio.run(flow());checks.append(dict(kind='flow',actual_Application=True,actual_session_handle=True,sage=True,reforge=True,challenge=True,wrong_phase_and_lease_refused=True))

    if 'reset'in selected:
        from els_server.storage.identification_ui import perform as identify
        from els_server.storage import skill_traits
        from els_server.storage.skill_trait_reset import reset as forget
        from els_server.domain.skill_trait_reset import reset_items
        level(20)
        with closing(sqlite3.connect(path))as db,db:db.execute('UPDATE reward_balances SET ed=2000000 WHERE uid=1001')
        for source in(287960,287961,710078,710079,710080,710081):
            gear=give(61885);scroll=give(source);payload=struct.pack('>QQ',scroll['uid'],gear['uid']);op='identify-reset-'+str(source)
            identify(path,1001,0x43a,payload,op,account_id=1)
            identify(path,1001,0x438,struct.pack('>QBIi',gear['uid'],0,0,0),'identify-'+str(source),lambda n:0,account_id=1)
            current=next(i for i in items()if i['uid']==gear['uid']);assert current['identified']and current['option_groups']['1']and scroll['uid']not in{i['uid']for i in items()}
            before=dump();identify(path,1001,0x43a,payload,op,account_id=1);assert dump()==before;discard(gear['uid'])
        for source in reset_items():
            skill_traits.choose(path,1001,1,struct.pack('>ii',21000,3),'choose-'+str(source));scroll=give(source)
            payload=struct.pack('>iiQB',21000,3,scroll['uid'],0);op='forget-'+str(source)
            result=forget(path,1001,1,payload,op,prepare=prepare)
            assert result.kind==0x560 and result.payload[:4]==bytes(4)and scroll['uid']not in{i['uid']for i in items()}
            with closing(sqlite3.connect(path))as db:assert not skill_traits.saved(db,1001)
            before=dump();forget(path,1001,1,payload,op,prepare=prepare);assert dump()==before
        assert account.get_reward_balances()['ed']==2000000
        checks.append(dict(kind='reset',identification_variants=6,forget_variants=10,normal_result=True,replay=True,no_ED_for_scroll=True))

    if 'challenge_ordinal'in selected:
        import uuid
        from els_server.storage.challenge_scroll import snapshot
        from els_server.storage.challenge_state import ChallengeState
        from els_server.storage.raid_economy_state import week_at
        week=week_at(int(time.time()));clock=[week-600];attempts=ChallengeState(path,1001,clock=lambda:clock[0])
        def clear_node(node):
            saved=attempts.current()
            account.reward_store.grant(str(uuid.uuid4()),b'owned-split-encounter',0,0,lambda *a:bytes(4),dungeon_clear=(node,1),challenge_clear=dict(attempt=saved['attempt'],dungeon=node,now=clock[0]))
        attempts.begin(4,1,account_id=1)
        for node in(34850,34860,34870):clear_node(node)
        clock[0]=week+300;clear_node(34870);attempts.abandon(account_id=1)
        clock[0]+=60;attempts.begin(4,1,account_id=1)
        for node in(34850,34860,34870):clear_node(node)
        with closing(sqlite3.connect(path))as db:
            assert snapshot(db,1001,4,clock[0])['clears']==4
            assert snapshot(db,1001,4,week-1)['clears']==3
        checks.append(dict(kind='challenge_ordinal',repeated_first_encounter_deduplicated=True,attempt_across_week_boundary=True,preexisting_receipts_read=True))

    if 'failure'in selected:
        gear=give(60100);scroll=give(130149);payload=struct.pack('>QQ',gear['uid'],scroll['uid']);before=dump()
        with patch.object(enhancement_scroll,'_commit',side_effect=ValueError('rollback')):
            try:enhancement_scroll.apply(path,1001,payload,'failed-enhance',account_id=1)
            except ValueError:pass
            else:raise AssertionError('Enhancement must roll back')
        assert dump()==before;discard(gear['uid'],scroll['uid'])
        level(99);scroll=give(710093);payload=struct.pack('>QQiiIB',scroll['uid'],0,0,0,0,0);before=dump()
        try:wisdom_potions.perform(path,1001,1,payload,'max-level',account.reward_store,prepare=prepare,notice=notice)
        except ValueError:pass
        else:raise AssertionError('Sage maximum-level qualification')
        assert dump()==before
        checks.append(dict(kind='failure',rollback=True,qualification=True))
print(json.dumps(dict(mode=args.mode,checks=checks,formal_installation=False,natural_GUI=False)))
