"""Eve's 电击磁场 (SI_SA_EEP_ELECTRONIC_FIELD, template 1622) refused to spawn.

The client really does ask: the local session dump recorded a single-record
0x2CE for template 1622 at 2026-10-28T18:49:34 in dungeon 33252, and the player
trace ``analysis/client-6c6b5180/20261028-184402`` shows the two neighboring
casts in the same second (384 sentry, 1621 surface-cutting) each followed 40 ms
later by ``updated_npc_record_decoded`` + ``updated_npc_actor_created`` for the
key the server handed out, while the 1622 send was followed by nothing at all.
The only thing that stopped it was ``EVE_SUMMON_TEMPLATES``: the gate was
pinned to the 384 family and the 2026-10-27 1621 extension, so an owner-bound,
uniquely decodable request was answered with ``result=-1`` and no 0x2D0.

Admitting it is a finite-source extension, not a shape relaxation - 1622 is
``NPC_UNIT_ID.NUI_SI_SA_EEP_ELECTRONIC_FIELD`` with CLASS_TYPE 0 / IS_NPC true
in the client catalog, and decoding still requires exactly one record, the
``-1`` sentinel key, one of the twenty native layouts, the requester as owner
and a finite position.

女王神侍 (hyper skill 25601, true grade 25604) has no captured 0x2CE yet, so its
admission rests on the client catalog alone: the skill is ``m_eType`` 13 with
``SA_EFFECTIVE_TIME`` 60 and icon piece ``SI_HA_EEP_LINK_OVERCHARGE_ILLUSION``,
and 1454 ``SI_HA_FERDINAND`` is the only CLASS_TYPE 0 actor whose motion is
``Motion_EEP_FERDINAND``. The dungeon boss that reuses the same model, 6384
``EN_TUNNEL_EVENT_FERDINAND``, is CLASS_TYPE 103 and stays refused. The spawn
dump still records the real request, so a wrong guess is visible instead of
silently swallowed.
"""
import struct
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from els_server.domain import dungeon_routes, summons
from els_server.domain.dungeon_npcs import MODE0_FIELDS
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState

ELECTRONIC_FIELD_TEMPLATE = 1622
OWNER_UID = 1004
DUNGEON_IDENTITY = 33252

# Verbatim 0x2CE body from state/launcher/script-spawn-dump.jsonl,
# 2026-10-28T18:49:34 (stage 0, part 0, unit_type 5, 136 bytes).
CAPTURED_REQUEST = bytes.fromhex(
    '000000010101bf800000a80000000000103a466d1875747f5924775b7527102d0a1451'
    '1739cb1d467db890a200821f5b3263c56a9a9c447a0000404de35472f244ec00000000'
    'aa1cb36a3a00000000000000000000000000f0debbe30000000100bf800000001a6f3e'
    '4dac398527bd41af6e29296f8200000000000000010000000000018fd00a74')

# Gate contents before each admission step; patching back proves each entry is
# load-bearing rather than decoration.
PREVIOUS_TEMPLATES = frozenset((384, 385, 386, 1621, 1622, 2091))
BEFORE_ELECTRONIC_FIELD = frozenset((384, 385, 386, 1621, 2091))

# 费尔德南 - the actor Eve's 超技能 女王神侍 (25601, true grade 25604) brings
# through the dimension gate. Pinned from the client catalog, not from a capture.
FERDINAND_TEMPLATE = 1454
FERDINAND_SKILLS = (25601, 25604)


def _dto(payload):
    for fields in summons.LAYOUTS.values():
        try:
            return summons._decode(payload, OWNER_UID, fields)
        except ValueError:
            continue
    raise AssertionError('captured request no longer decodes under any layout')


def wire_key(payload):
    position = 4
    for offset, size, xor, kind in MODE0_FIELDS:
        if offset == 0:
            break
        position += size
    return int.from_bytes(payload[position:position + 4], 'big') ^ 0x8d0dbb13


