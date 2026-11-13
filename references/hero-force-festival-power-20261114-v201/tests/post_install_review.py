"""Review the actually selected installations against accepted business/native inputs."""
from pathlib import Path
import hashlib,json,os,sys
H=Path(__file__).resolve().parent;O=H/'publication';ROOT=H.parents[1]
sys.path[:0]=[str(O),str(H)]
from release_config import OWNER,RELEASE,read,sha
import publication_common as common

def main():
    common.assert_held()
    data=read(O/'publication-inputs.json');local=read(O/'local-preopen-installation-acceptance.json')
    online=read(O/'qualified-online.json');components=read(O/'actual-components.json')
    assert local['ok']and local['observed_seconds']>=120 and online['ok']and online['public_tls']
    assert online['public']['expected_game_authentications']==8
    assert components['ok']and not components['game_started']
    installed=Path(local['runtime']);client=Path(components['client_root']);server=Path(components['server_root'])
    definition=read(O/'launcher-preview-v201/runtime-files.json')
    for row in definition['files']:
        assert sha((client if row['module']=='client'else server)/row['path'])==row['sha256']
        assert sha(installed/row['path'])==row['sha256']
    wanted={row['path']:row['sha256']for row in data['online_changes']}
    remote=common.remote("""from pathlib import Path
import hashlib,json,tomllib,urllib.request
r=Path('C:/ElsFriends');key=(r/'state/gm/access.key').read_text('ascii').strip()
status=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18765/api/status',headers={'X-GM-Key':key}),timeout=30))['result']
names="""+repr(list(wanted))+"""
print(json.dumps(dict(pid=status['pid'],ready=status['ready'],files={name:hashlib.sha256((r/name).read_bytes()).hexdigest()for name in names})))
""",timeout=90)
    assert remote['ready']and remote['pid']==online['candidate_pid']and remote['files']==wanted
    native=read(H/'native/result.json');assert native['ok']and native['mybuff_ready']and native['raid_native_power_ready']
    assert read(H/'native/activation-summary.json')['ok']
    native_root=Path(native['actual_signed_install'])
    assert sha(client/'tools/native_support.json')==sha(native_root/'tools/native_support.json')
    assert native['client_signature_definition']==sha(H/'packages/client.payload.json')
    assert sha(client/'tools/probe_updated_client.py')==sha(H/'runtime/client/tools/probe_updated_client.py')
    assert 'out.mkdir(parents=True,exist_ok=True)'in(client/'tools/probe_updated_client.py').read_text('utf8')
    profile=read(client/'tools/client_compatibility_profiles.json')
    assert profile['profiles'][0]['artifacts']['tools/probe_updated_client.py']==sha(client/'tools/probe_updated_client.py')
    proof=dict(ok=True,release=RELEASE,actual_cloud_pid=remote['pid'],actual_cloud_source_files=len(wanted),actual_selected_signed_files=len(definition['files']),actual_local_runtime=str(installed),client_template_matches_original_native_activated_input=True,actual_public_QA_expected_game_authentications=8,public_TLS_and_cold_reads=dict(path=str(O/'qualified-online.json'),sha256=sha(O/'qualified-online.json')),source_business_and_input_refresh_checks=read(H/'accepted-source.json')['checks'],actual_signed_original_client=dict(path=str(H/'native/result.json'),sha256=sha(H/'native/result.json')),limitations=['Client-origin values are not independently calculated server anti-forgery proof.','Native positive additional Greed bands and all-AD acknowledgement are not claimed.','Source full native clears and unchanged business tests are reused by exact input identity.','Launcher natural click remains separate from controlled form tests.'],player_original_EXE_KOM_modified=False,player_input_or_process_control=False)
    common.save(O/'post-install-review.json',proof)
    print('Actual installed cloud/local/signed inputs reviewed against qualified native and transaction evidence')

if __name__=='__main__':main()
