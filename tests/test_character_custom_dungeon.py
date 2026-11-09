"""Dungeon-side permanent customisation: Apply, persistence, cold replay.

Scope
-----
This pins the *server* contract only. Inside a dungeon the 0x4CB Apply is
admitted, the row is written and read back, the saved selection reaches the
dungeon member DTO's only variable-length slot, and the same selection survives
a dungeon exit and a re-login with the same 0x18E the login path replays.

It cannot cover rendering. Evidence collected 2026-11-08 (see
docs/repairs/dungeon-custom-20261108.md) shows every frame below is already on
the wire while the client still paints career defaults on the dungeon actor, so
a green run here means "the server said everything it can say", nothing more.
"""
import sqlite3, struct, sys, tempfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.domain import character_custom as custom
from els_server.storage import character_custom as store
from els_server.protocol.dungeon_messages import member
from els_server.protocol import character_custom_messages as wire
from els_server.protocol.character_custom_messages import selection_map
from els_server.protocol.protocol_codec import Event
from els_server.domain.character_rules import default_slots

OWNER = 1001
BOOK = 450000            # 无聊的艾索德 -> wait motion, family 1
CUT_IN = None            # filled from the catalog below, family 3


def apply_event(slot, custom_id, sequence):
    return Event(0x202, performers=(0,), kind=0x4cb,
                 payload=selection_map({slot: custom.canonical(custom_id)})), sequence


def result_of(events):
    assert events, events
    # An Apply now re-registers the landing row first (that row's own
    # CUSTOMIZING_TYPE), so the 4CC ack is no longer the first event.
    assert events[0].kind == 0x4cd, events[0]
    ack = next(event for event in events if event.kind == 0x4cc)
    return struct.unpack_from('>i', ack.payload)[0]


def volume(values):
    """The exact `set<int>` body the dungeon DTO carries for this selection."""
    ordered = tuple(sorted({int(v) for v in values if int(v) > 0}))
    return struct.pack('>I', len(ordered)) + b''.join(struct.pack('>i', v) for v in ordered)