def sentry_request(owner_uid, template):
    """Encode a native-shaped 0x2CE body through one pinned layout permutation."""
    dto = bytearray(0xa4)
    struct.pack_into('<i', dto, 0, -1)
    struct.pack_into('<i', dto, 4, template)
    dto[8] = 1
    struct.pack_into('<fff', dto, 9, 100.0, 0.0, -50.0)
    struct.pack_into('<q', dto, 0x6d, owner_uid)
    encoded = [struct.pack('>I', 1)]
    for offset, size, xor, kind in summons.LAYOUTS['0']:
        if kind == 'empty':
            encoded.append(struct.pack('>I', 3) + b'abc' if offset is None else bytes(4))
        elif size == 12:
            encoded.append(b''.join(dto[offset + i:offset + i + 4][::-1] for i in (0, 4, 8)))
        else:
            encoded.append((int.from_bytes(dto[offset:offset + size], 'little') ^ xor).to_bytes(size, 'big'))
    return b''.join(encoded)


def eve_session(root, uid):
    """A live dungeon session belonging to a character with the captured uid."""
    created = None
    for index in range(16):
        character = root.characters.create(f'EveSummon{index}', 5, f'create-electronic-field-{index}')
        if character['uid'] == uid:
            created = character
            break
    if created is None:
        raise AssertionError(f'no character reached uid {uid}')
    session = LocalSession(root.for_character(uid), enter_town=True, enter_dungeon=True,
                           client_build='dx11_260923', npc_slot_test=True, gate_test=True,
                           population_test=True)
    session.role = 'game'
    session.phase = 'dungeon_active'
    session.dungeon_substage_synced = True
    run = dungeon_routes.DungeonRun(DUNGEON_IDENTITY, str(uuid.uuid4()))
    session.dungeon_run = run
    session.defeated_npcs = run.defeated
    return session, run


class CapturedElectronicField(unittest.TestCase):
    def test_captured_request_is_the_electronic_field_actor(self):
        dto = _dto(CAPTURED_REQUEST)
        self.assertEqual(struct.unpack_from('<i', dto)[0], -1)
        self.assertEqual(struct.unpack_from('<i', dto, 4)[0], ELECTRONIC_FIELD_TEMPLATE)
        self.assertEqual(struct.unpack_from('<q', dto, 0x6d)[0], OWNER_UID)

    def test_decoder_stays_unique_after_admitting_the_template(self):
        valid = [name for name, fields in summons.LAYOUTS.items()
                 if _safe_decode(CAPTURED_REQUEST, fields) is not None]
        self.assertEqual(valid, ['0'])

    def test_gate_spawns_the_actor(self):
        notice = summons.sentry_spawn(CAPTURED_REQUEST, OWNER_UID, 16)
        self.assertEqual(notice.kind, 0x2d0)
        self.assertEqual(len(notice.payload), 144)
        self.assertEqual(notice.payload[-24:], bytes(24))
        self.assertEqual(struct.unpack_from('>I', notice.payload)[0], 1)
        self.assertEqual(wire_key(notice.payload), 16)

    def test_switch_off_the_admission_restores_the_refusal(self):
        with patch.object(summons, 'EVE_SUMMON_TEMPLATES', BEFORE_ELECTRONIC_FIELD):
            with self.assertRaises(ValueError):
                summons.sentry_spawn(CAPTURED_REQUEST, OWNER_UID, 16)

    def test_other_guards_still_apply_to_the_new_template(self):
        for uid in (OWNER_UID - 1, OWNER_UID + 1):
            with self.assertRaises(ValueError):
                summons.sentry_spawn(CAPTURED_REQUEST, uid, 16)
        with self.assertRaises(ValueError):
            summons.sentry_spawn(struct.pack('>I', 2) + CAPTURED_REQUEST[4:], OWNER_UID, 16)
        with self.assertRaises(ValueError):
            summons.sentry_spawn(CAPTURED_REQUEST + b'\0', OWNER_UID, 16)
        with self.assertRaises(ValueError):
            summons.sentry_spawn(CAPTURED_REQUEST, OWNER_UID, 15)


class CastPathReachesTheClient(unittest.TestCase):
    def test_the_cast_answers_with_ack_and_spawn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = LocalAccount(LocalState(Path(tmp) / 'save.db'))
            root.enable_characters()
            session, run = eve_session(root, OWNER_UID)
            reply = session.handle(Event(0x202, kind=0x2ce, payload=CAPTURED_REQUEST), 50)
            self.assertEqual([event.kind for event in reply], [0x2cf, 0x2d0])
            self.assertEqual(reply[0].payload, struct.pack('>i', 0))
            key = wire_key(reply[1].payload)
            self.assertGreaterEqual(key, 16)
            self.assertEqual(session.summon_keys, {key})
            # The stage-persistence fix keeps the request, so 电击磁场 also
            # survives entering the next map instead of dying early.
            self.assertEqual(run.summon_payloads, {key: CAPTURED_REQUEST})


