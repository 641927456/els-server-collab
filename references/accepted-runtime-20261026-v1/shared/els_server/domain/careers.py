"""Native career item eligibility, independent of transport and persistence."""
import json
from pathlib import Path
from els_server.domain.character_rules import CLASSES

DATA=json.loads((Path(__file__).parents[1]/'data/careers.json').read_text(encoding='utf8'))
RULES={int(k):v for k,v in DATA['rules'].items()}
PARENTS={int(k):v for k,v in DATA['parents'].items()}

def transition(character,template):
    from els_server.domain.character_rules import validate_career_state
    validate_career_state(character)
    if template not in RULES:raise ValueError('Unsupported career item')
    rule=RULES[template];kind=rule['kind'];target=rule['target'];current=character['unit_class']
    stage=CLASSES[current]['stage'];out=dict(character)
    if character['level']<rule['level']:raise ValueError('Career level requirement')
    if target and CLASSES[target]['base_class']!=CLASSES[current]['base_class']:raise ValueError('Career character mismatch')
    if kind.startswith('advancement_'):
        if current!=PARENTS[target] or stage!=int(kind[-1])-1:raise ValueError('Career route requirement')
        if kind=='advancement_3' and not character['transcendence']:raise ValueError('Third class requires transcendence')
        out['unit_class']=target
    elif kind=='transcendence_book':
        if stage!=2 or character['transcendence'] or character['master']:raise ValueError('Transcendence requirement')
        out['transcendence']=True
    elif kind=='master_advancement':
        if current!=target or stage!=3 or not character['transcendence'] or character['master']:raise ValueError('Master requirement')
        out['master']=True
        out['artifact']=dict(template=character['unit_type'],evolution=1,level=1,experience=0,potentials=[0]*4)
    else:
        if current==target or stage!=CLASSES[target]['stage']:raise ValueError('Same-stage class change requirement')
        if kind=='master_change':
            if not character['master']:raise ValueError('Master change requirement')
        elif kind=='transcendence_change':
            if not character['transcendence'] or character['master']:raise ValueError('Transcendence change requirement')
        elif character['master'] or (stage==2 and character['transcendence']):
            raise ValueError('Use the matching transcendence/master ticket')
        out['unit_class']=target
    out['revision']+=1
    return validate_career_state(out)