with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / 'custom.sqlite3'
    account = LocalAccount(LocalState(path))
    account.enable_characters()
    account.get_inventory_snapshot()
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('UPDATE characters SET unit_class=152,level=99 WHERE uid=?', (OWNER,))
    with closing(sqlite3.connect(path)) as db, db:
        items = grant_items(db, [dict(template=BOOK, metadata=VERIFIED_TEMPLATES[BOOK],
                                      group=TEMPLATE_BAG_GROUPS[BOOK], quantity=1)])
    book = next(i for i in items if i['template'] == BOOK)
    CUT_IN = next(r for r in custom.catalog().values()
                  if r['type'] == 3 and not r.get('native_only'))

    def snap():
        with closing(sqlite3.connect(path)) as db:
            return store.snapshot(db, OWNER)

    def session(phase):
        return SimpleNamespace(client_build='dx11_260923', item_test=True, role='game',
                               phase=phase, shop_session_id='dungeon-custom-test',
                               account=SimpleNamespace(characters=account.characters,
                                                       character=lambda: dict(uid=OWNER, title=0),
                                                       store=SimpleNamespace(path=path, uid=OWNER),
                                                       uid=OWNER, account_id=account.account_id))

    def book_payload(uid, template):
        rule = custom.catalog()[template]
        return struct.pack('>QQiiIB', uid, rule['custom_id'], rule['type'], 0, 0, 0)

    with patch('els_server.domain.dungeon_equipment_loot_flow.current_lease', lambda s: True), \
         patch('els_server.domain.avatar_set_flow.context', lambda s: object()), \
         patch('els_server.domain.avatar_set_flow.validate', lambda s, c: None):

        dungeon = session('dungeon_active')

        # 1) A book used inside a dungeon registers: 0x219 is no longer gated to
        #    town_only. Before the fix admitted() demanded phase=='town_ready'
        #    and the client renders nothing for result -1.
        receipt = store.use_book(path, OWNER, account.account_id,
                                 book_payload(book['uid'], BOOK), 'dungeon-book-1')
        assert receipt is not None and [e.kind for e in receipt['events']] == [0x21a, 0x4cd], receipt

        # 2) Apply inside the dungeon is admitted and lands on the same row a
        #    town Apply would have written.
        event, sequence = apply_event(1, custom.catalog()[BOOK]['custom_id'], 401)
        events = custom.handle(dungeon, event, sequence)
        assert result_of(events) == 0, events
        # The landing row is re-registered first, then the ack. The 0x18E actor
        # notice that used to follow is suppressed by default: the client's
        # reader (FUN_140c4e700) misaligns from byte 0 of our shape and then
        # hands the half-built default object to the actor, resetting the
        # appearance it was supposed to carry. See step 10 for the switch.
        assert [e.kind for e in events] == [0x4cd, 0x4cc], events
        assert snap()['selected'][1] == custom.canonical(custom.catalog()[BOOK]['custom_id'])

        # 3) A native-only cut-in slot behaves identically in a dungeon.
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('INSERT OR IGNORE INTO character_custom_permanent VALUES (?,?,?)',
                       (OWNER, CUT_IN['custom_id'], CUT_IN['book']))
        event, sequence = apply_event(CUT_IN['slot'], CUT_IN['custom_id'], 402)
        assert result_of(custom.handle(dungeon, event, sequence)) == 0
        selected = snap()['selected']
        assert selected[CUT_IN['slot']] == custom.canonical(CUT_IN['custom_id']), selected

        # 4) The saved selection reaches the dungeon actor DTO. `member` uses
        #    one variable-length slot for it; everything else is fixed width, so
        #    the frame may only grow by the set body.
        character = dict(uid=OWNER, account_id=account.account_id, title=0, unit_type=1,
                         unit_class=152, level=99, name='DungeonCustom',
                         transcendence=False, master=False)
        values = tuple(entry['custom_id'] for entry in selected.values())
        plain = member(default_slots(character), character, [])
        filled = member(default_slots(character), character, [], custom=values)
        body = volume(values)
        assert len(filled) - len(plain) == len(body) - 4, (len(filled), len(plain), len(body))
        assert filled.count(body) == 1, 'the custom set must appear exactly once'
        # Order and duplication in the caller must not change the frame.
        assert member(default_slots(character), character, [], custom=tuple(reversed(values)) * 2) == filled

        # 5) Leaving the dungeon changes nothing: the same snapshot is what the
        #    town session reads, so 回城保持 needs no re-apply.
        town = session('town_ready')
        assert snap()['selected'] == selected
        # ...and a town Apply appends to the same table, not to a parallel one.
        event, sequence = apply_event(11, custom.catalog()[BOOK]['custom_id'], 403)
        assert result_of(custom.handle(town, event, sequence)) == 0
        assert snap()['selected'][11] == custom.canonical(custom.catalog()[BOOK]['custom_id'])

        # 6) A cold login replays nothing while the notice is suppressed. This
        #    used to be one 0x18E carrying every selected slot; the frame cannot
        #    be parsed by this build, so the restore path now yields no events
        #    at all rather than an unreadable one.
        after_town = snap()['selected']
        assert custom.restored(dict(uid=OWNER, title=0, character_custom=snap())) == ()

        # 7) Re-applying the same slot is idempotent, not a second write.
        event, sequence = apply_event(1, custom.catalog()[BOOK]['custom_id'], 401)
        assert result_of(custom.handle(dungeon, event, sequence)) == 0
        assert snap()['selected'] == after_town

        # 8) The opener registers every selected row BEFORE the 635 that creates
        #    the window and pushes the 4CC state after it. A window built from an
        #    empty registry paints the career default on every row, which is
        #    exactly what both 20261108 town screenshots showed.
        opener = custom.handle(dungeon, Event(0x202, performers=(0,), kind=0x634, payload=b''), 410)
        kinds = [e.kind for e in opener]
        rows = len(after_town)
        assert kinds[:rows] == [0x4cd] * rows, kinds
        assert kinds[rows] == 0x635, kinds
        assert kinds[rows + 1:] == [0x4cc], kinds

        # 9) The entry burst itself lives in character_custom.dungeon_entry so it
        #    stays hot-reloadable (LocalSession's class cannot be). Pin its shape:
        #    DTO values, the pre-start burst, and the post-start empty->full pair.
        values, before, after, note = custom.dungeon_entry(dungeon)
        assert note == 'ok', note
        assert values == tuple(entry['custom_id'] for entry in after_town.values()), values
        assert [e.kind for e in before] == [0x4cd] * len(after_town) + [0x4cc], before
        # Every 4CD buckets its row by that row's own CUSTOMIZING_TYPE, which in
        # this build equals the slot number (CT_SKILL_CUTIN_SECOND=4,
        # CT_WAIT_MOTION3=11, CT_EMOTICON4=27). Sending the collapsed family
        # filed rows 2..4 of each multi-slot tab under row 1 and the window
        # painted them as the career default -- single-slot tabs such as the
        # skill frame were the only ones that resolved.
        rows = sorted(after_town)
        assert [e.payload[4] for e in before[:len(rows)]] == rows, [(s, e.payload[4]) for s, e in zip(rows, before)]
        # The whole post-DTO burst was the empty->full 0x18E pair, so it is empty
        # while the notice is suppressed: dungeon_entry must not return two
        # unreadable frames that the writer would then put on the wire.
        assert after == (), after

        # 10) ELS_ENABLE_18E_NOTICE=1 restores every suppressed frame verbatim.
        #     This is the switch kept for a byte-level capture comparison against
        #     a real server, so the shapes are pinned under it rather than
        #     deleted from the suite.
        with patch.object(wire, '_ENABLE_18E_NOTICE', True):
            notices = custom.restored(dict(uid=OWNER, title=0, character_custom=snap()))
            assert len(notices) == 1 and notices[0].kind == 0x18e, notices
            assert int.from_bytes(notices[0].payload[:8], 'big') == OWNER
            # 18E groups by custom FAMILY and carries one Info per rank of it, so
            # the entry count is the number of distinct families.
            families = {custom.selection_type(slot) for slot in after_town}
            assert int.from_bytes(notices[0].payload[16:20], 'big') == len(families), notices[0]
            for slot in after_town:
                family = custom.selection_type(slot)
                ranks = sorted(s for s, owner in custom.SLOT_TYPES.items() if owner == family)
                assert slot in ranks, (slot, family)
            live_values, live_before, live_after, live_note = custom.dungeon_entry(dungeon)
            assert live_note == 'ok' and live_values == values
            assert [e.kind for e in live_before] == [0x4cd] * len(after_town) + [0x4cc, 0x18e], live_before
            # 18E precedes the 4CC in the DTO burst as well: the client paints
            # each row from the manager's current selection, so a notice after
            # the ack is one frame too late.
            assert [e.kind for e in live_after] == [0x18e, 0x18e], live_after
            assert len(live_after[0].payload) < len(live_after[1].payload), live_after
            # Both frames stay on actor selector 0: the selector-1 experiment of
            # 15:01:26 changed nothing, so the third frame was removed.
            assert live_after[1].payload[8:12] == bytes(4), live_after[1].payload[:12]
            assert live_after[0].payload[8:12] == bytes(4), live_after[0].payload[:12]
            live_opener = custom.handle(dungeon, Event(0x202, performers=(0,), kind=0x634, payload=b''), 411)
            live_kinds = [e.kind for e in live_opener]
            count = len(after_town)
            assert live_kinds[count] == 0x18e, live_kinds
            assert live_kinds[count + 1] == 0x635, live_kinds
            assert live_kinds[count + 2:] == [0x4cc], live_kinds

        # A session without item_test never reaches the store and reports why.
        blind = session('dungeon_active')
        blind.item_test = False
        none = custom.dungeon_entry(blind)
        assert none[:3] == ((), (), ()) and none[3] == 'gate', none

print('character custom dungeon: PASS')
