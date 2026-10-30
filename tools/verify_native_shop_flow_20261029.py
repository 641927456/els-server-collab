"""Verify published-source provenance and both public RSA envelopes without private assets."""
from pathlib import Path
from xml.etree import ElementTree
import ast,base64,hashlib,hmac,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import relative
L=ROOT/'launchers/friends-v41';F=ROOT/'references/native-shop-flow-20261029-v1'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def public_xml(text):return re.search(r'PublicKey = "([^"]+)"',text).group(1)

def envelope(document,xml):
    payload=base64.b64decode(document['payload'],validate=True)
    signature=base64.b64decode(document['signature'],validate=True)
    key=ElementTree.fromstring(xml)
    number=lambda n:int.from_bytes(base64.b64decode(key.findtext(n),validate=True),'big')
    modulus,exponent=number('Modulus'),number('Exponent');width=(modulus.bit_length()+7)//8
    assert len(signature)==width and int.from_bytes(signature,'big')<modulus
    actual=pow(int.from_bytes(signature,'big'),exponent,modulus).to_bytes(width,'big')
    digest=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(payload).digest()
    expected=b'\x00\x01'+b'\xff'*(width-len(digest)-3)+b'\x00'+digest
    assert hmac.compare_digest(actual,expected),'Public RSA signature mismatch'
    return json.loads(payload)

def accepted_delivery(receipt,source,current,profile):
    assert receipt['ok'] and receipt['formally_published'] and receipt['V']==41
    assert receipt['source_candidate_freeze_sha256']==read(F/'qualification.json')['source_candidate_freeze_sha256']
    assert receipt['public_artifacts']==source['public_artifacts']
    assert receipt['remote_metadata_sha256']['public/latest.json']==source['public_artifacts']['latest']['sha256']
    assert receipt['actual_old_V40_public_network_and_EXE_download_verified']
    counts=receipt['index']
    assert counts['old']==1094 and counts['new_unique']==850 and counts['now']==1944
    assert counts['now']==counts['old']+counts['new_unique'] and counts['all_old_entries_exact']
    reader=receipt['signed_component_reader']
    assert reader==dict(total=1764,first_reused=914,first_downloaded=850,repeat_reused=1764,repeat_downloaded=0,full_archive_downloaded=False)
    assert receipt['public_observation_seconds']>=120
    assert receipt['both_launcher_pointers_V41'] and receipt['both_desktop_shortcuts_V41']
    assert receipt['own_locks_released'] and receipt['listener_PIDs_unchanged']
    assert receipt['original_game_EXE_KOM_write_count']==0 and not receipt['KOM_full_before_after_SHA_claimed']
    assert receipt['new_hook_sites']==source['new_hook_sites']
    assert all(receipt[k] is False for k in ('player_database_restore','natural_GUI','Scaleform_HUD','Actor_106_or_actual_hit','whole_user_goal_complete'))
    assert current['profile']=='channels/native-force-guild-flow-accepted-20261029-v1.json'
    for name,row in receipt['channels'].items():
        assert current['accepted'][name]=={k:row[k] for k in ('release','formal_manifest_sha256')}
        assert row['business_files']==len(profile['channels'][name]['files'])
    online,local=receipt['channels']['online'],receipt['channels']['local']
    assert online['backend_unchanged'] and online['formal_manifest_sha256']==source['actual_current_parents']['online']['manifest_sha256']
    assert local['parent_manifest_sha256']==source['actual_current_parents']['local']['manifest_sha256']
    assert local['all_parent_business_bytes_preserved'] and local['runtime_files']==1779
    assert local['support_modified']==2 and local['support_added']==1 and local['install_DDL']==0
    assert local['observation_seconds']>=120

def verify():
    p=read(L/'source-manifest.json');q=read(F/'qualification.json')
    assert p['V']==41 and p['parent_V']==40 and p['issue']==618
    assert len(p['sources'])==16 and len(p['external_retained_resources'])==1
    assert p['runtime_files']==1764 and p['component_backend']=='online'
    sources={r['path']:r for r in p['sources']}
    for name,row in sources.items():
        raw=(ROOT/row['source']).read_bytes();assert sha(ROOT/row['source'])==row['sha256'] and len(raw)==row['size']
        if name.endswith('.py'):ast.parse(raw)
    for edit in p['exact_constant_inverses']:
        raw=(ROOT/sources[edit['path']]['source']).read_bytes()
        assert raw.count(edit['current'].encode())==1
        restored=raw.replace(edit['current'].encode(),edit['parent'].encode(),1)
        assert hashlib.sha256(restored).hexdigest()==edit['parent_sha256']
    xml=public_xml((L/'AutoUpdate.cs').read_text(encoding='utf-8'))
    assert xml==public_xml((ROOT/'launchers/friends-v38/AutoUpdate.cs').read_text(encoding='utf-8-sig'))
    signed=read(ROOT/sources['runtime-files.signed.json']['source'])
    assert sources['runtime-files.signed.json']['sha256']==p['public_artifacts']['signed_components']['sha256']
    for artifact in p['public_artifacts'].values():
        if 'source' in artifact:assert sha(ROOT/artifact['source'])==artifact['sha256']
    components=envelope(signed,xml)
    unsigned=read(ROOT/p['public_artifacts']['component_manifest']['source'])
    assert components==unsigned and len(components['files'])==1764
    assert components['archive']['sha256']==p['public_artifacts']['runtime_archive']['sha256']
    rows={r['path']:r for r in components['files']};assert len(rows)==1764
    for name in rows:relative(name)
    latest=envelope(read(ROOT/p['public_artifacts']['latest']['source']),xml)
    artifact=p['public_artifacts']['launcher']
    assert latest['version']==41 and latest['sha256']==artifact['sha256']
    assert latest['size']==artifact['size'] and latest['file']==artifact['public_file']
    for row in p['runtime_support']:
        source=ROOT/row['source'];assert sha(source)==row['sha256']==rows[row['path']]['sha256']
        assert source.stat().st_size==row['size']==rows[row['path']]['size']
    data=next(r for r in p['runtime_support']if r['path']=='tools/ed_shop_catalogs.json')
    generator=next(r for r in p['runtime_support']if r['path']=='tools/install_ed_shop_bridge.py')
    assert data['sha256']in(ROOT/generator['source']).read_text(encoding='utf-8')
    assert p['new_hook_sites']==['0x313ABCE']
    assert not p['private_key_or_test_fixtures_included'] and not p['native_GUI_verified']
    assert q['actual_Frida_original_branch_controls']==13 and q['state_controls']==66
    assert not q['actual_GUI_Scaleform_HUD_verified'] and not q['full_attributes_or_battle_verified']
    # Preserve the actual approved V41 selection as historical evidence while
    # current-engine advances to later independently accepted server fixes.
    historical=F/'current-engine-at-delivery.json'
    assert sha(historical)=='271fcabde776815cd3c908f6a5a93190ff3ab8282b409b236d1771ace36d449f'
    accepted_delivery(read(F/'accepted-delivery.json'),p,read(historical),read(ROOT/'channels/native-force-guild-flow-accepted-20261029-v1.json'))
    print(json.dumps({'ok':True,'mapped_text_sources':16,'retained_external_PNG':1,'signed_components':1764,'runtime_support':3,'RSA_signatures':2,'GUI_or_battle_claimed':False}))

if __name__=='__main__':verify()
