"""Finite profile inputs and readbacks for exactly three enrolled QA accounts."""
from contextlib import closing
from pathlib import Path
import sqlite3


def seed(path, actors):
    from els_server.storage.characters import Characters
    from els_server.storage.local_state import LocalState
    from els_server.storage import profession_state, resonance_state, game_mail
    from els_server.storage.inventory_state import grant_items
    from els_server.protocol.profession_messages import ProfessionState
    from els_server.domain.profession_growth import BLACKSMITH_STEPS
    from els_server.domain.resonance import curve
    from els_server.domain.town_travel import catalog
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
    from els_server.game_data import client_data
    assert len(actors) == 3 and len({a['account_id'] for a in actors}) == 3
    assert all(a['uid'] is not None for a in actors)
    for a in actors:
        uid, account = a['uid'], a['account_id']
        LocalState(path, uid).save(20001, 0, 0, catalog()['towns']['20001']['xyz'])
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?', (uid,)).fetchone() == (account,)
            db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?', (uid,))
            db.execute('UPDATE reward_balances SET ed=?,experience=? WHERE uid=?', (6_000_000, client_data().thresholds[98], uid))
            if a is actors[0]:
                profession_state.replace(db, uid, account, 0, ProfessionState(2, 7, 0, {}, 0, BLACKSMITH_STEPS[7]))
                resonance_state.ensure(db)
                db.execute('INSERT INTO account_resonance VALUES(?,1,?,1)', (account, curve()[149]['TOTAL_ER_EXP']))
                grant_items(db, [dict(template=77000, metadata=VERIFIED_TEMPLATES[77000],
                    group=TEMPLATE_BAG_GROUPS[77000], quantity=5)], uid)
    first = actors[0]
    first['alt'] = dict(uid=Characters(path, first['account_id']).create(
        first['character_name']+'Alt', 4, 'owned-achievement-alt-'+str(first['uid']))['uid'],
        account_id=first['account_id'], character_name=first['character_name']+'Alt', bridge=first['bridge'])
    LocalState(path, first['alt']['uid']).save(20001, 0, 0, catalog()['towns']['20001']['xyz'])
    game_mail.initialize(path)


def snapshot(path, actors):
    from els_server.storage import achievements, game_mail
    from els_server.storage.inventory_state import load_items
    from els_server.storage.npc_trade import balances
    result = []
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        for a in [*actors, actors[0]['alt']]:
            uid, account = a['uid'], a['account_id']
            assert db.execute('SELECT account_id FROM character_owners WHERE uid=?', (uid,)).fetchone() == (account,)
            total, mails = game_mail.inbox(path, account, uid)
            result.append(dict(uid=uid, achievement=achievements.snapshot(db, account, uid),
                items=load_items(db, uid), money=balances(db, uid),
                mails=[dict(id=m['id'], item=m.get('item')) for m in mails], mail_total=total))
    return result
