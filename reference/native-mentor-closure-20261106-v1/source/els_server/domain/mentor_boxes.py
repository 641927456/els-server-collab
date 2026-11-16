"""One approved five-stone draw and two original fixed resurrection counters."""
import functools,hashlib,json
from pathlib import Path

DATA_SHA='d7dffc3951b503f934cd57fbac9898ef548a38c5b601391fde6b9d4b6d2fa3da'


@functools.lru_cache(maxsize=1)
def entries():
    raw=(Path(__file__).resolve().parents[1]/'data/mentor_boxes.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Mentor box definition identity')
    data=json.loads(raw)
    from els_server.domain.mentor_quests import catalog
    if (data['stone_box']!=132812 or data['probability_authorization_sha256']!=catalog()['stone_box']['authorization_sha256']
            or data['pool']!=[dict(template=t,quantity=1,weight=2000)for t in(132198,132202,132203,132204,132205)]):
        raise ValueError('Mentor stone box approved pool')
    rows=[]
    for template,gain in((132840,10),(90000746,20),(132812,0)):
        native=data['native_random_rules'][str(template)]
        if (native['m_ItemID']!=template or native['m_KeyItemID']!=0 or native['m_RequiredKeyCount']!=0
                or native.get('m_iRessurectionCount',0)!=gain
                or native['m_iGiveCount']!=(-1 if template==132812 else 0)
                or native['m_UseCondition']!={'global':'USE_CONDITION.UC_ANYONE'}):
            raise ValueError('Mentor native box use rule')
        if template==132812 and native['1']['m_iItemGroupID']!=14970:raise ValueError('Mentor native box group')
        rows.append(dict(template=template,selection_count=0,entries=data['pool']if not gain else (),
            mentor_box=True,random=not gain,resurrection_gain=gain))
    return tuple(rows)
