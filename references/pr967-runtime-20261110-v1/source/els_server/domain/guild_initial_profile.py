"""Current persistent guild state projected into the native login/profile DTO."""
from datetime import datetime, timezone, timedelta

VERSION = 1


def profile(saved, *, db, now=None):
    from els_server.domain.guild_bank_rules import permission_rows
    from els_server.domain import guild_rules
    if saved['profile_version'] != VERSION:
        raise ValueError('Unknown persisted guild profile; no migration')
    system=saved['system']
    level=guild_rules.level(system['experience'])
    basic = dict(id=saved['id'], name=saved['name'], max_members=system['capacity'],
                 level=level, experience=system['experience'], message=saved['message'],
                 founding_day=datetime.fromtimestamp(saved['created_at'],
                     timezone(timedelta(hours=8))).strftime('%Y-%m-%d'))
    # Explicit original constructor state. Numeric names intentionally retain
    # uncertainty; they are not declarations of official economic defaults.
    basic.update({'6b':0,'6f':0,'73':0,'77':False,'78':0,'7c':0,
                  '7d':0,'81':0,'85':0,'89':0,'8a':'','aa':'','ca':0})
    from els_server.storage.guild_system_state import currency
    coins,banner=currency(db,saved['id'])
    basic.update({'6b':coins,'6f':banner,'73':system['skin'],'aa':system['announcement'],'ca':system['announcement_author']})
    import time
    if now is None:now=int(time.time())
    from els_server.domain.guild_skills import page_profile
    pages={int(k):page_profile(system,p,now)for k,p in system['pages'].items()}
    from els_server.domain.guild_fountain import rows as fountain_rows
    from els_server.domain.guild_emblems import rows as emblem_rows
    from els_server.domain.guild_skins import rows as skin_rows
    selected=system['member_details'].get(str(saved['owner']),{}).get('page',1)
    return dict(basic=basic, master_name=saved['master_name'],members=saved['members'],active_page=selected,pages=pages,
                **{'11b':(),'133':(),'14b':0,'153':(),'163':permission_rows(system),'173':emblem_rows(system,now,equipped_only=True),
                   '183':skin_rows(system),'193':'','1b3':'','1d3':0,'1db':fountain_rows(system,now)})
