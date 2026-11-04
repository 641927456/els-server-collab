"""Version-one empty membership profile, not an economic guild subsystem.

KGuildInfo327B3C0 supplies the explicit zero/empty opaque basic fields.
The current 278/28B consumers accept empty extension collections; unknown
writers remain absent. Level/EXP/SP follow the proven create flow; current
native page selection is one-based. Only our versioned new rows are read.
"""
from datetime import datetime, timezone, timedelta

VERSION = 1


def profile(saved):
    from els_server.domain.guild_bank_rules import permissions
    if saved['profile_version'] != VERSION:
        raise ValueError('Unknown persisted guild profile; no migration')
    basic = dict(id=saved['id'], name=saved['name'], max_members=20,
                 level=1, experience=0, message=saved['message'],
                 founding_day=datetime.fromtimestamp(saved['created_at'],
                     timezone(timedelta(hours=8))).strftime('%Y-%m-%d'))
    # Explicit original constructor state. Numeric names intentionally retain
    # uncertainty; they are not declarations of official economic defaults.
    basic.update({'6b':0,'6f':0,'73':0,'77':False,'78':0,'7c':0,
                  '7d':0,'81':0,'85':0,'89':0,'8a':'','aa':'','ca':0})
    return dict(basic=basic, master_name=saved['master_name'],
                members=saved['members'], active_page=1,
                pages={1:dict(skills=(),points=1,cash_points=0,
                              max_cash_points=0,expiry='',alias='')},
                **{'11b':(),'133':(),'14b':0,'153':(),'163':permissions(),'173':(),
                   '183':(),'193':'','1b3':'','1d3':0,'1db':()})
