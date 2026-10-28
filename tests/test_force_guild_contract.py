"""Negative contracts for complete parent retention and honest candidate status."""
from contextlib import redirect_stdout
import copy
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from tools import verify_force_guild_flow_20261029 as checker


class ForceGuildContractTests(unittest.TestCase):
    def check_counterfactual(self,change):
        original=checker.read
        def changed(path):
            value=original(path)
            if Path(path).name=='native-force-guild-flow-20261029-v1.json':
                value=copy.deepcopy(value);change(value)
            return value
        with patch.object(checker,'read',side_effect=changed),redirect_stdout(io.StringIO()):
            with self.assertRaises(AssertionError):checker.verify()

    def test_complete_declared_candidate_passes(self):
        with redirect_stdout(io.StringIO()):checker.verify()

    def test_deleting_unchanged_parent_module_is_rejected(self):
        def remove(value):
            rows=value['channels']['online']['files']
            victim=next(row for row in rows if row['path']=='els_server/domain/acquisition_policy.py')
            rows.remove(victim)
        self.check_counterfactual(remove)

    def test_changed_unrelated_parent_is_rejected(self):
        def alter(value):
            row=next(row for row in value['channels']['local']['files']
                     if row['path']=='els_server/domain/acquisition_policy.py')
            row['sha256']='0'*64
        self.check_counterfactual(alter)

    def test_inherited_delivery_success_is_rejected(self):
        def mark(value):
            value['candidate']=False
            value['actual_dual_delivery_verified']=True
        self.check_counterfactual(mark)


if __name__=='__main__':unittest.main()
