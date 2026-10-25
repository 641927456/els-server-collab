"""Native preview membership is authoritative for ice role compatibility."""
from els_server.domain.inventory_items import role_ice_catalog
from functools import lru_cache

@lru_cache(maxsize=15)
def series_pools(unit_type=1):
    if type(unit_type) is not int or not 1<=unit_type<=15:raise ValueError('Invalid ice character type')
    from els_server.domain.acquisition_policy import can_acquire
    pools={int(machine):tuple((item,1) for item in roles[str(unit_type)] if can_acquire(item))
           for machine,roles in role_ice_catalog()['pools'].items()
           if roles.get(str(unit_type)) and can_acquire(int(machine))}
    return {machine:pool for machine,pool in pools.items() if pool}


def _split(weight,entries):
    if not entries or weight<len(entries):raise ValueError('Invalid local ice weights')
    whole,remainder=divmod(weight,len(entries))
    return tuple((entry,whole+(i<remainder)) for i,entry in enumerate(entries))


@lru_cache(maxsize=15)
def role_pools(unit_type=1):
    from els_server.domain.shop_additions import catalog
    from els_server.domain.acquisition_policy import can_acquire
    data=catalog('ice-common');result={}
    for machine,series in series_pools(unit_type).items():
        profile=data['profiles'][data['machine_profiles'][str(machine)]]
        groups=[]
        for group in profile['groups']:
            entries=[e for e in group['entries'] if e.get('role',unit_type)==unit_type and can_acquire(e['template'])]
            if entries:groups.append((group,entries))
        # Scale family weights exactly to the remaining local probability mass.
        total=sum(g['weight'] for g,_ in groups);mass=profile['common_weight']
        weights=[g['weight']*mass//total for g,_ in groups]
        for i in range(mass-sum(weights)):weights[i%len(weights)]+=1
        pool=list(_split(profile['cosmetic_weight'],[t for t,_ in series]))
        for (_,entries),weight in zip(groups,weights):
            pool.extend((e['template'],w) for e,w in _split(weight,entries))
        if len({t for t,_ in pool})!=len(pool) or sum(w for _,w in pool)!=10000:raise ValueError('Ice pool collision/weight mismatch')
        result[machine]=tuple(pool)
    return result


def reward_quantity(machine,template):
    from els_server.domain.shop_additions import catalog
    data=catalog('ice-common');profile=data['profiles'][data['machine_profiles'][str(machine)]]
    quantities={e['quantity'] for g in profile['groups'] for e in g['entries'] if e['template']==template}
    if len(quantities)>1:raise ValueError('Conflicting ice reward quantity')
    return quantities.pop() if quantities else 1
