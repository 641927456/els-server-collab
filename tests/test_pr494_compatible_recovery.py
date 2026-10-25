"""Code-first recovery stops new producers and retains already saved readers."""
from pathlib import Path
from contextlib import closing
import sqlite3,struct,unittest
from unittest.mock import patch
from tests import test_regional_boss_cubes_legacy as fixture
from els_server.domain import regional_boss_cubes_legacy as legacy
from els_server.storage import known_resurrection
from els_server.storage.inventory_state import load_items


class CompatibleRecovery(unittest.TestCase):
    setUp=fixture.LegacyRegionalCubeTests.setUp
    grant=fixture.LegacyRegionalCubeTests.grant
    items=fixture.LegacyRegionalCubeTests.items
    dump=fixture.LegacyRegionalCubeTests.dump

    def test_closed_legacy_producer_keeps_previously_granted_item_reader(self):
        row=legacy.catalog()[130159]
        box=self.grant(130159)
        fixture.open_cube(self.path,1001,130159,fixture.payload(box['uid']),'before-recovery',lambda n:0)
        output=row['entries'][0]['template']
        saved=next(i for i in self.items()if i['template']==output)
        second=self.grant(130159)
        before=self.dump()
        with patch.object(legacy,'BUSINESS_ENABLED',False):
            self.assertEqual(legacy.catalog(),{})
            # The frozen finite definitions and the existing inventory reader remain.
            self.assertEqual(len(legacy.data()['definitions']),10)
            with self.assertRaises(ValueError):
                fixture.open_cube(self.path,1001,130159,fixture.payload(second['uid']),'closed-producer')
            with closing(sqlite3.connect(self.path))as db:
                self.assertIn(saved,load_items(db,1001))
            self.assertEqual(self.dump(),before)

    def test_original_known_counter_reader_survives_option_one_recovery(self):
        box=self.grant(190556)
        request=struct.pack('>QBBBIi',box['uid'],0,0,0,0,1)
        known_resurrection.open_box(self.path,1001,request,'new-native-confirm',account_id=1,guard=lambda:None)
        self.assertEqual(known_resurrection.snapshot(self.path,1001),10)
        source=Path(known_resurrection.__file__).read_text('utf8')
        old="if request.option not in (0,1) or request.choices"
        self.assertEqual(source.count(old),1)
        source=source.replace(old,"if request.option or request.choices")
        recovered={'__name__':'pr494_known_counter_compatible_recovery'}
        exec(compile(source,'<exact-known-option-recovery>','exec'),recovered)
        before=self.dump()
        with self.assertRaises(ValueError):
            recovered['open_box'](self.path,1001,request,'stopped-native-confirm',account_id=1,guard=lambda:None)
        self.assertEqual(recovered['snapshot'](self.path,1001),10)
        self.assertEqual(self.dump(),before)


if __name__=='__main__':unittest.main()
