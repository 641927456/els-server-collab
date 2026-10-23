"""Resource-free metadata/forwarding checks; not full Application/TLS proof."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import math
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import town_dialogue as target
from els_server.domain import town_travel as travel
from els_server.protocol.protocol_codec import Event

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'els_server/data'
read=lambda p:json.loads(p.read_bytes())


def scene_source():
    tree=ast.parse((ROOT/'els_server/storage/local_state.py').read_text('utf8'))
    assignment=next(n for n in tree.body if isinstance(n,ast.Assign)and n.targets[0].id=='TOWN_SCENES')
    nodes=[assignment]+[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in('validate_location','scene_ready_location')]
    g=dict(math=math,struct=struct)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'existing-location-validation','exec'),g)
    return g


def aurora_guard(row):
    """Run the exact newly inserted strict block, excluding unchanged rewards."""
    tree=ast.parse((ROOT/'els_server/domain/town_dialogue.py').read_text('utf8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='catalog')
    start=next(i for i,n in enumerate(fn.body)if isinstance(n,ast.Assign)and isinstance(n.targets[0],ast.Name)and n.targets[0].id=='quest'and isinstance(n.value,ast.Subscript)and isinstance(n.value.slice,ast.Constant)and n.value.slice.value=='23690')
    nodes=fn.body[start:start+4]
    selfcheck=ast.dump(ast.Module(body=nodes,type_ignores=[]))
    assert 'Aurora original second NPC10360 dialogue'in selfcheck
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'original-Aurora-binding-guard','exec'),dict(row=row))


class Noah1010Continuation(unittest.TestCase):
    def test_two_exact_original_links_zero_rewards_and_manifests(self):
        row=read(DATA/'town_dialogue_quests.json');m=read(DATA/'town_dialogue_quests.manifest.json')
        self.assertTrue({'23690','23700'}<=set(row['quests']))
        self.assertEqual({int(q)for q in row['quests']},set(target.QUEST_IDS))
        self.assertEqual((len(row['quests']),len(row['subquests'])),(m['quests'],m['subquests']))
        self.assertEqual(hashlib.sha256((DATA/'town_dialogue_quests.json').read_bytes()).hexdigest(),m['payload_sha256'])
        for q,after in((23690,23700),(23700,23710)):
            d=row['quests'][str(q)]
            self.assertEqual(d['m_iAfterQuestID'],{'0':None,'1':after})
            self.assertEqual(d['m_vecSubQuest'],{'0':None,'1':23550})
            self.assertEqual((d['m_eStartNPCID'],d['m_eEndNPCID']),(10360,10360))
            self.assertEqual(d['QuestCondition']['m_iLevel'],99)
            self.assertEqual(set(d['QuestCondition']['m_eUnitType'].values()),set(range(1,15)))
            self.assertEqual(tuple(d['Reward'][k]for k in('m_iED','m_iEXP','m_iEP')),(0,0,0))
        t=read(DATA/'town_travel.json');tm=read(DATA/'town_travel.manifest.json')
        self.assertEqual(len(t['towns']),tm['towns'])
        self.assertEqual(hashlib.sha256((DATA/'town_travel.json').read_bytes()).hexdigest(),tm['payload_sha256'])

    def test_exact_Aurora_binding_and_tamper_rejections(self):
        row=read(DATA/'town_dialogue_quests.json');aurora_guard(row)
        for change in('house','NPC','scene','after','level','sub'):
            d=copy.deepcopy(row)
            if change=='house':d['npc_bindings']['10360']['houses']=[40258]
            if change=='NPC':d['subquests']['23550']['m_ClearCondition']['m_eTalkNPCID']=10361
            if change=='scene':d['npc_bindings']['10360']['towns']['1010']=963
            if change=='after':d['quests']['23700']['m_iAfterQuestID']['1']=23720
            if change=='level':d['quests']['23690']['QuestCondition']['m_iLevel']=98
            if change=='sub':d['quests']['23700']['m_vecSubQuest']['1']=23551
            with self.subTest(change=change),self.assertRaises(ValueError):aurora_guard(d)

    def test_loader_identity_precedes_unchanged_external_reward_boundary(self):
        row=read(DATA/'town_dialogue_quests.json');scenes=scene_source()['TOWN_SCENES']
        class Boundary(Exception):pass
        def external_reward_boundary(*args):raise Boundary('original locked reward resources not replaced')
        modules={'els_server.storage.local_state':NS(TOWN_SCENES=scenes),'els_server.domain.inventory_items':NS(VERIFIED_TEMPLATES=set()),'els_server.domain.acquisition_policy':NS(require_acquirable=external_reward_boundary)}
        with patch.dict(sys.modules,modules),patch.object(target,'PROJECT_ROOT',ROOT),patch.object(target,'client_data',return_value=NS(manifest={'catalog_sha256':row['catalog_sha256']})):
            target.catalog.cache_clear()
            with self.assertRaises(Boundary):target.catalog()
            with tempfile.TemporaryDirectory()as folder:
                root=Path(folder);dest=root/'els_server/data';dest.mkdir(parents=True)
                altered=copy.deepcopy(row);altered['towns']['1010']=963
                raw=json.dumps(altered).encode();(dest/'town_dialogue_quests.json').write_bytes(raw)
                manifest=read(DATA/'town_dialogue_quests.manifest.json');manifest['payload_sha256']=hashlib.sha256(raw).hexdigest();(dest/'town_dialogue_quests.manifest.json').write_text(json.dumps(manifest),'utf8')
                with patch.object(target,'PROJECT_ROOT',root):
                    target.catalog.cache_clear()
                    with self.assertRaisesRegex(ValueError,'scene identity'):target.catalog()
        target.catalog.cache_clear()

    def test_original_FD_forwarding_and_wrong_place_rejection(self):
        row=read(DATA/'town_dialogue_quests.json');calls=[];store=object()
        session=NS(role='game',phase='town_ready',active_map=1010,account=NS(uid=1001,get_location=lambda:{'map':1010}),shop_session_id='fixture-session')
        event=Event(0x202,kind=0xfd,performers=(0,),payload=struct.pack('>i',10360))
        def interact(actual,npc,operation):calls.append((actual,npc,operation));return ['forwarded']
        with patch.object(target,'catalog',return_value=row),patch.dict(sys.modules,{'els_server.storage.town_dialogue':NS(interact=interact),'els_server.domain.quest_flow':NS(store=lambda s:store)}):
            self.assertEqual(target.handle(session,event,1),['forwarded'])
            self.assertEqual(calls[0][:2],(store,10360))
            session.active_map=20010
            reply=target.handle(session,event,2)
            self.assertEqual(len(calls),1)
            self.assertEqual(reply[0].kind,0xfe)
            self.assertEqual(struct.unpack('>i',reply[0].payload[:4])[0],187)
            session.active_map=1010
            self.assertEqual(target.target(row['subquests']['23550']),1)
            with self.assertRaises(ValueError):target.target(dict(row['subquests']['23550'],m_iID=999))

    def test_existing_58C_admission_and_price_use_original_rules(self):
        data=read(DATA/'town_travel.json')
        with patch.object(travel,'catalog',return_value=data),patch.dict(sys.modules,{'els_server.domain.dungeon_routes':NS(route_catalog=lambda:NS(entry_identity=lambda value:value))}):
            row=travel.require_destination(1010,dict(unit_type=14,level=99),{26670},set())
            self.assertEqual((row['scene'],row['warp_start']['StartPosId'],row['xyz']),(964,1701,[-5245.0,152.0,-210.0]))
            self.assertEqual(travel.price(1010,20010,99),9900)
            for character,done in[(dict(unit_type=14,level=98),{26670}),(dict(unit_type=14,level=99),set())]:
                with self.assertRaises(ValueError):travel.require_destination(1010,character,done,set())

    def test_original_location_validation_accepts1010_and_preserves_old_towns(self):
        g=scene_source();g['validate_location'](1010,0,0,(-5245.,152.,-210.));g['validate_location'](20010,0,0,(0.,0.,0.))
        self.assertEqual(g['TOWN_SCENES'][1010],964)
        self.assertEqual(g['TOWN_SCENES'][20010],778)
        with self.assertRaises(ValueError):g['validate_location'](1010,0,0,(float('nan'),0.,0.))


if __name__=='__main__':unittest.main()
