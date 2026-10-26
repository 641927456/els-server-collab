"""Finite source guards and native wire/authority separation without runtime assets."""
import copy,json,struct,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from els_server.domain import native_hero_inputs as hero,raid_npc_stats as stats


class NativeHeroInputsTests(unittest.TestCase):
    def setUp(self):
        self.p=hero.policy()
        self.catalog=SimpleNamespace(_data={
            'routes':{'120000':{'source':self.p['source']}},
            'graphs':{self.p['source']:{'source_sha256':self.p['graph_sha256']}}})
        self.data=SimpleNamespace(dungeon=lambda identity:{'difficulty':1,'m_NPCLevel':87})

    def source(self,key):
        stage,part,group,index,template=map(int,key.split(':'))
        context=(120000,self.p['graph_sha256'],87,stage,part,group,index)
        return template,context

    def test_all_mode_sources_and_unlisted_controller(self):
        self.assertEqual(len(self.p['mode_sources']),58)
        self.assertEqual(len(self.p['sources']),8)
        for key,row in self.p['mode_sources'].items():
            template,ctx=self.source(key)
            native=SimpleNamespace(dungeon=self.data.dungeon,npc=lambda identity:row)
            # A non-integral float catches pre-rounding and double scaling.
            base=struct.unpack('<f',struct.pack('<f',106107.3046875))[0]
            expected=struct.unpack('<f',struct.pack('<f',base*10))[0]
            with patch.object(hero,'client_data',return_value=native):
                self.assertEqual(hero.source_maximum(self.catalog,template,base,ctx),(expected,True))
                self.assertEqual(hero.source_maximum(self.catalog,template,base,(*ctx[:6],99999)),(base,False))
                for bad in ((120000,'0'*64,*ctx[2:]),(*ctx[:2],88,*ctx[3:])):
                    with self.assertRaises(ValueError):hero.source_maximum(self.catalog,template,base,bad)
                wrong=copy.deepcopy(row);wrong['script']='wrong.lua'
                native.npc=lambda identity:wrong
                with self.assertRaises(ValueError):hero.source_maximum(self.catalog,template,base,ctx)
        self.assertEqual(hero.source_maximum(None,1,123,(30000,'unused',1,0,0,-1,0)),(123,False))

    def test_metadata_instance_identity_and_empty_compatibility(self):
        self.assertEqual(hero.ability_metadata([]),bytes(29))
        wire=hero.ability_metadata([2,4,6])
        self.assertEqual(len(wire),29+3*8)
        self.assertEqual(struct.unpack_from('>I',wire)[0],3)
        self.assertEqual([struct.unpack_from('>i4b',wire,4+8*i) for i in range(3)],
                         [(2,0,0,0,0),(4,0,0,0,0),(6,0,0,0,0)])
        self.assertEqual(wire[-25:],bytes(25))
        for keys in ([1,1],[-1],[16384],[True]):
            with self.assertRaises(ValueError):hero.ability_metadata(keys)

    def test_factor_and_room_scope(self):
        with patch.object(hero,'client_data',return_value=self.data):
            self.assertEqual(hero.difficulty(120000),1)
            self.assertEqual(struct.unpack('>I10f',hero.factor_vector(120000)),
                             (1,*tuple(struct.unpack('>10f',struct.pack('>10f',.4,.5,.4,.4,12,2,10,2.5,75,5.3)))))
            self.data.dungeon=lambda identity:{'difficulty':2,'m_NPCLevel':87}
            with self.assertRaises(ValueError):hero.factor_vector(120000)
        for identity in (30000,33881,120010):
            self.assertEqual(hero.factor_vector(identity),bytes(4))
            self.assertEqual(hero.difficulty(identity),0)

    def test_628_raw_inputs_preserve_other_81_bytes_and_reject_stale_context(self):
        provenance=json.loads((ROOT/'docs/client-first-monster-inputs-20261026.json').read_bytes())
        all_maps=stats.policy()['maps'];count=0
        for mid in provenance['new_maps']:
            m=all_maps[mid]
            catalog=SimpleNamespace(_data={'routes':{mid:{'source':m['source']}},
                'graphs':{m['source']:{'source_sha256':m['graph_sha256']}}})
            for key,row in m['sources'].items():
                stage,part,group,index,template=map(int,key.split(':'))
                ctx=(int(mid),m['graph_sha256'],m['npc_level'],stage,part,group,index)
                before=bytes((i*13+7)%256 for i in range(97))
                attrs=bytearray(before)
                with patch('els_server.game_data.client_data',return_value=SimpleNamespace(npc=lambda identity:row)):
                    self.assertTrue(stats.apply(catalog,template,attrs,ctx))
                    self.assertEqual(attrs[8:24],struct.pack('<4f',*row['values']))
                    self.assertEqual(attrs[:8]+attrs[24:],before[:8]+before[24:])
                    for bad in ((*ctx[:2],ctx[2]+1,*ctx[3:]),(ctx[0],'0'*64,*ctx[2:])):
                        check=bytearray(before)
                        with self.assertRaises(ValueError):stats.apply(catalog,template,check,bad)
                        self.assertEqual(check,before)
                    check=bytearray(before)
                    self.assertFalse(stats.apply(catalog,template,check,(*ctx[:6],99999)))
                    self.assertEqual(check,before)
                count+=1
        self.assertEqual(count,628)


if __name__=='__main__':unittest.main()
