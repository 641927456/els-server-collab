"""Class-advancement boxes the client consumes as cubes but the server has no table for.

Every template here is granted by a class-advancement quest reward and carries a
RandomItem rule (m_UseCondition plus one m_iItemGroupID per class branch), so the
native client always confirms it and sends the cube-use request. The reward pool
for those group ids is not contained in any local resource: the client's
RandomItem.lua maps cube -> group only, catalog.sqlite3 has no item-group rows,
the witnessed official probability disclosures cover the regional BOSS cubes, and
the 2014 package is outside this collaboration copy. The pool stays unknown, so a
cube use must keep refusing and must never invent a reward or burn the instance.
"""
import unittest
from els_server.domain.cubes import catalog
from tests import test_npc_sale as fixture
from tests.test_fixed_cubes import payload
from els_server.storage.fixed_cubes import open_cube

# 1/2/3转晋级宝箱、新的力量：原力、[阿莉尔]白境机甲防具宝箱（按职业分支随机）
# 与 [科宝]1/2/3转、超越转职纪念便利性道具宝箱（单一组随机）。
ADVANCEMENT_BOXES = (109999, 110850, 135867, 135869, 118655, 300645, 300646, 300647, 300648)


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


if __name__=='__main__':unittest.main()
