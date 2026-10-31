"""Current region task definitions and native level/type/quest entrance gates.

Quest completion comes from the shared persisted quest engine. This module
does not grant completion from a previous clear or from opening a map panel.
"""
import functools,hashlib,json
from els_server.game_data import CLIENT_SHA,DATA_DIR
from els_server.paths import PROJECT_ROOT

def sequence(row):
    return tuple(v for k,v in sorted(row.items(),key=lambda kv:int(kv[0])) if str(k)!='0' and v is not None)

class RegionQuestCatalog:
    def __init__(self,directory=DATA_DIR):
        raw=(directory/'region_quests.json').read_bytes()
        m=json.loads((directory/'region_quests.manifest.json').read_text(encoding='utf8'))
        if (m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA
            or hashlib.sha256(raw).hexdigest()!=m['payload_sha256']):raise ValueError('Region task catalog identity')
        if hashlib.sha256((PROJECT_ROOT/'config/dungeon_scope.json').read_bytes()).hexdigest()!=m['scope_sha256']:
            raise ValueError('Region dungeon scope changed; rebuild region tasks')
        self.data=json.loads(raw);self.manifest=m
        from els_server.game_data import client_data
        for item in self.data['reward_definitions']:
            if (hashlib.sha256(client_data().item(item['template'])['record']).hexdigest()!=item['record_sha256']
                or item['native']!={'ok':1,'consumed':304}):raise ValueError('Region reward evidence')
        for key in ('regions','dungeons','quests','subquests'):
            if len(self.data[key])!=m[key]:raise ValueError('Region catalog count')
        for row in self.data['quests'].values():
            q=row['definition']
            if q['m_bRepeat'] or q['m_bIsTimeEvent']:raise ValueError('Repeating/event region entry task')
            for i in sequence(q['m_vecSubQuest']):
                if str(i) not in self.data['subquests']:raise ValueError('Missing region subtask')
            for i in sequence(q['QuestCondition'].get('m_vecBeforeQuestID',{})):
                if i and str(i) not in self.data['quests']:raise ValueError('Missing region prerequisite')

    def quest_definitions(self):
        return {int(i):row['definition'] for i,row in self.data['quests'].items()}

    def subquest_definitions(self):
        return {int(i):row['definition'] for i,row in self.data['subquests'].items()}

    def region_allowed(self,region,character,completed):
        if type(region) is not int:return False
        row=self.data['regions'].get(str(region))
        if row is None:return False
        r=row['requirement'];level=character['level'];unit_type=character['unit_type']
        types=sequence(r.get('EnableUnitType',{}))
        if types and unit_type not in types:return False
        minimum=max([r.get('RequireUnitLevel',1),*[v['MIN_LEVEL'] for v in r.get('EnableUnitTypeLevel',{}).values() if v['UNIT_TYPE']==unit_type]])
        if not minimum<=level<=r.get('LimitUnitLevel',99):return False
        return not r.get('RequireQuestID') or r['RequireQuestID'] in completed

    def dungeon_allowed(self,dungeon,character,completed):
        if type(dungeon) is not int:return False
        # These current special entrances share region10011's level70 gate,
        # but each native dungeon definition requires level99. Reuse the
        # source minimum at both selection and actual admission; no new
        # rewards, tickets, matching or client-side calculation are added.
        if dungeon in (34310,41131,120010):
            from els_server.game_data import client_data
            if character['level']<client_data().dungeon(dungeon)['m_MinLevel']:return False
        if dungeon==41131:
            from els_server.domain.character_rules import CLASSES
            if CLASSES[character['unit_class']]['stage']!=3:return False
        regions=self.data['dungeons'].get(str(dungeon))
        if not regions:return False
        # Some special regions have no AddLocalMapRequireInfo registration.
        # Only current positive dungeon registrations get that default.
        return any(str(i) not in self.data['regions'] or self.region_allowed(i,character,completed) for i in regions)

@functools.lru_cache(maxsize=1)
def region_catalog():return RegionQuestCatalog()

def account_dungeon_allowed(account,identity):
    character=account.character()
    # Legacy protocol fixtures have no persistent role/quest system. The
    # integrated server always enables Characters before accepting players.
    if character is None:return True
    if account.store is None:return False
    from els_server.storage.seal_quests import QuestState
    completed=QuestState(account.store.path,account.uid,account_id=account.account_id).completed()
    from els_server.domain.dungeon_routes import route_catalog
    internal=next((p for p in route_catalog()._data.get('challenges',[]) if any(n['dungeon']==identity for n in p['nodes'])),None)
    if internal:
        from els_server.game_data import client_data
        if character['level']<client_data().dungeon(identity).get('m_MinLevel',1):return False
        identity=(34120+internal['phase']*10) if internal['challenge']==4 else (34540+internal['phase']*10)
    if not region_catalog().dungeon_allowed(identity,character,completed):return False
    from els_server.domain.dungeon_rotation import tower_encounter,selected
    return not tower_encounter(identity) or selected(identity,account)
