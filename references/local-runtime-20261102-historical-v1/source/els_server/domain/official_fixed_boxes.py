"""Two official fixed boxes that ship without a client ItemGroup table.

118655 [阿莉尔]白境机甲防具宝箱 is the reward of the official epic quest
"进入瑟芬提姆" (region_quests 27560). The official guide states every character
receives its own white-realm mech armour; the client's own items carry one
four-piece armour set per family (118381-118444), and Lu/Ciel additionally has
the Ciel/minor set marked in flags8. 117542 浓缩的艾尔精髓袋子（20个）is the
Ariel shop bag whose official description opens into 20 浓缩的艾尔精髓 (78931).
"""
import functools,hashlib,json,struct
from pathlib import Path
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA

BOXES=frozenset((117542,118655))
POLICY='official-fixed-boxes-20261101-v1'
COHORT_KEYS=frozenset('%d:0'%f for f in range(1,16))|{'10:1'}
EQUIP_SLOTS=(8,9,10,11)


@functools.lru_cache(maxsize=1)
def catalog():
    path=PROJECT_ROOT/'els_server/data/official_fixed_boxes.json';raw=path.read_bytes()
    manifest=json.loads(path.with_suffix('.manifest.json').read_text(encoding='utf8'));data=json.loads(raw);client=client_data()
    if (hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256'] or manifest['schema_version']!=1
        or manifest['client_sha256']!=CLIENT_SHA or data['schema_version']!=1 or data['policy']!=POLICY
        or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client.manifest['catalog_sha256']):
        raise ValueError('Official fixed box definition identity')
    from els_server.domain.inventory_items import LOCAL_MAX_STACK
    provenance=data['provenance']
    if (set(provenance['official'])!=set(map(str,BOXES))or set(provenance['sources'])!=set(map(str,BOXES))
        or not all(isinstance(v,str)and v for v in (*provenance['official'].values(),*provenance['sources'].values()))
        or not provenance['derivation']
        or (provenance['client_files_modified'],provenance['client_files_added'],provenance['new_game_hooks'],provenance['new_sources'])!=(0,0,0,0)):
        raise ValueError('Official fixed box provenance')
    readers={}
    for row in data['readers']:
        template=row['template'];item=client.item(template);record=item['record']
        if (item['name'],item['metadata'],item['equip_position'])!=(row['name'],row['metadata'],row['equip_position']):
            raise ValueError('Official fixed box reader identity')
        if hashlib.sha256(record).hexdigest()!=row['record_sha256']:raise ValueError('Official fixed box reader record')
        if item['metadata']==1:
            if (row['group'],row['max_stack'],item['item_type'])!=(1,1,2)or item['equip_position']not in EQUIP_SLOTS:
                raise ValueError('Official fixed box armour reader class')
        elif (row['group'],row['max_stack'],item['item_type'])!=(4,struct.unpack_from('<i',record,0x10)[0],7):
            raise ValueError('Official fixed box material reader class')
        if template in readers:raise ValueError('Official fixed box duplicate reader')
        readers[template]=MappingProxyType(row)
    boxes={}
    for row in data['boxes']:
        template=row['template'];item=client.item(template)
        if (template not in BOXES or template in boxes or item['name']!=row['name'] or item['item_type']!=7
            or item['metadata']!=row['metadata'] or item['equip_position']!=0 or row['group']!=4
            or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):
            raise ValueError('Official fixed box original identity')
        produced=[]
        if row['mode']=='fixed':
            if set(row)-{'template','name','item_type','metadata','group','mode','record_sha256','entries'}or len(row['entries'])!=1:
                raise ValueError('Official fixed box fixed scope')
            for entry in row['entries']:
                output=readers.get(entry['template'])
                if output is None or not 1<=entry['quantity']<=LOCAL_MAX_STACK:raise ValueError('Official fixed box fixed output')
                produced.append(entry['template'])
        elif row['mode']=='cohorts':
            if set(row)-{'template','name','item_type','metadata','group','mode','record_sha256','cohorts'}or set(row['cohorts'])!=COHORT_KEYS:
                raise ValueError('Official fixed box cohort scope')
            for key,members in row['cohorts'].items():
                family,minor=map(int,key.split(':'))
                slots=set()
                if len(members)!=4 or len(set(members))!=4:raise ValueError('Official fixed box cohort set')
                for member in members:
                    output=readers.get(member)
                    if output is None or output['metadata']!=1:raise ValueError('Official fixed box cohort output')
                    record=client.item(member)['record']
                    if record[0xd2]!=family or bool(record[8]&4)!=bool(minor):raise ValueError('Official fixed box cohort branch')
                    slots.add(record[0xd5]);produced.append(member)
                if slots!=set(EQUIP_SLOTS):raise ValueError('Official fixed box cohort slots')
        else:raise ValueError('Official fixed box mode')
        if not set(produced)<=set(readers):raise ValueError('Official fixed box unregistered output')
        boxes[template]=MappingProxyType(row)
    if set(boxes)!=set(BOXES)or len(readers)!=len(data['readers']):raise ValueError('Official fixed box finite scope')
    return MappingProxyType(dict(sha=manifest['payload_sha256'],boxes=MappingProxyType(boxes),
        readers=tuple(readers[t]for t in sorted(readers)),reader_map=MappingProxyType(readers)))


def boxes():return catalog()['boxes']
def readers():return catalog()['readers']
def definition_sha():return catalog()['sha']


def _branch(character):
    if not isinstance(character,dict)or type(character.get('unit_class'))is not int:raise ValueError('Official fixed box character')
    unit=client_data().unit(character['unit_class']);family=unit.get('unitType')
    if type(family)is not int or not 1<=family<=15:raise ValueError('Official fixed box character family')
    active=character.get('luciel_active_unit',0)if family==10 else 0
    if active not in (0,1):raise ValueError('Official fixed box character active unit')
    return family,active


def outputs_for(template,character):
    row=boxes().get(template)if type(template)is int else None
    if row is None:raise ValueError('Unknown official fixed box')
    if row['mode']=='fixed':
        return tuple(dict(template=e['template'],quantity=e['quantity'])for e in row['entries'])
    family,active=_branch(character)
    members=row['cohorts'].get(str(family)+':'+str(active))
    if members is None:raise ValueError('Official fixed box has no matching character branch')
    return tuple(dict(template=member,quantity=1)for member in members)


def preview(template,character):
    row=boxes()[template];outputs=outputs_for(template,character)
    return dict(template=template,name=row['name'],selection_count=0,entries=outputs,official_fixed_box=True),outputs


def plan_for(template,character):
    reader_map=catalog()['reader_map']
    return [dict(template=output['template'],metadata=reader_map[output['template']]['metadata'],
                 group=reader_map[output['template']]['group'],quantity=output['quantity'])for output in outputs_for(template,character)]
