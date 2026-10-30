"""Verify V42 source, two signed runtime identities and exact LOCAL support delta."""
from pathlib import Path
import base64,hashlib,json,re,sys
from xml.etree import ElementTree
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'launchers/friends-v42'
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verify_envelope(path,key):
    wrapper=read(path);raw=base64.b64decode(wrapper['payload'],validate=True);signature=base64.b64decode(wrapper['signature'],validate=True)
    xml=ElementTree.fromstring(key);number=lambda n:int.from_bytes(base64.b64decode(xml.findtext(n)),'big')
    n,e=number('Modulus'),number('Exponent');width=(n.bit_length()+7)//8
    if len(signature)!=width or int.from_bytes(signature,'big')>=n:raise ValueError('Invalid RSA signature size')
    actual=pow(int.from_bytes(signature,'big'),e,n).to_bytes(width,'big')
    suffix=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(raw).digest()
    expected=b'\x00\x01'+b'\xff'*(width-len(suffix)-3)+b'\x00'+suffix
    if actual!=expected:raise ValueError('Invalid runtime signature')
    document=json.loads(raw)
    if (document['schema'],document['product'],document['channel'],document['kind'])!=(1,'ElsFriends','friends','runtime-files'):raise ValueError('Invalid runtime channel')
    return document

def main():
    sys.path.insert(0,str(A));import build
    lock,files,_=build.inputs()
    key=re.search(r'PublicKey = "([^"]+)"',(A/'AutoUpdate.cs').read_text('utf-8-sig')).group(1)
    friends=verify_envelope(A/'runtime-files.signed.json',key);local=verify_envelope(A/'local-runtime-files.signed.json',key)
    if sha(A/'runtime-files.signed.json')!=sha(ROOT/'launchers/friends-v41/runtime-files.signed.json'):raise ValueError('V41 friends runtime changed')
    if friends['archive']['sha256'] not in (A/'Program.cs').read_text('utf8'):raise ValueError('Friends payload binding differs')
    if local['archive']['sha256'] not in (A/'LocalBootstrap.cs').read_text('utf8'):raise ValueError('Local payload binding differs')
    rows={r['path']:r for r in local['files']};metadata=read(A/'local-bootstrap-source.json')
    if rows['local-bootstrap-source.json']['sha256']!=sha(A/'local-bootstrap-source.json'):raise ValueError('Local source metadata differs')
    snapshot=A/'accepted-source-selection.json'
    if sha(snapshot)!='271fcabde776815cd3c908f6a5a93190ff3ab8282b409b236d1771ace36d449f':raise ValueError('Historical V42 selection snapshot changed')
    selection=read(snapshot);profile_path=ROOT/selection['profile']
    if sha(profile_path)!='77fb1412039711eaba1160f03f96cdd61bfb3fdde54df3c08491281f0ac448b9':raise ValueError('Historical V42 exact profile changed')
    profile=read(profile_path)
    formal={r['path']:r for r in profile['channels']['local']['files']}
    normalized=[{k:formal[p][k] for k in ('path','size','sha256')}for p in sorted(formal)]
    digest=hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    if len(formal)!=metadata['source_file_count'] or digest!=metadata['source_files_sha256']:raise ValueError('Formal LOCAL source set changed')
    if selection['accepted']['local']['formal_manifest_sha256']!=metadata['source_formal_manifest_sha256']:raise ValueError('Accepted LOCAL source differs')
    if metadata['generated_config_source_sha256']!=formal['config/server.toml']['sha256'] or 'config/server.toml' in rows:raise ValueError('Host configuration must be generated')
    for path,name in [('tools/launch_client.py','launch_client.py'),('tools/local_fresh_state.py','local_fresh_state.py'),('tools/client_compatibility_profiles.json','client_compatibility_profiles.json')]:
        if rows[path]['sha256']!=sha(A/name):raise ValueError('Signed support differs: '+path)
    artifacts=read(A/'client_compatibility_profiles.json')['profiles']
    for profile in artifacts:
        if 'tools/launch_client.py' in profile['artifacts']:
            if any(profile['artifacts'][path]!=rows[path]['sha256']for path in ('tools/launch_client.py','tools/local_fresh_state.py')):raise ValueError('Compatibility dependency differs')
    if len(friends['files'])!=1764 or len(rows)!=1779:raise ValueError('Runtime membership differs')
    print(json.dumps({'ok':True,'V':42,'source_files':len(files),'formal_LOCAL_files':len(formal),'friends_runtime_files':len(friends['files']),'local_runtime_files':len(rows),'RSA_signatures_verified':True,'game_started':False}))

if __name__=='__main__':main()
