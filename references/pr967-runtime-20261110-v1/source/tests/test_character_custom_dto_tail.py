"""The selection half of the 2A customization block (`DTO+0x6B9`).

Everything the server used to send for an already-chosen customization was
either the actor notice (0x18E) or the Apply reply (0x4CC). The 定制 window
never read any of them: it is created when the 635 opener arrives, and that
frame is two empty cash-availability vectors, so the only per-character state
the window can see is the login DTO. The DTO's customization block used to go
out with `+0x6B9` empty on every login, so every saved slot painted the career
default even though the row dropdown listed all the owned items.

`+0x6B9` is `map<i32, vector<i32>>` -- read out of the image, not assumed:
0xDA3370 reaches it at 0xDA35AD -> 0xDB6F10 -> 0xDD7C30 (`u32` count, then per
entry an `i32` key followed by 0xDB1B00 = `u32` count + `i32 x count`).
"""
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.domain import character_custom as custom
from els_server.protocol import character_custom_messages as wire
from els_server.protocol.local_messages import player_initialization

WAIT=custom.canonical(11001)      # family 1 (wait motion), slot 1
CUTIN=custom.canonical(11016)     # family 3 (skill cut-in), slot 3
SECOND=custom.canonical(13055)    # family 3, slot 4
FRAME=custom.canonical(8012)      # family 16 (skill frame), slot 16


def expected(entries):
    """`map<i32, vector<i32>>` exactly as 0xDD7C30 / 0xDB1B00 read it."""
    out=struct.pack('>I',len(entries))
    for family,ids in entries:
        out+=struct.pack('>iI',family,len(ids))+b''.join(struct.pack('>i',i) for i in ids)
    return out


def tail(selected,owned=None):
    return wire.dto_tail({'character_custom':{'owned':owned or {},'selected':selected}})


class DtoTail(unittest.TestCase):

    def test_empty_selection_keeps_the_previous_wire(self):
        # The line this replaced was `owned_map(...) + b'\x01' + u32(0)`; an
        # account with no saved selection must serialise to the same bytes.
        self.assertEqual(tail({}),wire.owned_map({})+b'\x01'+struct.pack('>I',0))

    def test_owned_map_is_untouched(self):
        owned={16:[FRAME]}
        self.assertEqual(tail({},owned),wire.owned_map(owned)+b'\x01'+struct.pack('>I',0))

    def test_single_rank_family_keeps_one_id(self):
        self.assertTrue(tail({16:FRAME}).endswith(expected([(16,[8012])])))

    def test_multi_rank_family_is_positional(self):
        # Family 3 owns slots 3/4/5/6, so its vector is four long and slot 3
        # lands at index 0; ranks this save never chose carry a zero id.
        self.assertTrue(tail({3:CUTIN}).endswith(expected([(3,[11016,0,0,0])])))

    def test_two_ranks_of_one_family_are_one_key(self):
        self.assertTrue(tail({3:CUTIN,4:SECOND}).endswith(expected([(3,[11016,13055,0,0])])))

    def test_two_families_are_two_keys(self):
        self.assertTrue(tail({1:WAIT,16:FRAME}).endswith(expected([(1,[11001,0,0,0]),(16,[8012])])))

    def test_player_initialization_carries_the_tail(self):
        character={'account_id':1,'uid':1001,'unit_class':1,'name':'T','level':1,'title':0,
                   'character_custom':{'owned':{},'selected':{16:FRAME}}}
        event=player_initialization(character=character)
        self.assertEqual(event.kind,0x2a)
        record=struct.pack('>I',0)+b'\x00'+struct.pack('>f',0)+b'\x00'
        self.assertTrue(event.payload.endswith(wire.dto_tail(character)+record*3))


if __name__=='__main__':
    unittest.main()
