"""Portable selected-source predicate contracts; actual runtime replay is separate.

Fixtures project static source graphs only. No player state, runtime pack, game,
SQL, or installed-machine paths are needed. The old callback is a negative control.
"""
from pathlib import Path
import ast,copy,hashlib,json,os,sys,types,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT=Path(os.environ.get('ELS_PR597_TEST_REPOSITORY',Path(__file__).resolve().parents[1]))
F=Path(__file__).resolve().parents[1]/'references/pr597-door-regression-20261028-v1'


def read(path):return json.loads(path.read_bytes())


def predicate(raw):
    klass=next(n for n in ast.parse(raw).body if isinstance(n,ast.ClassDef)and n.name=='DungeonRun')
    method=next(n for n in klass.body if isinstance(n,ast.FunctionDef)and n.name=='condition_ready')
    ns={};exec(compile(ast.Module(body=[method],type_ignores=[]),'selected-source-condition_ready','exec'),ns)
    return ns['condition_ready']


def state(row):
    graph={'source_sha256':row['source_sha256'],'projected_source_identity':row['identity']}
    npcs=copy.deepcopy(row['npcs'])
    return NS(identity=row['identity'],stage=row['stage'],part=row['part'],encounter=None,
              graph=copy.deepcopy(graph),catalog=NS(graph=lambda identity:copy.deepcopy(graph)),
              current={'npcs':npcs,'conditions':[copy.deepcopy(row['condition'])]},
              defeated={n['key']:b'hostile-retired'for n in npcs if n['active']and n.get('team',1)!=0})


