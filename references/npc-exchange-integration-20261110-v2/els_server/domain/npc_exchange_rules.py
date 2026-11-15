"""Original NPC house/recipe selectors and exact registered random weights."""
from collections import Counter
from fractions import Fraction
from functools import lru_cache
import hashlib,json,math,secrets,struct
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA

@lru_cache(maxsize=1)
def catalog():
    path=Path(__file__).resolve().parents[1]/'data/npc_exchange.json'
    raw=path.read_bytes();d=json.loads(raw);m=json.loads(path.with_suffix('.manifest.json').read_bytes())
    if(d['schema']!=1 or m['schema']!=1 or hashlib.sha256(raw).hexdigest()!=m['sha256']
       or d['client_sha256']!=m['client_sha256'] or d['client_sha256']!=CLIENT_SHA
       or d['catalog_sha256']!=client_data().manifest['catalog_sha256']
       or len(d['recipes'])!=m['recipe_count'] or len(d['readers'])!=m['reader_count']):
        raise ValueError('NPC exchange catalog identity')
    for row in d['readers']:
        item=client_data().item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or item['metadata']!=row['metadata']:
            raise ValueError('NPC native item reader identity')
    return d

def definitions():return catalog()['readers']

@lru_cache(maxsize=1)
def reader_ids():return frozenset(row['template']for row in definitions())

def request(payload):
    from els_server.protocol.purifier_exchange_messages import ExchangeRequest
    if type(payload)is not bytes or len(payload)!=37:raise ValueError('NPC exchange request width')
    r=ExchangeRequest(*struct.unpack('>iQiiiiiBi',payload))
    if(r.house<=0 or r.source<=0 or not 0<=r.source_uid<2**63 or r.source_quantity<=0
       or r.quantity<=0 or r.exchange_type not in(1,2,3,4)or r.native_flag!=1 or r.native_index!=0):
        raise ValueError('NPC exchange original selector')
    return r

@lru_cache(maxsize=1)
def groups():
    result={}
    for row in catalog()['recipes']:
        key=tuple(row[k]for k in('house','type','source','source_quantity'))
        result.setdefault(key,[]).append(row)
    return result

def _selected_rows(r):
    rows=groups().get((r.house,r.exchange_type,r.source,r.source_quantity),())
    if r.exchange_type==3:rows=[row for row in rows if row['destination']==r.destination]
    return rows


@lru_cache(maxsize=1)
def _specialized_indices():
    return frozenset(catalog()['specialized_indices'])


@lru_cache(maxsize=1)
def generic_indices():
    return frozenset(catalog()['generic_indices'])


def selection(r,town):
    if town not in catalog()['house_towns'].get(str(r.house),()):raise ValueError('NPC belongs to another scene')
    if r.exchange_type!=3 and r.destination!=0:raise ValueError('Nonselect NPC exchange destination')
    rows=_selected_rows(r)
    if not rows or r.exchange_type in(1,3)and len(rows)!=1:raise ValueError('Unknown or ambiguous NPC exchange recipe')
    if any(row['index'] in _specialized_indices() for row in rows):
        raise ValueError('Original NPC recipe requires its dedicated exchange')
    if any(row['destination']in catalog()['blocked_new_outputs']for row in rows):raise ValueError('NPC output remains explicitly closed')
    from els_server.domain.acquisition_policy import npc_output_allowed
    if any(row['index'] not in generic_indices() or not npc_output_allowed(row['destination'],rows)
           for row in rows):
        raise ValueError('Original NPC recipe has a source-restricted output')
    if len({row['period_days']for row in rows})!=1:raise ValueError('Mixed original NPC reward periods')
    if r.exchange_type in(2,4)and sum(Fraction(str(row['rate']))for row in rows)+failure_rate(rows)!=100:
        raise ValueError('Incomplete original NPC random probability mass')
    return rows

def specialized(r):
    rows=_selected_rows(r)
    return bool(rows and all(row['index'] in _specialized_indices() for row in rows))


def awards(rows,quantity,*,randbelow=None):
    if rows[0]['type']in(1,3):return Counter({rows[0]['destination']:rows[0]['quantity']*quantity}),0
    randbelow=secrets.randbelow if randbelow is None else randbelow
    rates=[Fraction(str(row['rate']))for row in rows]
    failure=failure_rate(rows)
    if sum(rates)+failure!=100:raise ValueError('Incomplete original NPC random probability mass')
    scale=math.lcm(*(rate.denominator for rate in rates),failure.denominator)
    weights=[int(rate*scale)for rate in rates];total=100*scale;result=Counter()
    for _ in range(quantity):
        ticket=randbelow(total)
        if type(ticket)is not int or not 0<=ticket<total:raise ValueError('NPC random draw range')
        for row,weight in zip(rows,weights):
            if ticket<weight:
                result[row['destination']]+=row['quantity'];break
            ticket-=weight
    return result,0

def failure_rate(rows):
    keys={tuple(row[k]for k in('house','type','source','source_quantity'))for row in rows}
    if len(keys)!=1:raise ValueError('Mixed NPC random groups')
    for policy in catalog().get('random_failure_groups',()):
        if next(iter(keys))==tuple(policy[k]for k in('house','type','source','source_quantity')):
            return Fraction(str(policy['failure_rate']))
    return Fraction(0)
