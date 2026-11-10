"""Approved anniversary draw and original fixed marriage/resurrection rewards."""
from functools import lru_cache
from pathlib import Path
import hashlib,json

DATA_SHA='a80520334319ac3d7300c00f10b35432667349c24749fc1551d6784bffd582a8'
POLICY='relationship-boxes-20261106-v1'


@lru_cache(maxsize=1)
def data():
    from els_server.game_data import CLIENT_SHA,client_data
    raw=(Path(__file__).resolve().parents[1]/'data/relationship_boxes.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Relationship box policy identity')
    d=json.loads(raw);c=client_data()
    if d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256'] or d['policy']!=POLICY:
        raise ValueError('Relationship box current client identity')
    for row in d['readers']:
        item=c.item(row['template'])
        if (item['metadata']!=row['metadata']or item['name']!=row['name']
                or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):
            raise ValueError('Relationship box original reader identity')
    for template,give,count in ((160762,-1,0),(111087,0,3),(277154,0,0)):
        r=d['native_rules'][str(template)]
        if (r['m_ItemID']!=template or r['m_iGiveCount']!=give or r.get('m_iRessurectionCount',0)!=count
                or r['m_UseCondition']!={'global':'USE_CONDITION.UC_ANYONE'}
                or r['m_KeyItemID']!=0 or r['m_RequiredKeyCount']!=0):
            raise ValueError('Relationship box original use mode')
    expected=[dict(template=t,quantity=q,weight=1)for t,q in
              ((77200,1),(111087,1),(109945,5),(109955,3),*((t,1)for t in range(130047,130054)))]
    if d['pool']!=expected:raise ValueError('Approved eleven equal anniversary outputs')
    return d


def definitions():return tuple(data()['readers'])


def entries():
    d=data()
    return (dict(template=160762,selection_count=0,random=True,draw_total=11,
                 relationship_box=True,entries=d['pool']),
            dict(template=111087,selection_count=0,resurrection_gain=3,
                 relationship_box=True,entries=()),
            dict(template=277154,selection_count=0,quick_start_box=True,
                 relationship_box=True,entries=d['fixed_wedding']))


def authorize_output(template,source):
    if source is None:return False
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!=POLICY:return False
    if (source.kind!='box' or identity['definition_sha256']!=DATA_SHA
            or identity['owner']!=source.owner or identity['box']!=160762
            or identity['output'] not in data()['pool']):
        raise ValueError('Anniversary owned box output identity')
    output=identity['output']
    source.validate_plan([dict(template=output['template'],metadata=2,group=4,quantity=output['quantity'])])
    if output['template']!=template:raise ValueError('Anniversary output outside exact committed draw')
    return True
