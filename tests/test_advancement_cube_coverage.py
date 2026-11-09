"""Class-advancement boxes the client consumes as cubes but the server has no table for.

Five templates remain outside the verified finite cube catalog. The available
RandomItem rules identify groups without proving their full current contents and
weights. This change adds no advancement-pool inference, producer or repair of
existing inventory: refusal must leave each owned instance intact.

The four [科宝] career boxes left this list when common-box-opening landed: each
now carries a witnessed per-class pool (300645: 3 entries, 300646: 6) instead of
being refused, so they are asserted as wired below.
"""
import unittest
from els_server.domain.cubes import catalog
from els_server.domain.job_reward_boxes import BOXES as JOB_BOXES, entries as job_entries
from tests import test_npc_sale as fixture
from tests.test_fixed_cubes import payload
from els_server.storage.fixed_cubes import open_cube

# 1/2/3转晋级宝箱、新的力量：原力、[阿莉尔]白境机甲防具宝箱（按职业分支随机）。
ADVANCEMENT_BOXES = (109999, 110850, 135867, 135869, 118655)

# [科宝]1/2/3转、超越转职纪念便利性道具宝箱（单一组随机）：witnessed pools.
WIRED_JOB_BOXES = (300645, 300646, 300647, 300648)


class AdvancementCubeCoverageTests(unittest.TestCase):
 setUp=fixture.SaleTests.setUp;grant=fixture.SaleTests.grant;items=fixture.SaleTests.items;dump=fixture.SaleTests.dump
 def test_unwired_advancement_boxes_are_pinned_as_unknown(self):
  for template in ADVANCEMENT_BOXES:
   self.assertNotIn(template,catalog(),f'{template} needs a witnessed reward pool before it can open')
   with self.assertRaises(ValueError):open_cube(self.path,1001,template,payload(self.grant(template)['uid']),'pin-'+str(template))
   self.assertIn(template,{i['template'] for i in self.items()})
 def test_refusal_does_not_consume_or_grant_anything(self):
  item=self.grant(109999);before=self.dump()
  with self.assertRaises(ValueError):open_cube(self.path,1001,109999,payload(item['uid']),'refuse',lambda n:self.fail('Draw'))
  self.assertEqual(self.dump(),before)
 def test_career_boxes_carry_a_witnessed_per_class_pool(self):
  pools={e['template']:e for e in job_entries()}
  for template in WIRED_JOB_BOXES:
   self.assertIn(template,catalog())
   self.assertIn(template,JOB_BOXES)
   self.assertTrue(pools[template]['entries'],f'{template} must not be an empty pool')


if __name__=='__main__':unittest.main()
