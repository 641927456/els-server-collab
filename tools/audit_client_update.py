"""Read-only client update snapshots, catalog differences and contract checks."""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor'))
from client_compatibility import inventory,load_registry,check_client

CATALOG_TABLES={'items':('id',),'units':('class_id',),'skills':('id',),
                'skill_tree':('class_id','skill_id'),'dungeons':('id',),
                'experience':('level',),'resources':('name',),'rules':('resource','ordinal')}

def catalog_identity(directory):
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf8'))
    path=directory/'catalog.sqlite3'
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    if manifest.get('schema_version')!=1 or manifest.get('catalog_sha256')!=sha:
        raise ValueError('Catalog manifest/schema/checksum mismatch')
    return manifest

def catalog_compare(before_dir,after_dir,limit=100):
    """Read definition catalogs only; never opens or migrates a player database."""
    if not 1<=limit<=200:raise ValueError('Catalog diff sample bound')
    before_dir=before_dir.resolve();after_dir=after_dir.resolve()
    a=catalog_identity(before_dir);b=catalog_identity(after_dir)
    def connect(directory):
        db=sqlite3.connect((directory/'catalog.sqlite3').as_uri()+'?mode=ro&immutable=1',uri=True)
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF');return db
    left=connect(before_dir);right=connect(after_dir)
    try:
        tables=[]
        for name,keys in CATALOG_TABLES.items():
            schemas=[db.execute('PRAGMA table_info('+name+')').fetchall() for db in (left,right)]
            if any(not s for s in schemas):raise ValueError('Missing definition catalog table: '+name)
            if [r[1:6] for r in schemas[0]]!=[r[1:6] for r in schemas[1]]:
                tables.append(dict(table=name,status='schema-changed',before_columns=[r[1:3] for r in schemas[0]],after_columns=[r[1:3] for r in schemas[1]]));continue
            columns=[r[1] for r in schemas[0]]
            # Only constants from the allowlist above are SQL identifiers.
            indices=[columns.index(k) for k in keys]
            def key(row):return tuple(row[i] for i in indices)
            lc=iter(left.execute('SELECT * FROM '+name+' ORDER BY '+','.join(keys)))
            rc=iter(right.execute('SELECT * FROM '+name+' ORDER BY '+','.join(keys)))
            x=next(lc,None);y=next(rc,None);counts=dict(added=0,removed=0,changed=0);samples={k:[] for k in counts}
            while x is not None or y is not None:
                if x is None or (y is not None and key(y)<key(x)):
                    op='added';identity=key(y);y=next(rc,None)
                elif y is None or key(x)<key(y):
                    op='removed';identity=key(x);x=next(lc,None)
                else:
                    identity=key(x);op='changed' if x!=y else None;x=next(lc,None);y=next(rc,None)
                if op:
                    counts[op]+=1
                    if len(samples[op])<limit:samples[op].append(identity)
            tables.append(dict(table=name,status='compared',counts=counts,id_samples=samples))
        closures=[]
        for relation,query in [('skill_tree->units','SELECT count(*) FROM skill_tree t WHERE NOT EXISTS (SELECT 1 FROM units u WHERE u.class_id=t.class_id)'),
                               ('skill_tree->skills','SELECT count(*) FROM skill_tree t WHERE NOT EXISTS (SELECT 1 FROM skills s WHERE s.id=t.skill_id)')]:
            try:closures.append(dict(relation=relation,unresolved=right.execute(query).fetchone()[0]))
            except sqlite3.DatabaseError as e:closures.append(dict(relation=relation,status='schema-review-required',error=str(e)))
        return dict(schema_version=1,kind='client-catalog-update-review',before_catalog_sha256=a['catalog_sha256'],
            after_catalog_sha256=b['catalog_sha256'],before_client_sha256=a['client_sha256'],after_client_sha256=b['client_sha256'],
            tables=tables,dependency_closure=closures,auto_approved=False,player_state_accessed=False,
            limitations=['Only units/skills references are checked here. Other enum/item/dungeon/quest/native-record dependencies require their original validators and protocol replay.',
                         'Removed/changed item IDs require saved-item compatibility review before release; this report never rewrites saved player data.'])
    finally:left.close();right.close()

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')

def identity(snapshot):
    return hashlib.sha256(canonical(snapshot)).hexdigest()

