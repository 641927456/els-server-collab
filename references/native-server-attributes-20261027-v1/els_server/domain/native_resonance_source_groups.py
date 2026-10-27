"""Selected authoritative ERP allocations for the original106 numeric groups."""
CURRENT_IDS=frozenset((1,2,4,16,17,18,19,20,21,22,11,12,13,14,15))


def numeric_groups(source):
    if type(source)is not dict or type(source.get('account'))is not dict:
        raise ValueError('Authoritative ERP snapshot required')
    enabled=source['account'].get('enabled')
    if type(enabled)is not bool:raise ValueError('Explicit account ERP state required')
    profile=source.get('profile')
    if not enabled:
        if profile is not None:raise ValueError('Disabled ERP source differs from canonical snapshot')
        return ()
    if type(profile)is not dict:raise ValueError('Synchronized ERP profile required')
    state=profile['state'];pages=profile['pages']
    if (state['selected_page']!=pages['selected_page']or state['page_count']!=len(pages['pages'])
            or state['level']!=source['account']['level']or state['cumulative_experience']!=source['account']['experience']):
        raise ValueError('ERP source generation differs')
    groups=state['allocation_groups']
    if type(groups)is not tuple or tuple(k for k,v in groups)!=(0,1,2):
        raise ValueError('Complete current ERP allocation groups required')
    flattened={};result=[]
    for tab,values in groups:
        if type(values)is not tuple or len(values)!=5:
            raise ValueError('Complete current ERP tab required')
        previous=0
        for stat,points in values:
            if (type(stat)is not int or stat<=previous or stat in flattened
                    or type(points)is not int or not 0<=points<2**31):
                raise ValueError('Unique ordered authoritative ERP points required')
            previous=stat;flattened[stat]=points
        result.append((tab,values))
    if set(flattened)!=CURRENT_IDS:raise ValueError('Current ERP definition coverage differs')
    selected=next((p for p in pages['pages']if p['page_id']==pages['selected_page']),None)
    if selected is None or dict(selected['points'])!=flattened:
        raise ValueError('Selected ERP page and wire allocations differ')
    return tuple(result)


def progress_fields(source):
    """DB29A0's17 bytes, preserving the canonical ERP profile's opaque fields.

    D3AD14..D3AD3D stores these in Unit28BD/28C1/28C5/28CD. They are not
    level, experience or available points. Disabled profiles use the original
    C832F0 zero-initialized record; enabled profiles require all four fields.
    """
    numeric_groups(source)
    if not source['account']['enabled']:
        return (0,0,0,0)
    state=source['profile']['state']
    result=[]
    for name,lo,hi in(('field21',-2**31,2**31-1),('field25',-2**31,2**31-1),
                       ('field29',0,2**64-1),('field31',0,255)):
        value=state.get(name)
        if type(value)is not int or not lo<=value<=hi:
            raise ValueError('Complete canonical ERP progress fields required')
        result.append(value)
    return tuple(result)
