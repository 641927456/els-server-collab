"""Verify exact reviewed server source bytes without importing game/database code."""
from pathlib import Path,PurePosixPath
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/pr494-reviewed-runtime-delta-20261026-v1'


def verify():
    manifest=json.loads((ARCHIVE/'manifest.json').read_bytes())
    assert manifest['schema']==1 and manifest['client_delta']==0 and manifest['install_DDL_statements']==0
    assert not manifest['private_configuration_or_player_data_included']
    assert set(manifest['channels'])=={'online','local'}
    seen=set();counts={}
    for channel,data in manifest['channels'].items():
        assert len(data['parent_manifest_sha256'])==64
        rows=data['delta'];assert sorted(r['path']for r in rows)==manifest['delta_paths']
        assert sorted(r['path']for r in rows if r['parent_sha256']is None)==manifest['new_paths']
        assert len(rows)==12 and len(manifest['new_paths'])==3
        for row in rows:
            rel=PurePosixPath(row['path']);location=PurePosixPath(row['archive'])
            assert not rel.is_absolute()and '..'not in rel.parts and ':'not in str(rel)and '\\'not in str(rel)
            assert str(rel).startswith('els_server/')and rel.suffix in('.py','.json')
            assert str(location)in('shared/'+str(rel),channel+'/'+str(rel))
            path=ARCHIVE/location
            assert path.resolve().is_relative_to(ARCHIVE.resolve())and not path.is_symlink()
            raw=path.read_bytes()
            assert len(raw)==row['size']and hashlib.sha256(raw).hexdigest()==row['sha256']
            if rel.suffix=='.py':compile(raw,str(location),'exec')
            else:json.loads(raw)
            seen.add(str(location))
        counts[channel]=len(rows)
    actual={p.relative_to(ARCHIVE).as_posix()for p in ARCHIVE.rglob('*')if p.is_file()}
    assert actual==seen|{'manifest.json'}and len(seen)==manifest['physical_files']
    return dict(ok=True,channels=counts,physical_files=len(seen),database_opened=False)


if __name__=='__main__':print(json.dumps(verify()))