def compare(before,after):
    if before.get('schema_version')!=1 or after.get('schema_version')!=1:
        raise ValueError('Unsupported inventory schema')
    if before.get('kind')!='client-update-inventory' or after.get('kind')!='client-update-inventory':
        raise ValueError('Expected inventory documents')
    reasons=[];tasks=[]
    if not after.get('complete'):
        reasons.append('inventory-incomplete');tasks.append('Resolve missing/opaque/invalid directories and repeat the read-only inventory.')
    if not before.get('complete'):
        reasons.append('baseline-incomplete');tasks.append('Use a complete retained baseline before interpreting a diff.')
    if after.get('missing_catalog_resources'):
        reasons.append('key-resource-coverage-incomplete')
        tasks.append('Verify missing/renamed key-resource definitions and native archive precedence before generating server data.')
    exe_changed=before['client']['sha256']!=after['client']['sha256']
    if exe_changed:
        reasons.append('native-contract-unreviewed')
        tasks.append('Compare native readers/callers, structure layout, codec, bootstrap and lifecycle against the old build; preserve source hashes and independent evidence. Do not copy RVAs.')
        tasks.append('Add a separately reviewed executable/native profile only after adapter and protocol replay validation; SHA difference alone is not proof of incompatibility.')
    changes=[];resource_changes=[]
    old={r['file']:r for r in before['archives']};new={r['file']:r for r in after['archives']}
    for name in sorted(old.keys()|new.keys()):
        a=old.get(name);b=new.get(name)
        status='added' if a is None else 'removed' if b is None else None
        if a and b:
            fields=['size','version','entry_count','index_sha256','header_sha256']
            if 'sha256' in a and 'sha256' in b:fields.append('sha256')
            if any(a.get(k)!=b.get(k) for k in fields):status='changed'
        if status:changes.append(dict(file=name,status=status))
        ar={r['name'].casefold():r for r in (a or {}).get('resources',[])}
        br={r['name'].casefold():r for r in (b or {}).get('resources',[])}
        for resource in sorted(ar.keys()|br.keys()):
            x=ar.get(resource);y=br.get(resource)
            fields=('size','compressed_size','algorithm','checksum','mapped_id','descriptor_sha256','disk_payload_sha256')
            # Relocation/file timestamp alone is not a semantic resource delta.
            if x is None or y is None or any(x.get(k)!=y.get(k) for k in fields):
                resource_changes.append(dict(archive=name,name=(y or x)['name'],
                    status='added' if x is None else 'removed' if y is None else 'changed',
                    before_payload_sha256=(x or {}).get('disk_payload_sha256'),
                    after_payload_sha256=(y or {}).get('disk_payload_sha256'),plaintext_compatible=None))
    if resource_changes:
        reasons.append('key-resources-require-review')
        tasks.append('Re-extract changed key tables through the verified build reader or verified offline decoder; compare enums, item IDs/record layouts, skills, dungeon/quest references, and regenerate a staged catalog with dependency-closure checks. Never update player saves by replacing a catalog.')
    if changes:
        tasks.append('Check complete resource-set provenance and native archive loading; changed graphics/archive hashes are evidence to review, not automatic functional failure.')
    if before.get('server_catalog_sha256')!=after.get('server_catalog_sha256'):
        reasons.append('server-catalog-baseline-changed')
    tasks.append('Keep the current working client separate. Freeze the matched server/catalog/adapter snapshot; perform isolated replay, online test, then local backup/sync through the coordinator. Record real login/town/dungeon/reconnect acceptance separately.')
    return dict(schema_version=1,kind='client-update-review',before_inventory_sha256=identity(before),
        after_inventory_sha256=identity(after),exe_changed=exe_changed,archive_changes=changes,
        key_resource_changes=resource_changes,review_reasons=reasons,
        classification='review-required' if reasons or changes else 'no-observed-contract-or-index-change',
        auto_approved=False,protocol_compatible=None,gameplay_accepted=False,tasks=tasks,
        limitations=['Unchanged disk payload bytes do not prove plaintext/native consumer/protocol parity.',
                     'Header/index mode cannot exclude payload changes outside the selected key resources; use --full-hash for a complete archive-byte comparison.',
                     'Duplicate names across archives have unresolved native precedence; all candidates are reported instead of choosing one.'])

def read_report(path):
    if path.stat().st_size>8*1024*1024:raise ValueError('Inventory report exceeds 8MiB')
    return json.loads(path.read_text(encoding='utf8'))

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    snap=sub.add_parser('snapshot',help='Read PE/KOM identities; never start the game')
    snap.add_argument('--client',type=Path,required=True);snap.add_argument('--full-hash',action='store_true')
    check=sub.add_parser('check',help='Check implemented native and key-resource contracts offline')
    check.add_argument('--client',type=Path,required=True)
    delta=sub.add_parser('diff',help='Compare immutable client inventory reports')
    delta.add_argument('--before',type=Path,required=True);delta.add_argument('--after',type=Path,required=True)
    catalogs=sub.add_parser('catalog-diff',help='Compare definition catalogs; never migrate player saves')
    catalogs.add_argument('--before',type=Path,required=True);catalogs.add_argument('--after',type=Path,required=True)
    for parser in (snap,check,delta,catalogs):
        parser.add_argument('--runtime',type=Path,default=ROOT)
        parser.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv)
    if a.output.exists():raise ValueError('Output exists; preserve the previous report')
    exit_code=0
    if a.command=='snapshot':
        sys.path.insert(0,str(a.runtime/'vendor'))
        result=inventory(a.client,a.runtime,full_hash=a.full_hash,registry=load_registry(a.runtime))
        if not result['complete']:exit_code=2
    elif a.command=='check':
        records=[]
        try:result=check_client(a.client,a.runtime,emit=lambda line:records.append(json.loads(line.split(': ',1)[1])))['report']
        except (ValueError,OSError):
            result=records[-1] if records else dict(status='disk-preflight-error');exit_code=2
    elif a.command=='diff':result=compare(read_report(a.before),read_report(a.after))
    else:result=catalog_compare(a.before,a.after)
    with a.output.open('x',encoding='utf8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(output=str(a.output),status=result.get('status',result.get('classification',result.get('kind'))),
                         auto_approved=False,game_started=False),ensure_ascii=False))
    return exit_code

if __name__=='__main__':raise SystemExit(main())