class FiniteSourceGate(unittest.TestCase):
    """Every admitted template must be a client-catalog NPC, not a shape."""

    def test_admitted_templates_are_pinned_npc_entries(self):
        catalog = client_data()
        for template in summons.EVE_SUMMON_TEMPLATES:
            entry = catalog.npc(template)
            self.assertEqual(entry['class_id'], 0, entry['script'])
            self.assertTrue(entry['is_npc'], entry['script'])
        self.assertEqual(catalog.npc(ELECTRONIC_FIELD_TEMPLATE)['script'],
                         'SI_SA_EEP_ELECTRONIC_FIELD.lua')

    def test_ferdinand_is_pinned_to_eves_hyper_skill_family(self):
        catalog = client_data()
        entry = catalog.npc(FERDINAND_TEMPLATE)
        self.assertEqual(entry['script'], 'SI_HA_FERDINAND.lua')
        self.assertEqual(entry['variants'][0]['MOTION'], 'Motion_EEP_FERDINAND.x')
        for skill in FERDINAND_SKILLS:
            definition = catalog.skill(skill)
            self.assertEqual(definition['m_eType'], 13, skill)
            self.assertEqual(definition['m_bBornSealed'], 1, skill)
            self.assertTrue(str(definition['m_wstrIconTexturePieceName']).startswith('SI_HA_EEP_'), skill)
            timed = [value['m_Value']['1'] for key, value in definition.items()
                     if key.startswith('NUMERICAL_DATA') and isinstance(value, dict)
                     and value.get('m_wstrName') == 'SA_EFFECTIVE_TIME']
            self.assertEqual(timed, [60], skill)

    def test_ferdinand_cast_spawns_the_actor(self):
        request = sentry_request(OWNER_UID, FERDINAND_TEMPLATE)
        notice = summons.sentry_spawn(request, OWNER_UID, 16)
        self.assertEqual(notice.kind, 0x2d0)
        self.assertEqual(len(notice.payload), 144)
        with tempfile.TemporaryDirectory() as tmp:
            root = LocalAccount(LocalState(Path(tmp) / 'save.db'))
            root.enable_characters()
            session, _run = eve_session(root, OWNER_UID)
            reply = session.handle(Event(0x202, kind=0x2ce, payload=request), 51)
            self.assertEqual([event.kind for event in reply], [0x2cf, 0x2d0])
            self.assertEqual(reply[0].payload, struct.pack('>i', 0))

    def test_switch_off_the_admission_refuses_ferdinand_again(self):
        self.assertEqual(set(summons.EVE_SUMMON_TEMPLATES) - PREVIOUS_TEMPLATES, {FERDINAND_TEMPLATE})
        request = sentry_request(OWNER_UID, FERDINAND_TEMPLATE)
        with patch.object(summons, 'EVE_SUMMON_TEMPLATES', PREVIOUS_TEMPLATES):
            with self.assertRaises(ValueError):
                summons.sentry_spawn(request, OWNER_UID, 16)

    def test_unpinned_template_stays_refused(self):
        for template in (1604, 200, 519):
            self.assertNotIn(template, summons.EVE_SUMMON_TEMPLATES)
            with self.assertRaises(ValueError):
                summons.sentry_spawn(sentry_request(OWNER_UID, template), OWNER_UID, 16)

    def test_non_npc_ferdinand_variant_is_not_a_summon(self):
        entry = client_data().npc(6384)
        self.assertEqual(entry['script'], 'EN_TUNNEL_EVENT_FERDINAND.lua')
        self.assertNotEqual(entry['class_id'], 0)
        self.assertNotIn(6384, summons.EVE_SUMMON_TEMPLATES)
        # The hostile boss reuses the very same model, so the motion name alone
        # cannot tell a summon from a monster; CLASS_TYPE is what discriminates.
        self.assertEqual(entry['variants'][0]['MOTION'], 'Motion_EEP_FERDINAND.x')
        with self.assertRaises(ValueError):
            summons.sentry_spawn(sentry_request(OWNER_UID, 6384), OWNER_UID, 16)


def _safe_decode(payload, fields):
    try:
        return summons._decode(payload, OWNER_UID, fields)
    except ValueError:
        return None


if __name__ == '__main__':
    unittest.main(verbosity=2)
