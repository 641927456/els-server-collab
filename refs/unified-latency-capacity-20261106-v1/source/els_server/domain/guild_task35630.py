"""Original35630 only: Mu talk plus actual committed guild membership."""
import functools
import hashlib
import json
from pathlib import Path

WRITER_ENABLED = True


@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/guild_task35630.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='3726cda7c50595a3412326af5481a1f3535e75acb7e42f6ed9187253c6550c14':
        raise ValueError('Guild task original source changed')
    row=json.loads(raw)
    from els_server.storage.local_state import TOWN_SCENES
    if any(TOWN_SCENES.get(int(t))!=scene for t,scene in row['towns'].items()):
        raise ValueError('Guild Mu original House40046 scene changed')
    from els_server.domain.guild_membership_items import definitions
    if not any(r['template']==400152 for r in definitions()):
        raise ValueError('Guild task fixed reward reader')
    return row


def target(sub):
    if sub not in catalog()['subquests'].values():
        raise ValueError('Unknown Guild objective')
    return 1


def joined(db,uid,qid,sub):
    if qid!=35630 or sub!=catalog()['subquests']['35631']:
        raise ValueError('Guild membership objective source')
    account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
    if account is None:raise ValueError('Guild task has no owned actor')
    from els_server.storage.guild_membership_state import snapshot
    return int(snapshot(db,uid,account[0]) is not None)


def action_guard(store,db,kind,request):
    if not callable(store.account_source_guard) or store.account_id is None:
        raise ValueError('Guild task requires live owner and source guard')
    store.account_source_guard(db)
    if request.get('npc',10045)!=10045:
        raise ValueError('Guild task original NPC identity')
    if not WRITER_ENABLED:
        done=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='completed_quests'").fetchone()
        if kind!='claim' or not done or not db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=35630',(store.uid,)).fetchone():
            raise ValueError('New Guild task writers are held')


def source(s):
    from els_server.domain.guild_membership_flow import facts
    captured=facts(s)
    if str(s.active_map) not in catalog()['towns']:
        raise ValueError('Guild task requires current original Mu town')
    return captured
