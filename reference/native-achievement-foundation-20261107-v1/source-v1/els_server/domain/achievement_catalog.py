"""Original achievement identities and conditions, shared by account consumers."""
from functools import lru_cache
from pathlib import Path
import json
from els_server.game_data import CLIENT_SHA


@lru_cache(maxsize=1)
def catalog():
    data=json.loads((Path(__file__).parents[1]/'data/client/achievements.json').read_bytes())
    if data['schema_version']!=1 or data['client_sha256']!=CLIENT_SHA:
        raise ValueError('Achievement resource identity changed')
    return {int(key):value for key,value in data['achievements'].items()}


def achievement(identity):
    try:return catalog()[identity]
    except KeyError:raise ValueError('Unknown current achievement identity')from None


@lru_cache(maxsize=1)
def rewards():
    data=json.loads((Path(__file__).parents[1]/'data/client/achievement_rewards.json').read_bytes())
    if data['schema_version']!=1:raise ValueError('Unknown achievement reward schema')
    return {int(key):value for key,value in data['rewards'].items()}


def reward_items(identity):
    groups=achievement(identity)['reward_groups'];known=rewards()
    if any(group not in known for group in groups):return None
    return [dict(item)for group in groups for item in known[group]]


def progress_projection(saved):
    """Native UI iterates this map, including definitions without a saved counter."""
    completed={row['id']for row in saved['completed']}
    progress={row['id']:{c['id']:c for c in row['conditions']}for row in saved['progress']}
    return [dict(id=identity,conditions=[dict(progress.get(identity,{}).get(condition['id'],
        dict(id=condition['id'],count=0,complete=False)))for condition in definition['conditions']])
        for identity,definition in sorted(catalog().items())if identity not in completed]


def points(completed):
    result=[0,0,0,0]
    for row in completed:
        definition=achievement(row['id']);result[definition['category']]+=definition['points']
    return result
