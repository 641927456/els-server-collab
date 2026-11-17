"""Compose the current guild's sourced economic effects in one read snapshot."""
from decimal import Decimal
from els_server.storage.guild_membership_state import snapshot
from els_server.domain import guild_services,guild_rules,guild_skills,guild_emblems,guild_fountain


def basis(value):
    scaled=Decimal(str(value))*10000
    if scaled!=int(scaled)or scaled<0:raise ValueError('Nonintegral guild percentage')
    return int(scaled)


def economic(db,owner,account,now):
    saved=snapshot(db,owner,account)
    result=dict(guild=0,experience_bp=0,clear_experience_bp=0,ed_bp=0,drop_bp=0,
                services=[],skills=[],guardian=None,fountain=[])
    if saved is None:return result
    result['guild']=saved['id'];state=saved['system']
    services=guild_services.rows(db,owner,account,now);result['services']=services
    if any(r['template']==1034 for r in services):result['experience_bp']+=5000
    if saved['grade']>5:return result
    page=str(state['member_details'].get(str(owner),{}).get('page',1))
    selected=guild_skills.effective(state['pages'][page],now)
    for skill,field in((514,'experience_bp'),(518,'ed_bp'),(519,'drop_bp')):
        rank=selected['skills'].get(str(skill),0)
        if not rank:continue
        definition=guild_rules.catalog()['skills'][str(skill)]['NUMERICAL_DATA1']
        amount=definition['m_Value'][str(rank)]
        result[field]+=basis(Decimal(str(amount))/100)
        result['skills'].append(dict(id=skill,rank=rank,page=int(page),basis_points=basis(Decimal(str(amount))/100)))
    guardian=state['equipped_emblems'].get('4')
    if guardian is not None:
        part=guild_emblems.parts(state)[str(guardian)]
        field={148:'ed_bp',149:'experience_bp',150:'drop_bp'}.get(guardian)
        if field is not None and part['level']and part['expires']>now:
            amount=part['level']*100;result[field]+=amount
            result['guardian']=dict(id=guardian,level=part['level'],end=part['expires'],basis_points=amount)
    from els_server.domain.title_option_data import catalog
    options=catalog()
    for socket,pity in guild_fountain.rows(state,now):
        if not socket:continue
        # DCB is the existing clear-only option, not ordinary monster EXP.
        rate=options[socket].get('m_fIncreaseDCBExpPercent',0)
        if rate:
            amount=basis(rate);result['clear_experience_bp']+=amount
            result['fountain'].append(dict(socket=socket,basis_points=amount,week=guild_rules.week(now)))
    return result


def economy(db,owner,account,now):
    result=economic(db,owner,account,now)
    return dict(experience_rate=(result['experience_bp']+result['clear_experience_bp'])/10000,
                ed_rate=result['ed_bp']/10000,services=result['services'],effects=result)
