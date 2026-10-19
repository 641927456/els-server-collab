"""The reusable experimental encoder matches the original parsed candidate."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dungeon_drops import potion_drop_notice
candidate = json.loads((ROOT / 'analysis/client-6c6b5180/20261013-225304/private-drop-list-candidate.json').read_text(encoding='utf8'))
packet = potion_drop_notice(910001, (200.0, 0.0, 0.0))
assert packet.event_id == 0x201 and packet.kind == 0xcf and len(packet.payload) == 54
assert packet.payload.hex() == candidate['wire_hex']
for drop_id, xyz, tail in ((0, (0,0,0), (0,0,0)), (True, (0,0,0), (0,0,0)), (2**31, (0,0,0), (0,0,0)), (1, (float('nan'),0,0), (0,0,0)), (1, (0,0), (0,0,0)), (1, (0,0,0), (0,0,2**31))):
    try:
        potion_drop_notice(drop_id, xyz, tail)
    except ValueError:
        continue
    raise AssertionError('Invalid experimental drop accepted')
print('PASS: CF encoder matches native parsed wire; invalid identities/positions/context rejected.')
