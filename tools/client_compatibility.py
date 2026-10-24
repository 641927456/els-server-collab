"""Reviewed native contracts and bounded read-only client resource inspection.

Directory decoding and disk fingerprints never imply native ABI or plaintext
catalog equivalence. No game process, archive or player state is modified here.
"""
import collections
import hashlib
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

MAX_INDEX=32*1024*1024
MAX_FILES=200000
REFERENCE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
DIRECTORY_SHA='d59f936e5a94d621d105386941b33d021c1325499ea5ba70443a3edaae1a584f'

def digest_file(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def stamp(path):
    s=path.stat()
    return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns

def archive(path,names,full_hash=False,directory_seeds=None):
    before=stamp(path)
    result=dict(file=path.name,size=before[2],resources=[])
    with path.open('rb') as f:
        h=f.read(72)
        if len(h)!=72 or not h.startswith(b'KOG '):raise ValueError('KOM header incomplete/unknown')
        count,_,time_sum,adler,n=struct.unpack_from('<5I',h,52)
        if not 0<count<=MAX_FILES or not 0<n<=MAX_INDEX or n>before[2]-72:
            raise ValueError('KOM directory bounds')
        raw=f.read(n)
        if zlib.adler32(raw)!=adler:raise ValueError('KOM directory checksum')
        result.update(version=h[:52].split(b'\0',1)[0].decode('ascii',errors='replace'),
                      entry_count=count,index_sha256=hashlib.sha256(raw).hexdigest(),
                      header_sha256=hashlib.sha256(h).hexdigest(),time_sum=time_sum)
        decoded=raw
        decoder='plain'
        if not raw.startswith(b'<?xml'):
            if b'V.0.4.' in h[:52]:
                prefix=b'<?xml version="1.0"?><Files>'
                if len(raw)<len(prefix):raise ValueError('KOM XML too short')
                key=bytes(a^b for a,b in zip(raw[:12],prefix[:12]))
                decoded=bytes(v^key[i%12] for i,v in enumerate(raw))
                decoder='existing-v4-xor'
            elif directory_seeds is not None:
                # Reuses extract_launcher_assets.py's witnessed directory decoder.
                from Crypto.Cipher import Blowfish
                if len(directory_seeds)!=201 or any(type(v) is not int or not 0<=v<=0xffffffff for v in directory_seeds):
                    raise ValueError('Directory decoder seed schema')
                seed=directory_seeds[n%200+1]
                key=hashlib.sha1(str(seed).encode()).digest()
                decoded=Blowfish.new(key,Blowfish.MODE_ECB).decrypt(raw[:n&~7])+raw[n&~7:]
                decoder='existing-d59f936e-directory-only'
            else:
                result.update(index_status='opaque-needs-build-decoder',payload_validation='not-performed')
                if stamp(path)!=before:raise ValueError('Client changed during inventory')
                if full_hash:
                    f.seek(0);result['sha256']=hashlib.file_digest(f,'sha256').hexdigest()
                    if stamp(path)!=before:raise ValueError('Client changed during inventory')
                return result
        if b'<!DOCTYPE' in decoded.upper() or b'<!ENTITY' in decoded.upper():
            raise ValueError('KOM XML declarations forbidden')
        try:root=ET.fromstring(decoded)
        except ET.ParseError:
            if decoder=='plain':raise
            result.update(index_status='opaque-decoder-not-matched',decoder=decoder,payload_validation='not-performed')
            if full_hash:
                f.seek(0);result['sha256']=hashlib.file_digest(f,'sha256').hexdigest()
            if stamp(path)!=before:raise ValueError('Client changed during inventory')
            return result
        if root.tag!='Files' or len(root)!=count or any(e.tag!='File' for e in root):
            raise ValueError('KOM index entry count/schema')
        offset=72+n;seen=set();algorithms=collections.Counter()
        for e in root:
            name=e.get('Name','')
            if not name or len(name)>512 or name.casefold() in seen or '/' in name or '\\' in name or ':' in name:
                raise ValueError('KOM resource name/duplicate')
            seen.add(name.casefold())
            size=int(e.get('Size','-1'));compressed=int(e.get('CompressedSize','-1'))
            algorithm=int(e.get('Algorithm','-1'))
            if not 0<=size<=1024**3 or not 0<=compressed<=512*1024**2 or offset+compressed>before[2] or not 0<=algorithm<=255:
                raise ValueError('KOM payload bounds/algorithm')
            algorithms[algorithm]+=1
            if name.casefold() in names:
                f.seek(offset);remaining=compressed;sha=hashlib.sha256()
                while remaining:
                    data=f.read(min(1024*1024,remaining))
                    if not data:raise ValueError('Truncated KOM payload')
                    sha.update(data);remaining-=len(data)
                result['resources'].append(dict(name=name,offset=offset,size=size,compressed_size=compressed,
                    algorithm=algorithm,checksum=e.get('Checksum'),file_time=e.get('FileTime'),
                    mapped_id=e.get('MappedID'),
                    descriptor_sha256=hashlib.sha256(json.dumps(e.attrib,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest(),
                    disk_payload_sha256=sha.hexdigest(),plaintext_verified=False))
            offset+=compressed
        if offset!=before[2]:raise ValueError('KOM trailing/unaccounted bytes')
        result.update(index_status='parsed',decoder=decoder,algorithms=dict(algorithms),
                      payload_validation='selected encrypted/compressed bytes hashed; no Lua execution or native-read claim')
        if full_hash:
            f.seek(0);result['sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    if stamp(path)!=before:raise ValueError('Client changed during inventory')
    return result

def inspect_pe(path):
    before=stamp(path)
    with path.open('rb') as f:
        h=f.read(64)
        if len(h)!=64 or h[:2]!=b'MZ':raise ValueError('PE DOS header')
        off=struct.unpack_from('<I',h,60)[0]
        if off<64 or off>before[2]-26:raise ValueError('PE header bounds')
        f.seek(off);pe=f.read(26)
        if pe[:4]!=b'PE\0\0' or struct.unpack_from('<H',pe,4)[0]!=0x8664 or struct.unpack_from('<H',pe,24)[0]!=0x20b:
            raise ValueError('Expected PE32+ x64 client')
        f.seek(0);sha=hashlib.file_digest(f,'sha256').hexdigest()
    if stamp(path)!=before:raise ValueError('Client changed during inventory')
    return dict(file=path.name,sha256=sha,size=before[2],machine='x64',coff_timestamp=struct.unpack_from('<I',pe,8)[0])

def inventory(client,runtime,full_hash=False,registry=None):
    initial_client_stamp=stamp(client)
    manifest=json.loads((runtime/'els_server/data/client/manifest.json').read_text(encoding='utf8'))
    exe=inspect_pe(client)
    names={r['name'].casefold() for r in manifest['sources']}|{'config.lua','item.kim'}
    paths=sorted(p for p in client.parent.iterdir() if re.fullmatch(r'datai?\d{3}\.kom',p.name,re.I))
    stamps={p:stamp(p) for p in [client,*paths]}
    archives=[];errors=[]
    for p in paths:
        try:archives.append(archive(p,names,full_hash=full_hash,directory_seeds=registry['directory_decoder']['seeds'] if registry else None))
        except (ValueError,OSError,ET.ParseError,struct.error) as e:errors.append(dict(file=p.name,error=str(e)))
    changed=[p.name for p,s in stamps.items() if not p.exists() or stamp(p)!=s]
    if not client.exists() or stamp(client)!=initial_client_stamp:
        changed.append(client.name)
    if changed:errors.append(dict(error='files-changed-during-inventory',files=changed))
    final_names=sorted(p.name for p in client.parent.iterdir() if re.fullmatch(r'datai?\d{3}\.kom',p.name,re.I))
    if final_names!=sorted(p.name for p in paths):errors.append(dict(error='archive-set-changed-during-inventory'))
    found={r['name'].casefold() for a in archives for r in a['resources']}
    return dict(schema_version=1,kind='client-update-inventory',client=exe,
        native_profile=next((p['id'] for p in registry.get('profiles',[]) if IMPLEMENTED_CONTRACTS.get(p.get('native_contract'))==(exe['sha256'],p.get('native_directory'),p.get('runtime_sha256'))),None) if registry else None,
        directory_key_witness_sha256=registry['directory_decoder']['source_sha256'] if registry else None,
        server_catalog_sha256=manifest['catalog_sha256'],server_catalog_client_sha256=manifest['client_sha256'],
        archives=archives,errors=errors,missing_catalog_resources=sorted(names-found),
        complete=bool(paths) and not errors and all(a['index_status']=='parsed' for a in archives),
        supported_new_build=False,native_or_protocol_tested=False,
        note='Disk metadata is evidence for comparison only. Resource payload hashes are not plaintext catalog identity or protocol validation.')


# JSON records evidence; adding a row alone does not implement a new adapter.
IMPLEMENTED_CONTRACTS={
 'dx11-6c6b5180-v1':('6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709',
                       'analysis/client-6c6b5180',
                       'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229')}

class CompatibilityPending(ValueError):pass

def load_registry(runtime):
    path=runtime/'tools/client_compatibility_profiles.json'
    if path.stat().st_size>512*1024:raise ValueError('Compatibility registry size')
    data=json.loads(path.read_text(encoding='utf8'))
    if data.get('schema_version')!=1 or not isinstance(data.get('profiles'),list) or not 1<=len(data['profiles'])<=16:
        raise ValueError('Compatibility registry schema')
    seeds=data['directory_decoder']['seeds']
    if len(seeds)!=201 or any(type(v) is not int or not 0<=v<=0xffffffff for v in seeds):
        raise ValueError('Directory decoder seed schema')
    if (data['directory_decoder']['source_sha256']!=DIRECTORY_SHA or
            hashlib.sha256(struct.pack('<201I',*seeds)).hexdigest()!='ace76856dbd98b1896f2153dcbf691b31aabb8f815969884fb1903d4a632dc2d'):
        raise ValueError('Directory decoder evidence mismatch')
    for p in data['profiles']:
        if not re.fullmatch('[0-9a-f]{64}',p['executable_sha256']):raise ValueError('Executable SHA schema')
        if not isinstance(p['artifacts'],dict) or not 4<=len(p['artifacts'])<=64:raise ValueError('Profile evidence count')
        for name,sha in p['artifacts'].items():
            if not isinstance(name,str) or not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('Profile artifact schema')
            inside(runtime,name)
        critical=p.get('critical_archives')
        if not isinstance(critical,list) or not 1<=len(critical)<=64:raise ValueError('Critical resource evidence missing')
        names=set()
        for a in critical:
            if not re.fullmatch(r'datai?\d{3}\.kom',a['file'],re.I) or a['file'].casefold() in names:
                raise ValueError('Critical archive identity/duplicate')
            names.add(a['file'].casefold());resources=a['resources']
            if not isinstance(resources,list) or not 1<=len(resources)<=1024:raise ValueError('Critical resource count')
            seen=set()
            for r in resources:
                name=r['name'].casefold()
                if not name or len(name)>512 or name in seen:raise ValueError('Critical resource identity/duplicate')
                seen.add(name)
                for k in ('disk_payload_sha256','descriptor_sha256'):
                    if not re.fullmatch('[0-9a-f]{64}',r[k]):raise ValueError('Critical resource SHA schema')
    return data

def inside(root,name):
    if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('Profile path outside runtime')
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Profile path outside runtime')
    return path

def select(client,runtime,registry,executable=None):
    executable=executable if executable is not None else inspect_pe(client)
    matches=[p for p in registry['profiles'] if p['executable_sha256']==executable['sha256']]
    if not matches:
        raise CompatibilityPending('客户端尚未完成适配核验（不是已确认不兼容）。EXE SHA256：'+executable['sha256']+'。请保留原可用客户端，并提交客户端更新检查报告。')
    if len(matches)!=1:raise ValueError('Ambiguous executable profiles')
    p=matches[0]
    contract=IMPLEMENTED_CONTRACTS.get(p['native_contract'])
    if contract!=(p['executable_sha256'],p['native_directory'],p['runtime_sha256']):
        raise CompatibilityPending('此版本没有已实现并核验的原生适配器，请更新朋友服启动器配套版本。')
    required={'analysis/client-6c6b5180/x2-runtime.bin','tools/trace_dx11_login.js',
              'els_server/data/client/catalog.sqlite3','els_server/data/client/manifest.json'}
    if not required.issubset(p['artifacts']):raise ValueError('Incomplete profile artifact evidence')
    if p['artifacts']['analysis/client-6c6b5180/x2-runtime.bin']!=p['runtime_sha256']:
        raise ValueError('Native image evidence conflicts with implemented contract')
    if p.get('server_catalog_sha256') and p['artifacts']['els_server/data/client/catalog.sqlite3']!=p['server_catalog_sha256']:
        raise ValueError('Catalog evidence conflicts with profile')
    for name,expected in p['artifacts'].items():
        with inside(runtime,name).open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=expected:raise ValueError('Client compatibility dependency changed: '+name)
    return dict(profile=p,native_directory=str(inside(runtime,p['native_directory'])),executable=executable)

def resource_decision(directory,profile,registry):
    """Check key bytes/descriptors only; cosmetic archive changes need not lock a build."""
    rows=[]
    for spec in profile['critical_archives']:
        if Path(spec['file']).name!=spec['file'] or '/' in spec['file'] or '\\' in spec['file']:
            raise ValueError('Critical archive name')
        expected={r['name'].casefold():r for r in spec['resources']}
        actual=archive(directory/spec['file'],set(expected),directory_seeds=registry['directory_decoder']['seeds'])
        if actual['index_status']!='parsed':
            rows.append(dict(file=spec['file'],status='directory-decoder-review-required',changes=[]));continue
        measured={r['name'].casefold():r for r in actual['resources']}
        changes=[]
        fields=('size','compressed_size','algorithm','checksum','mapped_id','descriptor_sha256','disk_payload_sha256')
        for name in sorted(expected):
            before=expected[name];after=measured.get(name)
            different=list(fields) if after is None else [k for k in fields if before.get(k)!=after.get(k)]
            if different:changes.append(dict(name=before['name'],fields=different,status='missing' if after is None else 'changed'))
        rows.append(dict(file=spec['file'],status='key-resource-review-required' if changes else 'key-resource-fingerprints-match',changes=changes))
    return dict(archives=rows,key_resource_fingerprints_match=bool(rows) and all(r['status']=='key-resource-fingerprints-match' for r in rows),
                native_archive_loading_verified=False,protocol_compatibility_inferred=False)

def ensure_unchanged(selection):
    for name,before in selection['disk_stamps'].items():
        path=Path(name)
        if not path.exists() or stamp(path)!=before:
            raise CompatibilityPending('客户端在兼容预检后发生变化，请等待官方更新完成后重新启动：'+path.name)

def check_client(client,runtime,emit=None):
    """Produce an attempt-log record and refuse unsupported contracts before launch."""
    report=dict(schema_version=1,phase='disk-preflight',status='checking',
                gameplay_accepted=False,native_live_checks_required=True)
    def record():
        if emit:emit('ELS_CLIENT_COMPATIBILITY: '+json.dumps(report,ensure_ascii=False,separators=(',',':')))
    try:
        registry=load_registry(runtime)
        client_stamp=stamp(client)
        executable=inspect_pe(client)
        report['executable_sha256']=executable['sha256']
        selection=select(client,runtime,registry,executable=executable)
        selection['disk_stamps']={str(client.resolve()):client_stamp}
        for row in selection['profile']['critical_archives']:
            path=client.parent/row['file'];selection['disk_stamps'][str(path.resolve())]=stamp(path)
        report.update(executable_sha256=selection['executable']['sha256'],
                      profile=selection['profile']['id'],native_contract=selection['profile']['native_contract'])
        decision=resource_decision(client.parent,selection['profile'],registry)
        report['resources']=decision
        if not decision['key_resource_fingerprints_match']:
            report['status']='resource-contract-review-required'
            changed=[r['name'] for a in decision['archives'] for r in a['changes']]
            raise CompatibilityPending('关键客户端资源尚未完成服务端配表适配：'+('、'.join(changed[:8]) or '资源目录格式变化')+'。请保留原可用客户端，并提交本次客户端检查日志或更新差异报告。')
        try:ensure_unchanged(selection)
        except CompatibilityPending:
            report['status']='client-changed-during-preflight';raise
        report['status']='known-contract-disk-checks-ready'
        selection['report']=report
        record()
        return selection
    except CompatibilityPending as error:
        if report['status']=='checking':report['status']='native-contract-review-required'
        report['error']=str(error);record();raise
    except (OSError,ValueError,KeyError,TypeError,struct.error,ET.ParseError) as error:
        report.update(status='disk-preflight-error',error=str(error));record();raise ValueError('客户端兼容预检未完成：'+str(error)) from error
