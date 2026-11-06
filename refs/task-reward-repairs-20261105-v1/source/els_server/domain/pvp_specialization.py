"""Native effects and costs; deterministic progression is an approved local rule."""
from functools import lru_cache
from pathlib import Path
import hashlib,json,struct
from els_server.game_data import client_data,CLIENT_SHA

DATA_SHA='fac704d8272a382c88ccbce436a9e7d442e84cc597da6bb05a48143942b82aaf'
POLICY='pvp-specialization-local-deterministic-20261105-v1'

@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/pvp_specialization.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('PvP specialization source identity')
    d=json.loads(raw);c=client_data()
    if d['policy']!=POLICY or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256']:raise ValueError('PvP specialization current client')
    for t,row in d['targets'].items():
        item=c.item(int(t))
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']or item['item_type']!=row['item_type']:raise ValueError('PvP specialization target identity')
    return d

@lru_cache(maxsize=1)
def by_option():return {v:r for r in catalog()['series'].values()for v in r['options']}

def target(template):
    row=catalog()['targets'].get(str(template))
    if row is None:raise ValueError('Duelist sparring equipment required')
    return row

def applicable(template,group,row):
    t=target(template)
    if row['group']!=group or t['item_type']not in row['item_types']or row['unit_type']not in(0,t['unit_type']):raise ValueError('PvP effect group/part/role mismatch')
    return row

def options(template,group,values):
    target(template)
    if group not in(22,23,24)or not isinstance(values,(list,tuple))or len(values)!=4:raise ValueError('PvP four native specialization slots')
    for value in values:
        if type(value)is not int or value<0:raise ValueError('PvP specialization option')
        if value:
            row=by_option().get(value)
            if row is None:raise ValueError('Unknown PvP specialization option')
            applicable(template,group,row)
    return list(values)

def request(payload):
    if not isinstance(payload,bytes)or len(payload)!=38:raise ValueError('PvP specialization request width')
    uid,n,group,count,slot,choice,flag,mode,tail=struct.unpack('>QIiIiQBiB',payload)
    if not 0<uid<2**63 or (n,count,flag,tail)!=(1,1,0,0)or group not in(22,23,24)or not 1<=slot<=4 or mode not in(11,12):raise ValueError('PvP specialization original producer fields')
    if mode==11 and choice!=0 or mode==12 and str(choice)not in catalog()['series']:raise ValueError('PvP specialization selected effect')
    return uid,group,slot-1,choice,mode

def advance(template,character,group,values,slot,choice,mode):
    current=options(template,group,values);value=current[slot]
    if mode==12:
        row=applicable(template,group,catalog()['series'][str(choice)])
        if value in row['options']:raise ValueError('Same PvP effect already selected')
        if group==24 and row['skill']not in {sid for sid,_ in client_data().skill_tree(character['unit_class'])}:raise ValueError('PvP skill is outside current career')
        current[slot]=row['options'][0]
    else:
        if not value:raise ValueError('Select PvP effect before enchant')
        row=by_option()[value];index=row['options'].index(value)
        if index==len(row['options'])-1:raise ValueError('PvP effect is already at its maximum')
        current[slot]=row['options'][index+1]
    return current,catalog()['costs'][str(target(template)['item_type'])][str(mode)][str(group)]
