"""Check the current parent through equip, career, and cold-read paths in a disposable save."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import struct
import sys
from tempfile import TemporaryDirectory

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
BASE = ROOT / 'releases/online' / json.loads((WORK / 'candidate-files.json').read_bytes())['parent']
sys.path.insert(0, str(BASE))

if '--candidate' in sys.argv:
    import els_server.domain
    import els_server.protocol
    import els_server.storage

    for package in (els_server.domain, els_server.protocol, els_server.storage):
        package.__path__.insert(0, str(WORK / 'candidate' / Path(*package.__name__.split('.'))))

from els_server.config import ServerConfig
from els_server.domain.careers import RULES
from els_server.domain.local_session import LocalAccount, LocalSession
from els_server.domain.native_skill_delivery_sources import initialization
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import ensure_inventory, grant_items
from els_server.storage.local_state import LocalState, ensure_local_tables
from els_server.storage.reward_state import ensure_reward_tables


def server_case(path, method='item'):
    with closing(sqlite3.connect(path)) as db, db:
        ensure_local_tables(db)
        ensure_reward_tables(db)
        ensure_inventory(db)
    uid = Characters(path).create('OwnJobProbe', 1, 'own-job-probe')['uid']
    root = LocalAccount(LocalState(path))
    root.enable_characters()
    actor = root.for_character(uid)
    session = LocalSession(actor, **ServerConfig().session_options())
    session.role = 'game'
    session.phase = 'town_ready'
    session.active_map = 20000
    session.ed_catalog_loaded = True

    template = next(t for t, row in RULES.items()
                    if row['kind'] == 'advancement_3' and row['target'] == 79)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('UPDATE characters SET unit_class=66,level=99,transcendence=1 WHERE uid=?', (uid,))
        db.execute('UPDATE reward_balances SET experience=? WHERE uid=?', (client_data().thresholds[98], uid))
        if method == 'item':
            ticket = grant_items(db, [dict(template=template, metadata=client_data().item(template)['metadata'],
                                           group=4, quantity=1)], uid)[0]
        elif method == 'shop':
            db.execute('UPDATE reward_balances SET ed=1000000000 WHERE uid=?', (uid,))

    def handle(kind, payload, sequence):
        return session.handle(Event(0x202, kind=kind, performers=(0,), payload=payload), sequence)

    def equip(index, skill, sequence):
        reply = handle(0x122, struct.pack('>ii', index, skill), sequence)
        return struct.unpack('>5i', next(e.payload for e in reply if e.kind == 0x123))

    old_skills = (21100, 21101, 21102, 21246, 21026)
    new_skills = (21113, 21114, 21115, 21251, 21026)
    for index, skill in enumerate(old_skills):
        assert equip(index, skill, index + 1)[:3] == (0, index, skill)
    assert actor.get_skills()[:5] == old_skills

    if method == 'item':
        kind, ack_kind = 0x219, 0x21a
        payload = struct.pack('>QQiiIB', ticket['uid'], 0, 0, 0, 0, 0)
    elif method == 'shop':
        from els_server.storage.shop_state import _catalog

        sku = next(offer['sku'] for offer in _catalog(1).offers if offer['template'] == template)
        kind, ack_kind = 0x80f, 0x810
        payload = struct.pack('>IIH', 1, sku, 1)
    elif method == 'quest':
        from els_server.domain.job_quests import catalog
        from els_server.domain.seal_quests import quest_catalog, sequence, target
        from els_server.storage import periodic_quest_scope
        from els_server.storage.seal_quests import ensure

        quest = next(q for q in catalog()['quests'].values() if q['Reward'].get('m_eChangeUnitClass') == 79)
        qid = quest['m_iID']
        prerequisites = quest['QuestCondition']['m_vecBeforeQuestID']
        with closing(sqlite3.connect(path)) as db, db:
            ensure(db)
            for pre in sequence(prerequisites):
                periodic_quest_scope.insert_completed(db, uid, pre, 1, '{}')
            objectives = {row['m_iID']: target(row) for row in quest_catalog().objectives(qid)}
            periodic_quest_scope.insert_active(db, uid, qid, 2, 2, json.dumps(objectives))
        kind, ack_kind = 0xf4, 0xf5
        payload = struct.pack('>iiI5B', qid, 0, 0, 0, 0, 1, 1, 0)
    else:
        from els_server.storage.quick_start import ensure as ensure_enrollment
        from els_server.storage.seal_quests import ensure

        with closing(sqlite3.connect(path)) as db, db:
            ensure_enrollment(db)
            ensure(db)
            db.execute('INSERT INTO quick_start_accounts VALUES (?, ?, 1)', (actor.account_id, uid))
            db.execute('INSERT INTO completed_quests VALUES (?, 169603, 1, ?)', (uid, '{}'))
        kind, ack_kind = 0xc56, 0xc57
        payload = struct.pack('>i', 79)
    reply = handle(kind, payload, 20)
    kinds = [e.kind for e in reply]
    assert next(e.payload for e in reply if e.kind == ack_kind)[:4] == bytes(4), kinds
    assert kinds.index(0x29f) < kinds.index(0x131) < kinds.index(0x55b), kinds
    wire = next(e.payload for e in reply if e.kind == 0x55b)
    skills = initialization(wire)
    assert skills.owner == uid and tuple(skill for skill, _ in skills.preset.slots)[:5] == new_skills
    assert not set(old_skills[:4]).intersection(dict(skills.learned))
    assert set(new_skills).issubset(dict(skills.learned))
    restored = [e.payload for e in reply if e.kind == 0x123]
    if '--candidate' in sys.argv:
        assert [struct.unpack('>5i', ack) for ack in restored] == [(0, i, sid, -1, 0) for i, sid in enumerate(new_skills[:4])]
        assert kinds.index(0x55b) < kinds.index(0x123)
    else:
        assert not restored

    with closing(sqlite3.connect(path)) as db:
        before_retry = tuple(db.iterdump())
    replay = handle(kind, payload, 20)
    assert all(e.kind not in (0x29f, 0x123) for e in replay)
    with closing(sqlite3.connect(path)) as db:
        assert tuple(db.iterdump()) == before_retry

    with closing(sqlite3.connect(path)) as db:
        before_drag = db.execute('SELECT payload,revision FROM skill_slots WHERE uid=?', (uid,)).fetchone()
    assert struct.unpack('>22i', before_drag[0])[:5] == new_skills
    assert actor.character()['unit_class'] == 79
    assert LocalState(path, uid).load_skills()[:5] == new_skills
    manual = []
    for index, skill in enumerate(new_skills[:4]):
        equip_reply = handle(0x122, struct.pack('>ii', index, skill), 21 + index)
        equip_ack = next(e.payload for e in equip_reply if e.kind == 0x123)
        assert struct.unpack('>5i', equip_ack) == (0, index, skill, -1, 0)
        manual.append(equip_ack)
    if restored:
        assert restored == manual
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT payload,revision FROM skill_slots WHERE uid=?', (uid,)).fetchone() == before_drag
    print('CAREER', '66 -> 79', method, 'replies', [hex(k) for k in kinds], flush=True)
    print('SLOTS', old_skills, '->', new_skills, '55B/cold read agree; re-equip ACK leaves SQL unchanged', flush=True)
    return wire, manual[0]


def refresh_scope():
    from els_server.domain.careers import PARENTS
    from els_server.domain.character_rules import CLASSES
    from els_server.domain.role_progression import slot_accepts
    from els_server.domain.skill_rules import equippable_skills, upgraded_slots
    from els_server.protocol.career_messages import skill_refresh

    routes = 0
    for target, definition in CLASSES.items():
        if definition['stage'] != 3:
            continue
        for seals in ((), tuple(range(1, 12))):
            before = dict(uid=1001, unit_type=client_data().unit(target)['unitType'],
                          unit_class=PARENTS[target], level=99, transcendence=True, master=False,
                          skill_row_expanded=True, skill_seal_groups=seals)
            after = dict(before, unit_class=target)
            samples = {True: None, False: None}
            for skill in equippable_skills(before):
                index = next(i for i in range(22) if slot_accepts(i, skill))
                slots = [0] * 22
                slots[index] = skill
                migrated = upgraded_slots(slots, after)
                replaced = skill != migrated[index]
                if samples[replaced] is None:
                    samples[replaced] = (index, migrated)
                if all(samples.values()):
                    break
            for replaced, (index, migrated) in samples.items():
                events = skill_refresh(after, migrated, rebuild=False, previous_class=before['unit_class'])
                actual = [struct.unpack('>5i', event.payload) for event in events if event.kind == 0x123]
                assert actual == ([(0, index, migrated[index], -1, 0)] if replaced else [])
                assert [event.kind for event in events[:2]] == [0x131, 0x55b]
        routes += 1
    assert routes == 60

    second = dict(uid=1001, unit_type=1, unit_class=66, level=99, transcendence=True, master=False)
    second_slots = (21100,) + (0,) * 21
    assert [e.kind for e in skill_refresh(second, second_slots, rebuild=False, previous_class=PARENTS[66])] == [0x131, 0x55b]
    third = dict(second, unit_class=79)
    third_slots = (21113,) + (0,) * 21
    assert [e.kind for e in skill_refresh(third, third_slots, rebuild=False, previous_class=80)] == [0x131, 0x55b]
    master = dict(third, master=True, artifact=dict(template=1, evolution=1, level=1, experience=0, potentials=[0]*4))
    from els_server.domain.role_progression import first_master_skill

    master_slots = third_slots[:-1] + (first_master_skill(master),)
    assert [e.kind for e in skill_refresh(master, master_slots, rebuild=True, previous_class=79)] == [0x446, 0x123, 0x55b]
    print('SCOPE 60 routes with and without seals; second-job, lateral third-job, and Master controls', flush=True)


if __name__ == '__main__':
    if 'scope' in sys.argv:
        refresh_scope()
    else:
        with TemporaryDirectory(dir=WORK, prefix='owned-') as directory:
            methods = [method for method in ('item', 'shop', 'quest', 'quick') if method in sys.argv] or ['item']
            for method in methods:
                server_case(Path(directory) / (method + '.sqlite3'), method)