class PR597DoorRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=read(F/'source-projected-gates.json')
        cls.legacy=read(F/'legacy-negative-control.json')
        rejected=read(F/'rejected/manifest.json')
        if rejected['runtime_selected']or rejected['source_head']!=cls.legacy['old_PR597_head']:
            raise AssertionError('Rejected-source identity or scope')
        for name,row in rejected['files'].items():
            raw=(F/'rejected'/name).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['sha256']or len(raw)!=row['size']:
                raise AssertionError('Rejected negative-control bytes changed')
        old_text=(F/'rejected/dungeon_routes.py').read_bytes().decode('utf8')
        old_class=next(n for n in ast.parse(old_text).body if isinstance(n,ast.ClassDef)and n.name=='DungeonRun')
        old_method=next(n for n in old_class.body if isinstance(n,ast.FunctionDef)and n.name=='condition_ready')
        if ast.get_source_segment(old_text,old_method)!=cls.legacy['condition_source']:
            raise AssertionError('Negative callback differs from frozen PR597 source')
        helper_text=(F/'rejected/local_dungeon_flow.py').read_bytes().decode('utf8')
        helper_source='\n\n'.join(ast.get_source_segment(helper_text,n)for n in ast.parse(helper_text).body
                               if isinstance(n,ast.FunctionDef)and n.name in {'script_door','_room_clear','script_gate','key_code_gate'})
        if helper_source!=cls.legacy['helper_function_source']:
            raise AssertionError('Negative helper differs from frozen PR597 source')
        if read(F/'rejected/local_dungeon_flow.json')['script_gate_relaxation']is not cls.legacy['script_gate_relaxation']:
            raise AssertionError('Negative control switch differs from frozen config')
        selected=read(ROOT/'channels/current-engine.json');profile=read(ROOT/selected['profile'])
        cls.callbacks={}
        for ch in ('online','local'):
            row=next(r for r in profile['channels'][ch]['files']if r['path']=='els_server/domain/dungeon_routes.py')
            raw=(ROOT/row['source']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['sha256']or len(raw)!=row['size']:
                raise AssertionError('Selected dungeon route source bytes differ from manifest')
            cls.callbacks[ch]=predicate(raw)
        ns={};exec(compile(cls.legacy['condition_source'],'PR597-original-condition_ready','exec'),ns)
        cls.old_callback=staticmethod(ns['condition_ready'])

    def fixed(self,identity):return [r for r in self.fixture['fixed']if r['identity']==identity]

    def test_original_PR597_reproduces_three_early_raid_openings(self):
        helper=types.ModuleType('els_server.domain.local_dungeon_flow')
        helper.script_gate_relaxation=lambda:self.legacy['script_gate_relaxation']
        exec(compile(self.legacy['helper_function_source'],'PR597-original-door-helpers','exec'),helper.__dict__)
        rows=self.fixed(34140);self.assertEqual(len(rows),3)
        with patch.dict(sys.modules,{helper.__name__:helper}):
            for row in rows:
                run=state(row);condition=run.current['conditions'][0]
                self.assertTrue(self.old_callback(run,condition))
                for ch,callback in self.callbacks.items():
                    with self.subTest(channel=ch,stage=row['stage']):self.assertFalse(callback(run,condition))

    def test_each_raid_controller_retirement_changes_reject_to_accept(self):
        for ch,callback in self.callbacks.items():
            for row in self.fixed(34140):
                with self.subTest(channel=ch,stage=row['stage']):
                    run=state(row);condition=run.current['conditions'][0]
                    self.assertEqual(condition['required'],[6851+2*row['stage']])
                    self.assertFalse(callback(run,condition))
                    for n in run.current['npcs']:
                        if n['template']in condition['required']:run.defeated[n['key']]=b'controller-retired'
                    self.assertTrue(callback(run,condition));self.assertTrue(callback(run,condition))

    def test_missing_or_partially_retired_controller_rejects(self):
        for ch,callback in self.callbacks.items():
            for row in self.fixed(34140):
                with self.subTest(channel=ch,stage=row['stage']):
                    run=state(row);condition=run.current['conditions'][0]
                    run.current['npcs'][:]=[n for n in run.current['npcs']if n['template']not in condition['required']]
                    self.assertFalse(callback(run,condition))
                    run=state(row);condition=run.current['conditions'][0]
                    first=next(n for n in run.current['npcs']if n['template']in condition['required'])
                    second=dict(first,key=max(n['key']for n in run.current['npcs'])+1)
                    run.current['npcs'].append(second);run.defeated[first['key']]=b'first-retired'
                    self.assertFalse(callback(run,condition))
                    run.defeated[second['key']]=b'second-retired';self.assertTrue(callback(run,condition))

    def test_existing_30282_and_30182_exact_doors_remain_usable(self):
        for identity,kind,required in ((30282,1,[1]),(30182,3,[145])):
            rows=self.fixed(identity);self.assertEqual(len(rows),2)
            for ch,callback in self.callbacks.items():
                for row in rows:
                    with self.subTest(channel=ch,identity=identity,stage=row['stage']):
                        run=state(row);c=run.current['conditions'][0]
                        self.assertEqual((c['kind'],c['required']),(kind,required))
                        self.assertTrue(callback(run,c))
                        live=next(n['key']for n in run.current['npcs']if n['active']and n.get('team',1)!=0)
                        del run.defeated[live];self.assertFalse(callback(run,c))

    def test_changed_graph_door_shape_or_map_cannot_reuse_exception(self):
        for identity in (30282,30182):
            for ch,callback in self.callbacks.items():
                for row in self.fixed(identity):
                    with self.subTest(channel=ch,identity=identity,stage=row['stage']):
                        run=state(row);run.graph['source_sha256']='0'*64
                        self.assertFalse(callback(run,run.current['conditions'][0]))
                        run=state(row);run.identity=999999
                        self.assertFalse(callback(run,run.current['conditions'][0]))
                        for field,value in (('active',True),('no_drop',False),('ally',True),('team',0)):
                            run=state(row);c=run.current['conditions'][0]
                            gate=next(n for n in run.current['npcs']if(n['key_code']==1 if identity==30282 else n['template']==145))
                            gate[field]=value
                            self.assertFalse(callback(run,c),(field,value))

    def test_every_other_source_kind1_and_kind3_keeps_original_predicate(self):
        rows=self.fixture['other_conditions'];self.assertEqual(len(rows),513)
        for ch,callback in self.callbacks.items():
            for row in rows:
                run=state(row);c=run.current['conditions'][0];npcs=run.current['npcs']
                keys=[n['key']for n in npcs if(n['key_code']in c['required']if c['kind']==1 else n['template']in c['required'])]
                self.assertEqual(callback(run,c),bool(keys)and all(k in run.defeated for k in keys),(ch,row['identity'],row['stage'],row['part'],c))
                run.defeated={};self.assertFalse(callback(run,c),(ch,row['identity'],row['stage'],row['part']))


if __name__=='__main__':unittest.main()
