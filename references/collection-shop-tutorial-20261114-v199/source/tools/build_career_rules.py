"""Join native product names, class restrictions and advancement routes."""
import json,re,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'analysis/client-6c6b5180'
def read(path):return json.loads(path.read_text(encoding='utf8'))
def build():
    rows=read(BASE/'native-job-shop-catalog.json')['rows']
    route_path=ROOT/'analysis/character-career-20261014/native-career-routes.json'
    classes={str(r['id']):r for r in read(route_path)['rows']}
    names={r['name']:r['id'] for r in classes.values() if r['stage']>0}
    assert len(names)==180
    by_route={(r['unit_type'],r['line'],r['stage']):r['id'] for r in classes.values()}
    assert len(by_route)==195
    rules={};unresolved=[]
    for row in rows:
        name=row['name'];kind=row['job_kind'];raw=bytes.fromhex(row['record_hex']);target=None
        if kind.startswith('advancement_'):
            stage=int(kind[-1]);stem=name[4:]
            if stage==1:
                candidates=[v for n,v in names.items() if stem.startswith(n) and classes[str(v)]['stage']==stage]
            else:
                parent=classes[str(raw[211])]
                assert parent['stage']==stage-1
                candidates=[by_route[(parent['unit_type'],parent['line'],stage)]]
            if len(candidates)!=1:unresolved.append((row['id'],name,candidates));continue
            target=candidates[0]
        elif kind in ('class_change','transcendence_change','master_change'):
            stem=name.removeprefix('[领导者]').removesuffix('（超越）').removesuffix('转职变更券')
            target=names.get(stem)
        elif kind=='master_advancement':target=names.get(name.removeprefix('觉悟的标志<').removesuffix('>'))
        elif kind=='transcendence_book':target=0
        if target is None:unresolved.append((row['id'],name,[]));continue
        # Career purchases use category/stage conditions. The item-use level
        # byte is 99 on newer first/second-class tickets despite their native
        # purchase descriptions requiring only that class stage (70 for Trans.).
        level=raw[209]
        if kind=='class_change':level=99 if classes[str(target)]['stage']==3 else 0
        elif kind=='transcendence_change':level=70
        rules[str(row['id'])]=dict(kind=kind,target=target,required_class=raw[211],unit_type=classes[str(target)]['unit_type'] if target else 0,level=level,name=name,resource_unit_type=raw[210])
    if unresolved:raise ValueError(unresolved)
    assert len(rules)==541
    # Item restrictions supply all 120 first->second / second->third edges.
    edges={str(r['target']):r['required_class'] for r in rules.values() if r['kind'].startswith('advancement_')}
    assert len(edges)==180
    for target,parent in edges.items():
        a,b=classes[target],classes[str(parent)]
        assert a['base_class']==b['base_class'] and a['stage']==b['stage']+1
    out=dict(client_sha256=read(BASE/'native-job-shop-catalog.json')['client_sha256'],rules=rules,parents=edges,
             source='Native UnitManager class names plus class stage/base/line tables (478e120/48a1be0/48a22a0); advancement parent from item byte211. Class-change restriction bytes are not target IDs.',
             route_evidence_sha256=hashlib.sha256(route_path.read_bytes()).hexdigest())
    dest=ROOT/'els_server/data/careers.json';dest.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
    print('Validated',len(rules),'native career items and',len(edges),'advancement edges.')
if __name__=='__main__':build()
