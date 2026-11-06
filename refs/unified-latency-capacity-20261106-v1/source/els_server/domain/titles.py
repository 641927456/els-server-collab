"""Pinned title definitions. Ownership comes exclusively from server storage."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    path=PROJECT_ROOT/'els_server/data/titles.json';raw=path.read_bytes()
    manifest=json.loads(path.with_name('titles.manifest.json').read_text(encoding='utf8'))
    data=json.loads(raw)
    if (manifest['schema_version']!=1 or manifest['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=manifest['sha256'] or data['client_sha256']!=CLIENT_SHA
        or data['catalog_sha256']!=client_data().manifest['catalog_sha256'] or len(data['titles'])!=932):
        raise ValueError('Title catalog identity')
    return data

def definition(title):
    if type(title) is not int or str(title) not in catalog()['titles']:raise ValueError('Unknown title')
    return catalog()['titles'][str(title)]

def eligible(character,title):
    if not {'level','unit_type','unit_class'}<=character.keys():raise ValueError('Incomplete title character')
    t=definition(title)
    if not (character['level']>=t['m_iOpenLevel'] and t['m_eUnitType'] in (0,character['unit_type'])
            and t['m_eUnitClass'] in (0,character['unit_class'])):return False
    mode=t.get('m_eTitleCanUseType',0)
    if mode==0:return True
    values=tuple(v for k,v in t.get('m_vecTitleCanUseValue',{}).items() if str(k)!='0' and v is not None)
    # Current pinned source uses exactly one value for all31 guarded titles.
    if len(values)!=1 or type(values[0]) is not int or values[0]<=0:return False
    if mode==1:return character['level']>=values[0] # TCUT_LEVEL
    if mode==2: # TCUT_QUEST_CLEAR: the selected character, never a sibling.
        completed=character.get('title_completed_quests',())
        return isinstance(completed,(tuple,list,set,frozenset)) and values[0] in completed
    return False

def scope(character,title):
    t=definition(title)
    return ('account',character['account_id']) if t['m_bAccountTitle'] else ('character',character['uid'])

def attributes(character):
    title=character.get('title',0)
    if not title:return (0.,)*7
    if not eligible(character,title):raise ValueError('Ineligible active title')
    t=definition(title)
    return tuple(float(t.get(k,0)) if k else 0. for k in ('m_iBaseHP','m_iAtkPhysic','m_iAtkMagic',None,None,'m_iDefPhysic','m_iDefMagic'))
