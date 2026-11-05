"""Exact original stamp registrations; no acquisition pools or retail stack claim."""
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA
from els_server.paths import PROJECT_ROOT

@functools.lru_cache(maxsize=1)
def definitions():
    raw=(PROJECT_ROOT/'els_server/data/item_sealing.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='c733c9fc506b3397190b2146505fbd1de98a2d56ec9fe9d7d13ff9e0e3eb8c31':
        raise ValueError('Item sealing data changed')
    data=json.loads(raw);native=data['native'];source=client_data()
    if (data['schema_version']!=1 or data['client_sha256']!=CLIENT_SHA or
            data['source_catalog_sha256']!=source.manifest['catalog_sha256'] or
            data['source_kim_sha256']!='a3bcc9c926b19aa36f1c737ca53993b23da11c372bfd5adf3d740dc0b691ab8e' or
            data['source_resource_sha256']!='69d30716332a9fd20297af5f5108f57356613d12f86684dc4b594d09b4cfa85d' or
            not native['all_passed'] or native['live_process_access'] or native['outside_candidate_modules'] or
            native['image_sha256']!='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229' or
            len(data['original_rules'])!=62 or len(data['items'])!=49 or len(native['rows'])!=98):
        raise ValueError('Item sealing original provenance')
    rules={r['template']:(r['grade'],r['target_item_type']) for r in data['original_rules']}
    proof={(r['template'],r['count']):r for r in native['rows']};result={}
    for row in data['items']:
        t=row['template'];d=source.item(t)
        if (t in result or hashlib.sha256(d['record']).hexdigest()!=row['record_sha256'] or
                (d['item_type'],d['metadata'],row['group'],row['max_stack'])!=(7,row['metadata'],4,99) or
                row['metadata'] not in (0,2) or ((d['flags4']>>20)&15)!=row['grade'] or
                rules.get(t)!=(row['grade'],row['target_item_type']) or row['target_item_type'] not in (0,2)):
            raise ValueError('Item sealing stamp definition')
        for n in (1,99):
            p=proof.get((t,n),{})
            if (p.get('metadata'),p.get('group'),p.get('consumed'),p.get('instance_count'))!=(row['metadata'],4,304,n):
                raise ValueError('Item sealing native codec witness')
        result[t]=row
    if set(rules)-set(result)!=set(data['missing_templates']) or len(data['missing_templates'])!=13:
        raise ValueError('Missing original stamp identity coverage')
    return result

def accepts(stamp_template,target_record):
    row=definitions().get(stamp_template)
    if row is None:return False
    grade=(int.from_bytes(target_record[4:8],'little')>>20)&15
    typ=(int.from_bytes(target_record[8:12],'little')>>3)&31
    # Original6BE260 dispatches IT_HOUSING to its own SealItemInfo map.
    # These generic EventSealItemData registrations never select housing.
    if typ==16:return False
    return row['grade']==grade and row['target_item_type'] in (0,typ)
