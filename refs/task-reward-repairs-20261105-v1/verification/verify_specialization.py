"""Source rewards -> exchange -> native specialization; private SQL only."""
import json,sqlite3,struct,unittest
from contextlib import closing
from dataclasses import asdict,replace as replace_profile
from unittest.mock import patch
import verify_furniture as harness
from verify_furniture import Consumers,encode,box,checks,PRIVATE,OUT,temp
from els_server.storage import pvp_specialization as store,pvp_official_profiles as profiles
from els_server.domain.pvp_specialization import catalog,request,options
from els_server.storage.fixed_cubes import open_cube
from els_server.storage.material_exchange import exchange
from els_server.protocol.purifier_exchange_messages import ExchangeRequest
from els_server.protocol.fish_exchange_messages import acknowledgement as exchange_ack
from els_server.protocol.pvp_match_messages import registration_ack

def wire(uid,group=22,slot=1,choice=1000000,mode=12):return struct.pack('>QIiIiQBiB',uid,1,group,1,slot,choice,0,mode,0)

class Specialization(Consumers):
    def profile(self,ap=10000):
        payload=struct.pack('>IBBBiI',1,0,1,0,0,0)
        profiles.register(self.path,self.uid,1,payload,'owned-registration',guard=lambda:None,encode=lambda p,r:[registration_ack(0,False,'')])
        # Explicit private AP fixture; not a fabricated live match/result source.
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            p,rev=profiles.snapshot(db,self.uid,1)
            db.execute('UPDATE official_pvp_profiles SET profile_json=?WHERE uid=?',(json.dumps(asdict(replace_profile(p,ap=ap))),self.uid))
    def ap(self):
        with closing(sqlite3.connect(self.path))as db:
            db.execute('BEGIN');return profiles.snapshot(db,self.uid,1)[0].ap
    def gear(self,weapon=False):
        qid=32090 if weapon else 32000;t=79076 if weapon else 72970
        self.ready(qid);source=self.claim(qid);boxitem=next(i for i in source['updates']if i['template']==t)
        before={i['uid']for i in self.items()};encode(open_cube(self.path,self.uid,t,box(boxitem['uid']),'open-'+str(t),account_id=1,prepare=self.guard))
        item=next(i for i in self.items()if i['uid']not in before)
        from els_server.domain.identification_ui import initial_pending
        if item.get('identified')is False or initial_pending(item):
            from els_server.storage.identification_ui import perform
            encode(perform(self.path,self.uid,1,struct.pack('>QBIi',item['uid'],0,0,0),'identify-'+str(t),prepare=self.guard))
        return next(i for i in self.items()if i['uid']==item['uid'])
    def use(self,payload,op):return store.perform(self.path,self.uid,1,payload,op,self.guard,now=2000000000)
    def current(self,item):return next(i for i in self.items()if i['uid']==item['uid'])
    def reject(self,p,op='bad'):
        before=self.dump()
        with self.assertRaises(ValueError):self.use(p,op)
        self.assertEqual(self.dump(),before)
    def test_source_coins_and_fragments_reach_effect(self):
        gear=self.gear();self.ready(32010);source=self.claim(32010)
        self.assertEqual({i['template']:i['count']for i in source['updates']if i['template']in(72920,72980)},{72920:6,72980:10})
        from els_server.domain.pvp_material_exchange import catalog as exchange_catalog
        town=int(next(iter(exchange_catalog()['towns'])))
        self.account.save_location(town,0,0,(0.,0.,0.))
        p=struct.pack('>iQiiiiiBi',40016,0,72920,1,72930,3,6,1,0);r=ExchangeRequest(*struct.unpack('>iQiiiiiBi',p))
        encode(exchange(self.path,self.uid,town,p,'source-coins',r,account_id=1,source_quantity=1,destination=72930,output_quantity=1,acknowledgement=exchange_ack,guard=self.guard))
        self.reject(wire(gear['uid']),'no-profile');self.profile(800)
        original=gear.get('option_groups',{})
        encode(self.use(wire(gear['uid']),'select'))
        self.assertEqual(self.ap(),300);self.assertFalse(any(i['template']in(72920,72930)for i in self.items()))
        self.assertEqual(self.current(gear)['option_groups']['22'],[140000001,0,0,0])
        before=self.dump();encode(self.use(wire(gear['uid']),'select'));self.assertEqual(before,self.dump())
        for n in(1,2):
            p=wire(gear['uid'],mode=11,choice=0);encode(self.use(p,'upgrade-'+str(n)))
            self.assertEqual(self.current(gear)['option_groups']['22'][0],140000001+n)
            before=self.dump();encode(self.use(p,'upgrade-'+str(n)));self.assertEqual(before,self.dump())
        self.assertEqual(self.ap(),100);self.reject(p,'no-fragments')
        self.assertEqual({k:v for k,v in self.current(gear)['option_groups'].items()if k!='22'},original)
        checks.append(dict(case='source32010_to_specialization',coins=6,fragments=10,stone_exchange=6,initial_level=1,upgrades=2,AP_initial=800,AP_final=100,replay=True,cold_SQL=True))
    def test_weapon_cap_change_and_invalid_inputs(self):
        gear=self.gear(True);self.profile(50000);self.grant(72930,90);self.grant(72980,500)
        p=wire(gear['uid'],choice=1000027);encode(self.use(p,'weapon-select'))
        self.assertEqual(self.ap(),49000)
        for n in range(1,10):encode(self.use(wire(gear['uid'],choice=0,mode=11),'weapon-up-'+str(n)))
        self.assertEqual(self.current(gear)['option_groups']['22'],[141000140,0,0,0]);self.assertEqual(self.ap(),45400)
        self.assertEqual(next(i['count']for i in self.items()if i['template']==72980),500-34*9)
        self.reject(wire(gear['uid'],choice=0,mode=11),'at-cap');self.reject(p,'same-effect')
        encode(self.use(wire(gear['uid'],choice=1000028),'change'))
        self.assertEqual(self.current(gear)['option_groups']['22'][0],141000141)
        self.reject(wire(gear['uid'],choice=1000000),'armor-effect-on-weapon')
        self.reject(wire(gear['uid'],group=24,choice=1100085),'foreign-skill')
        good=wire(gear['uid'],choice=1000027)
        for n,bad in enumerate((good[:-1],good+b'\0',good[:-6]+b'\1'+good[-5:],good[:-1]+b'\1',wire(gear['uid'],slot=0),wire(gear['uid'],slot=5),wire(gear['uid'],mode=11,choice=1000027))):self.reject(bad,'malformed-'+str(n))
        checks.append(dict(case='weapon_specialization',initial_stones=30,initial_AP=1000,upgrade_fragments=34,upgrade_AP=400,max_level=10,cap_no_debit=True,same_effect_no_debit=True,change_resets_to_1=True,malformed_atomic=True))
    def test_atomicity_skills_and_mixed_fragments(self):
        gear=self.gear();self.profile(20000);self.grant(72930,30);self.grant(72940,24);self.grant(72950,24)
        selected=wire(gear['uid'])
        for module,name in ((store,'encode_event'),(store,'_commit')):
            before=self.dump()
            with patch.object(module,name,side_effect=ValueError('owned late fault')):
                with self.assertRaises(ValueError):self.use(selected,'fault-'+name)
            self.assertEqual(before,self.dump())
        count=[0]
        def late(db):
            self.guard(db);count[0]+=1
            if count[0]>1:raise ValueError('owned stale actor')
        before=self.dump()
        with self.assertRaises(ValueError):store.perform(self.path,self.uid,1,selected,'stale',late)
        self.assertEqual(before,self.dump())
        encode(self.use(selected,'selected'));self.grant(72960,2);self.grant(72980,3)
        encode(self.use(wire(gear['uid'],choice=0,mode=11),'mixed-fragments'))
        self.assertFalse(any(i['template']in(72960,72980)for i in self.items()))
        support=int(next(k for k,r in catalog()['series'].items()if r['group']==23 and 2 in r['item_types']))
        skill=int(next(k for k,r in catalog()['series'].items()if r['group']==24 and r['unit_type']==1 and r['skill']==21000))
        for g,choice in((23,support),(24,skill)):
            for slot in range(1,5):encode(self.use(wire(gear['uid'],group=g,slot=slot,choice=choice),f'group-{g}-{slot}'))
        self.assertEqual(len(self.current(gear)['option_groups']['24']),4)
        foreign=int(next(k for k,r in catalog()['series'].items()if r['group']==24 and r['unit_type']==2))
        self.reject(wire(gear['uid'],group=24,choice=foreign),'other-role-skill')
        first_class_skill=int(next(k for k,r in catalog()['series'].items()if r['group']==24 and r['unit_type']==1 and r['skill']==21005))
        self.reject(wire(gear['uid'],group=24,choice=first_class_skill),'not-current-career')
        self.sql('UPDATE characters SET unit_class=10 WHERE uid=?',(self.uid,))
        self.grant(72950,6);encode(self.use(wire(gear['uid'],group=24,choice=first_class_skill),'first-class-skill'))
        self.assertEqual(self.current(gear)['option_groups']['24'][0],catalog()['series'][str(first_class_skill)]['options'][0])
        checks.append(dict(case='specialization_transaction',encoding_rollback=True,receipt_rollback=True,late_actor_rollback=True,old_new_fragments_aggregated=True,three_groups_four_slots=True,current_career_skill=True))

    def test_actual_actor_dispatch_and_failures(self):
        gear=self.gear();self.profile(500);self.grant(72930,6)
        from els_server.application import Application,FriendsSession
        from els_server.config import ServerConfig
        from els_server.storage.accounts import Accounts
        from els_server.domain.local_session import LocalSession
        from els_server.protocol.protocol_codec import Event
        from els_server.domain.pvp_material_exchange import catalog as exchange_catalog
        auth=PRIVATE/'owned-specialization-accounts.sqlite3';registry=Accounts(auth)
        with closing(registry.connect())as db,db:
            db.execute('INSERT INTO accounts VALUES(1,?,?,1)',('owned_qa','0'*64))
        app=Application(ServerConfig(state_file=self.path,accounts_file=auth,log_dir=PRIVATE/'logs'))
        app.registry=registry;app.accounts[1]=self.account
        s=FriendsSession(app,dict(id=1,name='owned_qa'),self.account,**app.config.session_options())
        town=int(next(iter(exchange_catalog()['towns'])))
        self.account.save_location(town,0,0,(0.,0.,0.));s.role='game';s.phase='town_ready'
        s.completed.update((0x28,0x225,0x227));s.pending_map=s.active_map=town;app.playing[1]=s
        def event(p):return Event(0x202,kind=0x6e7,payload=p,performers=(0,))
        try:
            before=self.dump();reply=LocalSession._handle(s,event(wire(gear['uid']+999)),1)
            encode(reply);self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],2005);self.assertEqual(before,self.dump())
            reply=LocalSession._handle(s,event(wire(gear['uid'])),2);encode(reply)
            self.assertEqual(reply[0].kind,0x6e8);self.assertEqual(self.ap(),0)
            before=self.dump();encode(LocalSession._handle(s,event(wire(gear['uid'])),2));self.assertEqual(before,self.dump())
            self.grant(72980,10);before=self.dump()
            reply=LocalSession._handle(s,event(wire(gear['uid'],choice=0,mode=11)),3);encode(reply)
            self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],2005);self.assertEqual(before,self.dump())
            app.playing[1]=object();before=self.dump()
            self.assertEqual(LocalSession._handle(s,event(wire(gear['uid'])),2),[]);self.assertEqual(before,self.dump())
            app.playing[1]=s
            # The same actual actor also reaches both new pet RPC consumers.
            from verify_pet import Pets
            pet=Pets.create_pet(self);food=self.grant(135977)[0];self.ready(25610);self.claim(25610)
            nutrient=Event(0x202,kind=0x8ad,payload=struct.pack('>IQiQB',1,food['uid'],1,pet['uid'],1),performers=(0,))
            reply=LocalSession._handle(s,nutrient,4);encode(reply);self.assertEqual(reply[0].kind,0x8ae)
            digestive=Event(0x202,kind=0x8b9,payload=struct.pack('>Qi',pet['uid'],135994),performers=(0,))
            reply=LocalSession._handle(s,digestive,5);encode(reply);self.assertEqual(reply[-1].kind,0x8ba)
            self.assertEqual(struct.unpack_from('>i',reply[-1].payload)[0],0)
        finally:
            registry.close();app.close()
        from els_server.storage.item_locks import assign,forget
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,self.uid,gear['uid'],2000003600)
        self.reject(wire(gear['uid'],choice=0,mode=11),'locked-target')
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');forget(db,gear['uid'])
        self.sql('UPDATE equipment_enhancement SET level=-1 WHERE item_uid=?',(gear['uid'],))
        self.reject(wire(gear['uid'],choice=0,mode=11),'broken-target')
        checks.append(dict(case='actual_shared_actor_dispatch',actual_Application_FriendsSession_Accounts=True,capture_not_mocked=True,original6E7_to6E8=True,AP_failure_current_snapshot=True,replay=True,obsolete_actor_no_delta=True,pet8AD_and8B9=True,locked_target_no_debit=True,broken_target_no_debit=True))

    def test_material_locks_and_equipped_effect(self):
        gear=self.gear();self.profile(3000);material=self.grant(72930,6)[0]
        from els_server.storage.item_locks import assign,forget
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,self.uid,material['uid'],2000003600)
        before=self.dump()
        with self.assertRaisesRegex(ValueError,'Insufficient PvP specialization materials'):self.use(wire(gear['uid']),'locked-only')
        self.assertEqual(before,self.dump());available=self.grant(72930,6)[0]
        # A repeated grant can extend the same locked stack. Remove that fixture
        # lock explicitly before the separate equipment-movement check.
        if available['uid']==material['uid']:
            with closing(sqlite3.connect(self.path))as db,db:
                db.execute('BEGIN IMMEDIATE');forget(db,material['uid'])
            self.assertEqual(self.current(material)['count'],12)
        encode(self.use(wire(gear['uid']),'use-available'))
        self.assertEqual(self.ap(),2500)
        from els_server.domain.equipment_requirements import catalog as requirements
        from els_server.game_data import client_data
        from els_server.storage.equipment_moves import move_equipment
        slot=requirements()[1][client_data().item(gear['template'])['equip_position']]
        original=self.current(gear);groups=original['option_groups'];position=original['slot']
        encode_event=__import__('els_server.protocol.protocol_codec',fromlist=['encode_event']).encode_event
        from els_server.protocol.protocol_codec import Event
        encode_event(Event(0x201,kind=0x105,payload=move_equipment(self.path,struct.pack('>BiBiB',1,position,9,slot,0),self.uid)))
        self.assertEqual(self.current(gear)['option_groups'],groups)
        self.assertEqual(self.current(gear)['group'],9)
        encode_event(Event(0x201,kind=0x105,payload=move_equipment(self.path,struct.pack('>BiBiB',9,slot,1,position,0),self.uid)))
        self.assertEqual(self.current(gear)['option_groups'],groups)
        checks.append(dict(case='specialization_material_and_wear',locked_only_rejected_atomically=True,wear_and_remove_keep_effect=True,UID_preserved=True))

if __name__=='__main__':
    names=['Specialization.'+s for s in __import__('sys').argv[1:]]if len(__import__('sys').argv)>1 else ['Specialization.'+s for s in('test_source_coins_and_fragments_reach_effect','test_weapon_cap_change_and_invalid_inputs','test_atomicity_skills_and_mixed_fragments','test_actual_actor_dispatch_and_failures','test_material_locks_and_equipped_effect')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names,module=__import__(__name__)))
    temp.cleanup();report=dict(ok=result.wasSuccessful(),tests=result.testsRun,checks=checks,failures=[dict(test=str(t),trace=e)for t,e in result.failures+result.errors],private_SQL_removed=not PRIVATE.exists(),formal_SQL=False,network=False,natural_GUI=False,natural_battle=False)
    name='specialization-'+__import__('sys').argv[1]+'-validation.json'if len(__import__('sys').argv)>1 else'specialization-validation.json'
    (OUT/name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(ok=report['ok'],private_SQL_removed=report['private_SQL_removed'])))
    raise SystemExit(0 if report['ok']else 1)
