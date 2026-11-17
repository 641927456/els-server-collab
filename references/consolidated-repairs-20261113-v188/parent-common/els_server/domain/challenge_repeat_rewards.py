"""Weekly final breath and repeat marks from the roster's weekly progress.

Final-node, living-helper mark eligibility and units5/10/15/10/20 follow the
2024-01-17 implemented notes, unchanged by the2024-11-20 improvement.
The weekly breath quantity1 is the previously authorized server-local value.
The original shared clear writer owns the inventory and receipt transaction.
"""
from els_server.storage.challenge_scroll import snapshot
from els_server.storage.challenge_state import read,eligible
from els_server.domain.reward_rules import item_plan
from els_server.domain.raid_life_observation import alive
from secrets import randbelow
from els_server.game_data import client_data

# Current native final-node display pools. Exact official rates are private;
# the 2026-10-25 authorization permits this explicit server-local rate:
# each listed Force book independently has a 1% chance per weekly claim.
FORCE_DROPS={34950:(43677,43678),35020:(43773,43774)}
FORCE_CHANCE_BP=100
FORCE_POLICY='challenge-force-local-20261107-v1'

MARK_UNITS={(4,1):5,(4,2):10,(4,3):15,(5,1):10,(5,2):20}


def plans(db,members,now):
    rows=[]
    for member in members:
        effect=member.active_challenge
        state=read(db,member.account.uid)
        node=eligible(state,effect['dungeon'],now)
        if node is None or state['attempt']!=effect['attempt']:
            raise ValueError('Challenge repeat reward requires current encounter')
        ordinal=next(i for i in range(node['count'])if not state['progress']&(1<<(node['flag']+i)))
        key=(state['challenge'],effect['dungeon'],ordinal)
        value=snapshot(db,member.account.uid,state['challenge'],now,details=True)
        rows.append((member,key,(effect['dungeon'],ordinal)in value['encounters'],bool(node['final']and ordinal==node['count']-1),state['phase']))
    if len({(key,phase)for _,key,_,_,phase in rows})!=1:raise ValueError('Challenge repeat roster encounter changed')
    pool=FORCE_DROPS.get(rows[0][1][1],())
    if pool and not set(pool)<=set(client_data().dungeon(rows[0][1][1])['BOSS_DROP_ITEM'].get('COMMON',{}).values()):
        raise ValueError('Challenge Force current final-node display changed')
    fresh=sum(not repeated for _,_,repeated,_,_ in rows);result={}
    for member,key,repeated,final,phase in rows:
        rewards=[]
        if final and not repeated:
            rewards.append(item_plan(136135 if key[0]==4 else 136140,1))
            for template in pool:
                if randbelow(10000)<FORCE_CHANCE_BP:rewards.append(item_plan(template,1))
        if final and repeated and fresh and alive(member,member.dungeon_run.run_id):
            rewards.append(item_plan(136151 if key[0]==4 else 136152,fresh*MARK_UNITS[(key[0],phase)]))
        result[member]=rewards
    return result


def source(member,plan,guard):
    """Seal the exact current final plan inside its original group writer."""
    run=member.dungeon_run
    if run.identity not in FORCE_DROPS or not plan:return None
    from els_server.domain.raid_reward_items import _issue_source
    return _issue_source(member.reward_transaction,member.account.uid,member.reward_run_id,'phase',
        dict(reward_source=FORCE_POLICY,dungeon=run.identity,graph_sha256=run.graph['source_sha256'],
            attempt=member.active_challenge['attempt'],source_run=run.run_id,stage=run.stage,
            owner=member.account.uid,pool=list(FORCE_DROPS[run.identity]),chance_bp=FORCE_CHANCE_BP,
            weekly_claim=any(r['template']in(136135,136140)for r in plan)),plan,guard)
