from pathlib import Path
import hashlib,json,shutil,os,subprocess,difflib
W=Path(__file__).resolve().parent;R=W.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
inputs=read(W/'input-manifests.json');targets={f['path'] for v in inputs.values() for f in v['files']}
parents={c:read(R/f'releases/{c}/current.json')for c in ('online','local')}
online=R/parents['online']['path'];local=R/parents['local']['path']
assert parents['online']['release']=='shop-rare-navy-20261101-v1'
assert parents['local']['release']=='local-shop-rare-navy-20261101-v1'
runtime=W/'runtime';runtime.mkdir(exist_ok=True)
def merge_bytes(current,before,incoming,folder):
    folder.mkdir(parents=True,exist_ok=True)
    for name,data in (('current',current),('base',before),('incoming',incoming)):
        (folder/name).write_bytes(data.replace(b'\r\n',b'\n'))
    return subprocess.run(['git','merge-file','-p',str(folder/'current'),str(folder/'base'),str(folder/'incoming')],capture_output=True)
links=[]
for p in online.rglob('*'):
    if not p.is_file() or '__pycache__'in p.parts:continue
    rel=p.relative_to(online).as_posix();out=runtime/rel;out.parent.mkdir(parents=True,exist_ok=True)
    if p.stat().st_size>=1024*1024 and rel not in targets:
        if out.exists():assert os.path.samefile(p,out)
        else:os.link(p,out)
        links.append(rel)
    else:shutil.copy2(p,out)
records=[];conflicts=[]
for name,source in inputs.items():
    base=Path(source['parent']);incoming=Path(source['root'])
    for row in source['files']:
        rel=row['path'];dest=runtime/rel;before=base/rel;src=incoming/rel
        assert sha(src)==row['sha256']
        assert (sha(before)if before.exists()else None)==row['parent_sha256']
        current=dest.read_bytes()if dest.exists()else None
        if current is None or current==(before.read_bytes()if before.exists()else None):
            result=src.read_bytes();mode='exact-input'
        elif current==src.read_bytes():result=current;mode='already-inherited'
        else:
            cp=W/'merge-inputs'/name/rel;cp.parent.mkdir(parents=True,exist_ok=True);cp.write_bytes(current)
            proc=merge_bytes(current,before.read_bytes(),src.read_bytes(),cp.parent/(cp.name+'.normalized'))
            assert proc.returncode in (0,1),(rel,proc.stderr)
            result=proc.stdout;mode='three-way'
            if proc.returncode:
                # Boost changes owned_reward_box dispatch from the historical list
                # to the common catalog flag. Quick Start boxes have their own flag.
                expected=b"<<<<<<< "
                lines=result.decode('utf8').splitlines(keepends=True)
                start=next(i for i,x in enumerate(lines)if x.startswith('<<<<<<< '))
                end=next(i for i,x in enumerate(lines)if x.startswith('>>>>>>> '))
                block=''.join(lines[start:end+1])
                assert name=='quick'and rel=='els_server/domain/local_session.py'and 'owned_reward_box' in block and '720818' in block,block
                replacement="                    elif fixed_cubes()[cube_template].get('owned_reward_box') or fixed_cubes()[cube_template].get('quick_start_box') or cube_template in (300645,300646,300647,300648):\n"
                result=(''.join(lines[:start])+replacement+''.join(lines[end+1:])).encode()
                assert b'<<<<<<< 'not in result
                conflicts.append(dict(path=rel,input=name,resolution='Dispatch both catalog flags through the existing guarded fixed-cube consumer; preserve four legacy job boxes.'))
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(result)
        records.append(dict(input=name,path=rel,mode=mode,input_sha256=row['sha256'],output_sha256=sha(dest)))
local_delta=W/'local-delta';local_rows=[]
for row in inputs['boost']['files']:
    rel=row['path'];src=Path(inputs['boost']['root'])/rel;before=Path(inputs['boost']['parent'])/rel;current=local/rel;dest=local_delta/rel
    dest.parent.mkdir(parents=True,exist_ok=True)
    if (current.read_bytes()if current.exists()else None)==(before.read_bytes()if before.exists()else None):result=src.read_bytes()
    elif current.read_bytes()==src.read_bytes():result=src.read_bytes()
    else:
        proc=merge_bytes(current.read_bytes(),before.read_bytes(),src.read_bytes(),W/'merge-inputs'/'local'/rel)
        assert proc.returncode==0,(rel,proc.stdout.decode('utf8','replace'));result=proc.stdout
    dest.write_bytes(result);local_rows.append(dict(path=rel,parent_sha256=sha(current)if current.exists()else None,sha256=sha(dest),size=len(result)))
online_rows=[]
for rel in sorted(targets):
    p=runtime/rel;old=online/rel
    online_rows.append(dict(path=rel,parent_sha256=sha(old)if old.exists()else None,sha256=sha(p),size=p.stat().st_size))
save(W/'composition.json',dict(parents=parents,online_root=str(runtime),online_delta=online_rows,local_root=str(local_delta),local_delta=local_rows,records=records,conflicts=conflicts,immutable_resource_links=links,scope=dict(boost='dual',abyss='online-only',quick='online-only')))
print(json.dumps(dict(ok=True,online=len(online_rows),local=len(local_rows),three_way=[r['path']for r in records if r['mode']=='three-way'],conflicts=conflicts,immutable_links=len(links))))
