"""Resource-backed party bounds; ordinary rooms remain limited to four."""
from els_server.game_data import client_data
from els_server.domain.dungeon_routes import route_catalog


def raid_definition(identity):
    if type(identity) is not int or not route_catalog().supports(identity):
        return None
    definition = client_data().dungeon(identity)
    if definition.get('m_eDungeonType') != 6:
        return None
    # The source includes real single-player raid variants; those must not
    # acquire multi-player admission from their native dungeon type alone.
    maximum = definition.get('m_MaxPlayerCount')
    minimum = definition.get('m_MinPlayerCount')
    if type(maximum) is not int or type(minimum) is not int or not 2 <= maximum <= 6 or not 1 <= minimum <= maximum:
        return None
    return dict(minimum=minimum, maximum=maximum, identity=identity)


def capacity(party):
    source = raid_definition(party['dungeon']) if party.get('raid_party') else None
    maximum = 8 if party.get('union_party') else source['maximum'] if source else 6 if party.get('raid_party') else 4
    recruitment=party.get('recruitment')
    return min(maximum,recruitment['maximum']) if recruitment and recruitment['published'] else maximum


def admission_size(party, identity):
    if party.get('union_party'):
        return False
    count = len(party['members'])
    if party.get('challenge'):
        from els_server.domain.group_challenge import limits
        from els_server.domain.challenge_flow import allowed
        state=party['challenge']
        if 'striker_parent' in party:
            native=client_data().dungeon(identity)
            minimum,maximum=native['m_MinPlayerCount'],native['m_MaxPlayerCount']
        else:
            minimum,maximum=limits(state['challenge'],state['phase'])
        effects=[allowed(s,identity) for s in party['members']]
        return minimum<=count<=maximum and all(e and e['attempt']==state['attempt'] for e in effects)
    if not party.get('raid_party'):
        # The four-member room cap must not override the selected dungeon's
        # own bounds or its native single-player-only condition.
        if not route_catalog().supports(identity):return False
        definition=client_data().dungeon(identity)
        if 1 in definition.get('DUNGEON_CHECK_CONDITION',{}).values():return False
        minimum=definition.get('m_MinPlayerCount',1)
        maximum=definition.get('m_MaxPlayerCount',4)
        return (type(minimum) is int and type(maximum) is int and 1<=minimum<=maximum
            and max(2,minimum)<=count<=min(capacity(party),maximum))
    definition = raid_definition(identity)
    return definition is not None and definition['minimum'] <= count <= min(capacity(party), definition['maximum'])


def solo_admission(identity):
    """An ungrouped entrance must honor the selected native variant's bounds."""
    if not route_catalog().supports(identity):return False
    native=client_data().dungeon(identity)
    return native.get('m_MinPlayerCount',1)<=1<=native.get('m_MaxPlayerCount',4)


def waiting_size(party,identity):
    """A waiting room may recruit up to capacity before reaching the entry minimum."""
    if not route_catalog().supports(identity):return False
    count=len(party['members']);raid=raid_definition(identity)
    if party.get('raid_party'):return raid is not None and 1<=count<=min(capacity(party),raid['maximum'])
    native=client_data().dungeon(identity)
    if raid is not None or 1 in native.get('DUNGEON_CHECK_CONDITION',{}).values():return False
    # The waiting roster is a four-person party even when its selected
    # dungeon admits two. Admission_size enforces that dungeon's actual cap.
    # A created/stopped advert may retain only its leader while selecting.
    return 1<=count<=capacity(party)


def entry_size(session,identity):
    application=getattr(session,'application',None)
    party=application.world.party_of.get(session) if application is not None else None
    return admission_size(party,identity) if party is not None else solo_admission(identity)
