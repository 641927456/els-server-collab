from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent/'runtime'))
from els_server.domain.item_expiration import require_current,expired
from els_server.domain.boosting_2026_item_policy import deadline,item_deadline
class ExpiryProjection(unittest.TestCase):
    def test_existing_deadline_only_projection(self):
        require_current(dict(expires_at=2000000000),now=1999999999)
        self.assertFalse(expired(dict(expires_at=2000000000),now=2000000000))
        with self.assertRaisesRegex(ValueError,'Item has expired'):
            require_current(dict(expires_at=2000000000),now=2000000001)
    def test_event_template_still_caps_only_event_items(self):
        end=deadline()
        self.assertEqual(item_deadline(dict(template=723619)),end)
        self.assertEqual(item_deadline(dict(template=723619,expires_at=end+100)),end)
        self.assertEqual(item_deadline(dict(template=723619,expires_at=end-100)),end-100)
        self.assertEqual(item_deadline(dict(template=720797,expires_at=end+100)),end+100)
if __name__=='__main__':unittest.main(verbosity=2)
