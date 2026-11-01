"""Original five-quest Quick Start, permanently open under the owner's policy."""
import functools,hashlib,json
from pathlib import Path

CODE=578
QUESTS=tuple(range(169600,169605))
BOXES=frozenset((720720,720721,720818))
MASTER_TICKET=719707
DATA_SHA='4bd041b1586d3e91ccd914e4f50c92150730452bd2a26aa6f8d5ec25877523e2'

@functools.lru_cache(maxsize=1)
def catalog():
    from els_server.game_data import client_data,CLIENT_SHA
    raw=(Path(__file__).parents[1]/'data/quick_start.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Quick Start source changed')
    data=json.loads(raw);client=client_data()
    if data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client.manifest['catalog_sha256']:
        raise ValueError('Quick Start client identity')
    for row in data['readers']:
        item=client.item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or row['native']!={'ok':1,'consumed':304}:
            raise ValueError('Quick Start native reward identity')
    return data

def selected(options):
    if CODE not in options:return False
    if options[CODE]!=0 or len(options)!=1:raise ValueError('Quick Start creation options')
    return True

def require_quest(character,quest):
    if quest['m_iID'] in QUESTS and not character.get('quick_start',False):
        raise ValueError('Quick Start participant required')

def career_transition(before,target,completed):
    from els_server.domain.careers import PARENTS,transition,RULES
    from els_server.domain.character_rules import CLASSES
    current=before['unit_class'];stage=CLASSES[current]['stage']
    if target==0:raise ValueError('New Quick Start transcendence paused for code recovery')
    # The native transcendence button sends an empty STXAny, encoded as class0.
    if target==0 and stage==2 and not before['transcendence']:
        if QUESTS[2] not in completed:raise ValueError('Quick Start transcendence task')
        kind='transcendence_book'
    else:
        if target not in CLASSES or PARENTS.get(target)!=current or stage not in (0,1,2):
            raise ValueError('Quick Start career branch')
        if QUESTS[(0,1,3)[stage]] not in completed:raise ValueError('Quick Start career task')
        kind='advancement_'+str(stage+1)
    template=next((t for t,r in RULES.items() if r['kind']==kind and (kind=='transcendence_book' or r['target']==target)),None)
    if template is None:raise ValueError('Quick Start original career rule missing')
    return transition(before,template)

def box_entries():
    return tuple(dict(template=int(t),selection_count=0,quick_start_box=True,entries=tuple(rows))
                 for t,rows in catalog()['boxes'].items())


def install_inventory():
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    from els_server.domain.activity_2026_stack_policy import effective_stack
    for row in catalog()['readers']:
        t=row['template']
        if t in VERIFIED_TEMPLATES:
            if (VERIFIED_TEMPLATES[t],TEMPLATE_BAG_GROUPS[t])!=(row['metadata'],row['group']):
                raise ValueError('Quick Start existing inventory classification')
            continue
        VERIFIED_TEMPLATES[t]=row['metadata'];TEMPLATE_BAG_GROUPS[t]=row['group']
        TEMPLATE_MAX_STACKS[t]=effective_stack(row['max_stack'])
