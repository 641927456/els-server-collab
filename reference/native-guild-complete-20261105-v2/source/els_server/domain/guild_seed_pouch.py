"""Current400265 selection pouch, with an explicit separately approved pool.

The current source declares GiveCount1 and group400265, without its contents.
An unset policy admits no production draw and never substitutes a random pool.
"""
from pathlib import Path
import json
BOX=400265

def selected_templates():
    value=json.loads((Path(__file__).resolve().parents[1]/'data/guild_seed_pouch_policy.json').read_bytes())['templates']
    if value is None:return None
    if not isinstance(value,list)or not value or len(value)!=len(set(value))or any(type(t)is not int for t in value):raise ValueError('Guild seed pouch explicit pool')
    from els_server.domain.guild_rules import calls
    seeds={row[0]['SEED_ITEM_ID']for row in calls('AddGuildPlant')}
    if not set(value)<=seeds:raise ValueError('Guild seed pouch includes an unsupported current plant')
    return tuple(value)

def entry():
    templates=selected_templates()
    if templates is None:return None
    return dict(template=BOX,group=4,selection_count=1,guild_seed_pouch=True,
        entries=[dict(template=t,quantity=1)for t in templates])
