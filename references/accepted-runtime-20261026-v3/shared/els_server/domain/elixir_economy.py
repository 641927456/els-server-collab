"""Pinned effect inputs and an explicit local formula for original ordinary rewards."""
import functools,hashlib,json,math
from fractions import Fraction
from pathlib import Path

PAYLOAD_SHA='cc20d66d0262e937a947e9068e80fd54ebfb17e86ae9530058da6c3978325e2e'
TEMPLATES=(190401,310775,310776,722760,722761)

@functools.lru_cache(maxsize=1)
def policy():
    from els_server.game_data import client_data,CLIENT_SHA
    raw=(Path(__file__).resolve().parents[1]/'data/elixir_economy.json').read_bytes();d=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=PAYLOAD_SHA or d['client_sha256']!=CLIENT_SHA or tuple(r['template']for r in d['rows'])!=TEMPLATES or d['new_sources']:
        raise ValueError('Elixir economy source identity')
    for r in d['rows']:
        if hashlib.sha256(client_data().item(r['template'])['record']).hexdigest()!=r['record_sha256']:raise ValueError('Elixir economy item source')
    return d

def eligible(identity):
    from els_server.domain.formal_pve_economy import definition
    if type(identity)is not int:raise ValueError('Elixir economic map identity')
    return definition(identity) is not None

def effects(rows,identity,kind):
    if kind not in('experience','drop'):raise ValueError('Elixir economic effect kind')
    if not eligible(identity):return 0,[]
    definitions={r['template']:r for r in policy()['rows']};selected=[];total=0
    for row in rows:
        rule=definitions.get(row['template'])
        if rule is None or identity in rule['disabled_dungeons']:continue
        amount=rule[kind+'_bp']
        if amount:
            selected.append(dict(template=row['template'],source_uid=row['source_uid'],start=row['start'],end=row['end'],basis_points=amount));total+=amount
    if not 0<=total<=10000:raise ValueError('Finite elixir economic percentage')
    return total,selected

def percentage(value,basis_points):
    if type(value)is not int or value<0 or type(basis_points)is not int or not 0<=basis_points<=10000:raise ValueError('Elixir economic integer amount')
    return value*(10000+basis_points)//10000

def draw(size,randbelow):
    if type(size)is not int or size<1:raise ValueError('Elixir probability denominator')
    value=randbelow(size)
    if type(value)is not int or not 0<=value<size:raise ValueError('Elixir probability random bound')
    return value

def hit(numerator,denominator,randbelow,basis_points=0):
    if type(numerator)is not int or type(denominator)is not int or not 0<=numerator<=denominator or type(basis_points)is not int or not 0<=basis_points<=10000:raise ValueError('Elixir probability source')
    if not basis_points:return draw(denominator,randbelow)<numerator
    return draw(denominator*10000,randbelow)<min(denominator*10000,numerator*(10000+basis_points))

def source_case(cases,groups,items,scale,randbelow,basis_points):
    """Scale legal leaf hit mass once, keeping original legal relative weights.

    Unsupported/blank outcomes stay outside the legal pool. A group contributes
    its original parent probability times its original child probability.
    No unsupported leaf, repeated grant or extra item is introduced.
    """
    if type(basis_points)is not int or not 1<=basis_points<=10000:raise ValueError('Source bonus percentage')
    leaves=[]
    for case in cases:
        weight=Fraction(case['ticks'],scale)
        if case['kind']=='group':
            for child in groups[str(case['id'])]:
                if child['kind']!='group'and str(child['id'])in items and child['ticks']:
                    leaves.append((child,weight*Fraction(child['ticks'],scale)))
        elif str(case['id'])in items and case['ticks']:leaves.append((case,weight))
    mass=sum((p for case,p in leaves),Fraction())
    if not mass:return None
    if not 0<mass<=1:raise ValueError('Source original legal probability mass')
    boosted=min(Fraction(1),mass*Fraction(10000+basis_points,10000))
    if draw(boosted.denominator,randbelow)>=boosted.numerator:return None
    denominator=math.lcm(*(weight.denominator for case,weight in leaves));weights=[int(weight*denominator)for case,weight in leaves]
    chosen=draw(sum(weights),randbelow)
    for (case,weight),ticks in zip(leaves,weights):
        if chosen<ticks:return case
        chosen-=ticks
    raise ValueError('Source legal leaf selection')
