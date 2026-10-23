"""Source/manifest/FD adapter checks; no player DB, full TLS or natural route."""
import copy
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from els_server.domain import town_dialogue as target
from els_server.protocol.protocol_codec import Event
from els_server.protocol.tutorial_dialogue_messages import acknowledgement

QUESTS=(22378,22390,22420)
AFTER={22378:22379,22390:22400,22420:22430}
SUB={'m_iID':162120,'m_eClearType':1,'m_bAutomaticDescription':0,'m_ClearCondition':{'m_eTalkNPCID':10025}}
BINDING={'houses':[40028],'towns':{'1009':851,'20010':778}}

class ResourceBoundary(RuntimeError):pass

class Npc10025Dialogue(unittest.TestCase):
    def payload(self):
        return json.loads((target.PROJECT_ROOT/'els_server/data/town_dialogue_quests.json').read_bytes())

    def test_original_rows_after_links_and_manual_claim_are_preserved(self):
        row=self.payload()
        for qid in QUESTS:
            q=row['quests'][str(qid)]
            self.assertIn(qid,target.QUEST_IDS)
            self.assertEqual(q['m_iID'],qid)
            self.assertEqual(q['QuestCondition']['m_iLevel'],99)
            self.assertEqual(set(q['QuestCondition']['m_eUnitType'].values()),set(range(1,13)))
            self.assertEqual(q['m_iAfterQuestID'],{'0':None,'1':AFTER[qid]})
            self.assertEqual(q['m_vecSubQuest'],{'0':None,'1':162120})
            self.assertEqual(q['QuestCondition']['m_vecBeforeQuestID'],{})
            self.assertFalse(q.get('m_bAutoClearQuest',0))
            self.assertEqual(q['Reward'],{'m_iSP':0,'m_iBuff':0,'m_iEP':15,'m_iED':1350000,'m_iEXP':5154470,'m_bEnable':1,'m_eChangeUnitClass':0})
        self.assertEqual(row['subquests']['162120'],SUB)
        self.assertIn(162120,target.SUBQUEST_IDS)
        self.assertEqual(row['npc_bindings']['10025'],BINDING)

    def test_actual_payload_hash_and_catalog_counts(self):
        path=target.PROJECT_ROOT/'els_server/data/town_dialogue_quests.json'
        raw=path.read_bytes();row=json.loads(raw)
        manifest=json.loads(path.with_suffix('.manifest.json').read_bytes())
        self.assertEqual(manifest['payload_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(manifest['quests'],len(row['quests']))
        self.assertEqual(manifest['subquests'],len(row['subquests']))
        self.assertEqual(set(map(int,row['quests'])),target.QUEST_IDS)
        self.assertEqual(set(map(int,row['subquests'])),target.SUBQUEST_IDS)

    def loader_to_old_resource_boundary(self,row,scenes):
        # Only new finite identity/scene checks are exercised. Existing item
        # resource validation is deliberately stopped, never mocked as passed.
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'els_server/data/town_dialogue_quests.json'
            path.parent.mkdir(parents=True)
            raw=json.dumps(row,ensure_ascii=False,indent=2).encode()+b'\n';path.write_bytes(raw)
            path.with_suffix('.manifest.json').write_text(json.dumps(dict(schema_version=2,
                payload_sha256=hashlib.sha256(raw).hexdigest(),client_sha256=row['client_sha256'],
                quests=len(row['quests']),subquests=len(row['subquests']))),encoding='utf-8')
            def item(template):raise ResourceBoundary('unchanged reward resources not exercised')
            data=NS(manifest={'catalog_sha256':row['catalog_sha256']},item=item)
            with patch.object(target,'PROJECT_ROOT',Path(root)),patch.object(target,'client_data',lambda:data),patch.dict(sys.modules,{
                'els_server.storage.local_state':NS(TOWN_SCENES=scenes),
                'els_server.domain.inventory_items':NS(VERIFIED_TEMPLATES={v['template']for v in row['reward_definitions']}),
                'els_server.domain.acquisition_policy':NS(require_acquirable=lambda template:None)}):
                target.catalog.cache_clear()
                try:return target.catalog()
                finally:target.catalog.cache_clear()

    def test_missing1009_dependency_is_not_hidden(self):
        from els_server.storage.local_state import TOWN_SCENES
        row=self.payload();scenes=dict(TOWN_SCENES);scenes.pop(1009,None)
        with self.assertRaisesRegex(ValueError,'Town dialogue NPC scene source'):
            self.loader_to_old_resource_boundary(row,scenes)

    def test_new_finite_checks_reach_existing_resource_boundary_with_scene_dependency(self):
        from els_server.storage.local_state import TOWN_SCENES
        row=self.payload();scenes=dict(TOWN_SCENES);scenes.pop(1009,None);scenes[1009]=851
        with self.assertRaisesRegex(ResourceBoundary,'unchanged reward resources not exercised'):
            self.loader_to_old_resource_boundary(row,scenes)
        # Exact House/town context is checked before the untouched reward loop.
        row['npc_bindings']['10025']['houses']=[40029]
        with self.assertRaisesRegex(ValueError,'Varnimyr NPC10025 source identity'):
            self.loader_to_old_resource_boundary(row,scenes)

    def session(self,town):
        return NS(role='game',phase='town_ready',active_map=town,shop_session_id='owned-model-session',
            account=NS(uid=1001,get_location=lambda:{'map':town}))

    def call(self,session,event,sequence):
        row=self.payload();store=NS(uid=1001);interact=Mock(return_value=[acknowledgement()])
        with patch.object(target,'catalog',lambda:row),patch.dict(sys.modules,{
            'els_server.storage.town_dialogue':NS(interact=interact),
            'els_server.domain.quest_flow':NS(store=lambda session:store)}):
            answer=target.handle(session,event,sequence)
        return answer,interact,store

    def test_fd_forwards_only_exact_npc_context_to_existing_storage(self):
        event=Event(0x202,kind=0xfd,performers=(0,),payload=struct.pack('>i',10025))
        for town in (1009,20010):
            s=self.session(town);answer,interact,store=self.call(s,event,17)
            interact.assert_called_once_with(store,10025,'owned-model-session:town-npc-talk:1001:17')
            self.assertEqual([e.kind for e in answer],[0xfe])

    def test_wrong_place_saved_owner_phase_sequence_and_npc_never_forward(self):
        event=Event(0x202,kind=0xfd,performers=(0,),payload=struct.pack('>i',10025))
        for change in ('town','saved','phase','sequence','performers','npc'):
            s=self.session(20010);e=event;seq=17
            if change=='town':s.active_map=20000
            if change=='saved':s.account.get_location=lambda:{'map':20000}
            if change=='phase':s.phase='dungeon_active'
            if change=='sequence':seq=0
            if change=='performers':e=replace(e,performers=())
            if change=='npc':e=replace(e,payload=struct.pack('>i',10026))
            answer,interact,_=self.call(s,e,seq);interact.assert_not_called()
            if change=='npc':self.assertIsNone(answer)
            else:self.assertEqual(struct.unpack_from('>i',answer[0].payload)[0],187)

if __name__=='__main__':unittest.main()
