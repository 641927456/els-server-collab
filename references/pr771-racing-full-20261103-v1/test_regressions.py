"""Existing mount lifecycle cases, with the prior outer-handler fixture fix."""
from pathlib import Path
import importlib.util,sys,unittest
ROOT=Path('G:/els');B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime';G=B/'git'
sys.path.insert(0,str(R))
modules={}
for name in ('test_mount_state','test_mount_flow','test_mount_retry'):
    path=G/'tests'/(name+'.py');spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);modules[name]=m
class CurrentFlow(modules['test_mount_flow'].MountFlowTests):
    def setUp(self):super().setUp();self.session.handle=self.session._handle
def load_tests(loader,tests,pattern):
    suite=unittest.TestSuite()
    for name in loader.getTestCaseNames(modules['test_mount_state'].MountTests):
        if name!='test_rule_replay_matches_native_and_rejects_nan':suite.addTest(modules['test_mount_state'].MountTests(name))
    suite.addTests(loader.loadTestsFromTestCase(CurrentFlow))
    suite.addTests(loader.loadTestsFromTestCase(modules['test_mount_retry'].MountRetryTests))
    return suite
