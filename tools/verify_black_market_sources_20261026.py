"""Verify paired black-market source bytes without game imports or database access."""
from pathlib import Path,PurePosixPath
import hashlib,json,re

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/black-market-native-completion-20261026-v1'
HEX=re.compile('[0-9a-f]{64}')

def verify():
    manifest=json.loads((ARCHIVE/'manifest.json').read_bytes())
    assert manifest['schema']==1 and manifest['issue']==505
    assert manifest['client_delta']==0 and manifest['install_DDL_statements']==0
    assert manifest['runtime_overlay_not_main'] is True
    assert manifest['private_configuration_or_player_data_included'] is False
    assert manifest['final_parent_qualification_verified'] is True and HEX.fullmatch(manifest['qualification_sha256'])
    assert set(manifest['channels'])=={'online','local'}
    seen=set();counts={};sources={}
    for channel,data in manifest['channels'].items():
        assert HEX.fullmatch(data['parent_manifest_sha256'])
        assert sorted(r['path']for r in data['files'])==manifest['source_paths']
        for row in data['files']:
            rel=PurePosixPath(row['path']);location=PurePosixPath(row['archive'])
            assert not rel.is_absolute()and '..'not in rel.parts and ':'not in str(rel)and '\\'not in str(rel)
            assert str(rel).startswith('els_server/')and rel.suffix in('.py','.json')
            assert str(location)in('shared/'+str(rel),channel+'/'+str(rel))
            path=ARCHIVE/location
            assert path.resolve().is_relative_to(ARCHIVE.resolve())and not path.is_symlink()
            raw=path.read_bytes()
            assert len(raw)==row['size']and HEX.fullmatch(row['sha256'])and hashlib.sha256(raw).hexdigest()==row['sha256']
            assert row['parent_sha256']is None or HEX.fullmatch(row['parent_sha256'])
            assert row['change_status']==('unchanged_dependency'if row['parent_sha256']==row['sha256']else'new'if row['parent_sha256']is None else'changed')
            if rel.suffix=='.py':compile(raw,str(location),'exec')
            else:json.loads(raw)
            sources[channel,str(rel)]=raw;seen.add(str(location))
        counts[channel]=len(data['files'])
        for leaf,data_leaf in(('black_market_rules','black_market'),('black_market_box_rules','black_market_boxes'),('market_conversion_rules','market_conversion')):
            code=sources[channel,'els_server/domain/'+leaf+'.py'].decode('utf8')
            claimed=re.search(r"DATA_SHA=['\"]([0-9a-f]{64})['\"]",code)
            assert claimed and claimed[1]==hashlib.sha256(sources[channel,'els_server/data/'+data_leaf+'.json']).hexdigest()
    assert len(manifest['six_coupon_files'])==6
    for row in manifest['six_coupon_files']:
        for channel in counts:assert hashlib.sha256(sources[channel,row['path']]).hexdigest()==row['sha256']
    for row in manifest['auxiliary_files']:
        rel=PurePosixPath(row['path']);assert len(rel.parts)==1 and rel.suffix in('.json','.txt')and rel.name!='manifest.json'
        assert hashlib.sha256((ARCHIVE/rel).read_bytes()).hexdigest()==row['sha256'];seen.add(str(rel))
    actual={p.relative_to(ARCHIVE).as_posix()for p in ARCHIVE.rglob('*')if p.is_file()}
    assert actual==seen|{'manifest.json'}
    assert len(seen)-len(manifest['auxiliary_files'])==manifest['physical_source_files']
    return dict(ok=True,channels=counts,physical_sources=manifest['physical_source_files'],six_coupon_qualification_retained=True,database_opened=False)

if __name__=='__main__':print(json.dumps(verify()))
