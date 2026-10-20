"""Prepare a reviewed two-card increment without running dashboard history."""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT=Path('G:/els').resolve()
ALLOWED_CARDS={'boxes','quests'}
TEXT_FIELDS={'summary','remaining','summary_short','remaining_short'}
META_FIELDS={'local_release','local_manifest_sha256','local_manifest_sha','local_business_files','updated_at'}
SOURCE_NAMES={'data':'progress-data.json','template':'dashboard.html','preview':'server-preview.html','shorts':'card-summaries.json'}

def require(condition,message):
    if not condition:raise ValueError(message)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def read_json(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def html_data(html):
    matches=list(re.finditer(r'^const DATA=',html,re.M))
    require(len(matches)==1,'Exactly one DATA assignment required')
    value,end=json.JSONDecoder().raw_decode(html,matches[0].end())
    require(re.match(r';\s*\nconst \$=',html[end:]) is not None,'DATA suffix changed')
    return value

def render(template,data):
    require(template.count('/*__DATA__*/')==1,'Exactly one template DATA placeholder required')
    require('data-els-progress-dashboard="1"' in template,'Wrong dashboard template')
    result=template.replace('/*__DATA__*/',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
    require(html_data(result)==data,'Rendered DATA differs')
    return result

def prepare(source,facts_path,expected_facts_sha,output):
    source=source.resolve();output=output.resolve();facts_path=facts_path.resolve()
    require(output.is_relative_to(ROOT/'analysis'),'Output must be a private analysis directory')
    require(not output.is_relative_to(ROOT/'analysis/coordination-20261015'),'Shared dashboard output prohibited')
    require(not output.exists(),'Output must be new, never overwrite a preview')
    watched={}
    def pinned(path,sha):
        path=path.resolve();raw=path.read_bytes()
        require(digest(raw)==sha,'Source SHA mismatch: '+str(path))
        watched[path]=sha
        return raw
    facts_raw=pinned(facts_path,expected_facts_sha)
    facts=json.loads(facts_raw.decode('utf-8-sig'))
    require(facts.get('schema_version')==1,'Facts schema')
    require(set(facts)=={'schema_version','sources','changes','metadata','installation','evidence_sources'},'Facts scope keys')
    require(set(facts['sources'])==set(SOURCE_NAMES)|{'public_builder'},'Source scope')
    raw={k:pinned(source/name,facts['sources'][k]) for k,name in SOURCE_NAMES.items()}
    data=json.loads(raw['data'].decode('utf-8-sig'));shorts=json.loads(raw['shorts'].decode('utf-8-sig'))
    template=raw['template'].decode('utf-8-sig').replace('\r\n','\n')
    preview=raw['preview'].decode('utf-8-sig').replace('\r\n','\n')
    require(html_data(preview)==data,'Snapshot JSON and HTML disagree')
    require(render(template,data)==preview,'Existing preview/template relationship changed')
    require(set(facts['changes'])==ALLOWED_CARDS,'Only boxes and quests are allowed')
    require(set(facts['metadata'])==META_FIELDS,'Metadata scope')
    install=facts['installation']
    require(set(install)=={'receipt_path','receipt_sha256','pointer_sha256','manifest_sha256'},'Installation scope')
    receipt_path=Path(install['receipt_path']).resolve()
    require(receipt_path.is_relative_to(ROOT/'analysis'),'Receipt must be an analysis artifact')
    receipt=json.loads(pinned(receipt_path,install['receipt_sha256']))
    pointer=json.loads(pinned(ROOT/'releases/local/current.json',install['pointer_sha256']))
    require(receipt.get('ok') is True and receipt.get('channel')=='local','Local completion not successful')
    require(receipt.get('observation_seconds',0)>=120,'Local observation incomplete')
    for field in ('all_typed_rows_and_schema_preserved','dual_SQLite_backup_API','no_client_behavior_changes','online_game_unchanged'):
        require(receipt.get(field) is True,'Incomplete installation protection: '+field)
    require((pointer['release'],pointer['manifest_sha256'])==(receipt['release'],receipt['manifest_sha256']),'Pointer and completion differ')
    manifest=Path(receipt['local_manifest_path']).resolve()
    require(manifest.is_relative_to(ROOT/'releases/local'/pointer['release']),'Manifest outside installed release')
    require(install['manifest_sha256']==pointer['manifest_sha256'],'Manifest source binding differs')
    manifest_raw=pinned(manifest,install['manifest_sha256'])
    require(len(json.loads(manifest_raw)['files'])==receipt['business_files_verified'],'Installed business count differs')
    expected_metadata=dict(local_release=receipt['release'],local_manifest_sha256=receipt['manifest_sha256'],local_manifest_sha=receipt['manifest_sha256'],local_business_files=receipt['business_files_verified'])
    require(type(expected_metadata['local_business_files']) is int,'Business count type')
    for field,value in expected_metadata.items():
        require(type(data.get(field)) is type(value),'Existing metadata type changed: '+field)
        require(facts['metadata'][field]==value,'Metadata is not derived from receipt: '+field)
    require(type(facts['metadata']['updated_at']) is str,'Timestamp type')
    datetime.datetime.strptime(facts['metadata']['updated_at'],'%Y-%m-%d %H:%M:%S')
    evidence={}
    for entry in facts['evidence_sources']:
        require(set(entry)=={'label','path','sha256'},'Evidence source fields')
        path=Path(entry['path']).resolve()
        require(path.is_relative_to(ROOT/'analysis'),'Evidence outside analysis')
        pinned(path,entry['sha256'])
        require(type(entry['label']) is str and 0<len(entry['label'])<=200,'Evidence label')
        require(entry['sha256'] not in evidence,'Duplicate evidence SHA')
        evidence[entry['sha256']]=dict(label=entry['label'],path=path.as_uri(),sha256=entry['sha256'])
    result=copy.deepcopy(data);new_shorts=copy.deepcopy(shorts)
    require(len({c['id'] for c in data['systems']})==len(data['systems']),'Duplicate card identity')
    cards={c['id']:c for c in result['systems']}
    for key,patch in facts['changes'].items():
        require(set(patch)==TEXT_FIELDS|{'evidence_sha256'},'Card fields outside reviewed text/evidence scope')
        require(key in cards,'Missing target card')
        for field in TEXT_FIELDS:
            text=patch[field]
            require(type(text) is str and len(text)>0,'Non-text or empty card field')
            if field.endswith('_short'):require(len(text)<=64,'Short field exceeds64 characters')
            cards[key][field]=text
        require(type(patch['evidence_sha256']) is list,'Evidence references type')
        for sha in patch['evidence_sha256']:
            require(sha in evidence,'Evidence reference not independently pinned')
            if evidence[sha] not in cards[key]['evidence']:cards[key]['evidence'].append(evidence[sha])
        new_shorts[key]=dict(remaining_sha256=digest(patch['remaining'].encode('utf8')),remaining_short=patch['remaining_short'])
    result.update(facts['metadata'])
    before=copy.deepcopy(data);after=copy.deepcopy(result)
    for snapshot in (before,after):
        for field in META_FIELDS:snapshot.pop(field,None)
        for card in snapshot['systems']:
            if card['id'] in ALLOWED_CARDS:
                for field in TEXT_FIELDS|{'evidence'}:card.pop(field,None)
    require(before==after,'Unreviewed card/item/score or metadata changed')
    html=render(template,result)
    # Export only with the existing project public HTML converter. No publisher import.
    public_builder=ROOT/'analysis/coordination-20261015/progress-web-01a14442/build_public.py'
    pinned(public_builder,facts['sources']['public_builder'])
    spec=importlib.util.spec_from_file_location('_existing_public_dashboard',public_builder)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for path,sha in watched.items():require(digest(path.read_bytes())==sha,'Concurrent source change: '+str(path))
    output.mkdir(parents=True,exist_ok=False)
    (output/'progress-data.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (output/'card-summaries.json').write_text(json.dumps(new_shorts,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (output/'server-preview.html').write_text(html,encoding='utf8')
    exported=module.build(output/'server-preview.html',output/'public-preview.html')
    require(html_data((output/'public-preview.html').read_text(encoding='utf8'))['local_release']==receipt['release'],'Public local release differs')
    for path,sha in watched.items():require(digest(path.read_bytes())==sha,'Concurrent source change after rendering: '+str(path))
    report=dict(ok=True,isolated_output=True,shared_files_written=0,network_operations=0,history_executed=False,
                changed_cards=sorted(ALLOWED_CARDS),allowed_metadata=sorted(META_FIELDS),scores_items_and_other_cards_preserved=True,
                short_hashes_synchronized=True,local_release=receipt['release'],local_observation_seconds=receipt['observation_seconds'],
                public_export=exported,sources=[dict(path=str(p),sha256=s) for p,s in watched.items()],
                files=[dict(path=p.name,sha256=digest(p.read_bytes())) for p in sorted(output.iterdir()) if p.is_file()])
    (output/'incremental-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return report

def main(default_source,argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviewed-card-update',type=Path,required=True)
    parser.add_argument('--facts-sha256',required=True)
    parser.add_argument('--incremental-output',type=Path,required=True)
    parser.add_argument('--dashboard-source',type=Path,default=default_source)
    args=parser.parse_args(argv)
    report=prepare(args.dashboard_source,args.reviewed_card_update,args.facts_sha256,args.incremental_output)
    print(json.dumps(dict(ok=True,path=str(args.incremental_output),history_executed=False,shared_files_written=0)))
    return 0
