"""Verify exact installed source/evidence bytes without activating another engine."""
from pathlib import Path,PurePosixPath
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'references/player-feedback-online-20261103-v1'
MANIFEST_SHA='eb276a6514e8ccf60066a82552ed065e7c02ce4d31c0476ee003c395e1805107'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def verify():
    path=ARCHIVE/'manifest.json';assert digest(path)==MANIFEST_SHA
    manifest=json.loads(path.read_bytes());rows=manifest['source_files']
    assert manifest['issue']==777 and manifest['archive_only'] and not manifest['default_engine_selection_changed']
    assert len(rows)==11 and len({r['runtime_path']for r in rows})==11
    assert sum(r['parent_sha256']is None for r in rows)==1
    compiled=0
    for row in rows:
        p=PurePosixPath(row['archive_path'])
        assert not p.is_absolute()and '..'not in p.parts and p.parts[0]=='source'
        assert row['archive_path']=='source/'+row['runtime_path']
        source=ARCHIVE/row['archive_path'];assert source.is_file()and source.stat().st_size==row['size']and digest(source)==row['sha256'],row['runtime_path']
        if source.suffix=='.py':compile(source.read_bytes(),row['runtime_path'],'exec');compiled+=1
        else:assert source.suffix=='.json';json.loads(source.read_bytes())
    actual={p.relative_to(ARCHIVE).as_posix()for p in(ARCHIVE/'source').rglob('*')if p.is_file()}
    assert actual=={r['archive_path']for r in rows}
    for name,proof in manifest['evidence'].items():
        source=ARCHIVE/name;assert source.stat().st_size==proof['size']and digest(source)==proof['sha256']
    public=json.loads((ARCHIVE/'public-validation.json').read_bytes())
    validation=json.loads((ARCHIVE/'validation.json').read_bytes())
    delivered=json.loads((ARCHIVE/'installed-summary.json').read_bytes())
    expected={r['runtime_path']:r['sha256']for r in rows}
    assert public['ok']and public['public_TLS']and len(public['checks'])==5 and public['source']==expected
    assert validation['ok']and validation['sources']==expected and validation['replay_no_duplicate_reward']and validation['late_encoding_failure_rolls_back']
    assert delivered['release']==manifest['release']and delivered['online_installed']and delivered['own_QA_cleaned']
    assert delivered['source_delta']==11 and delivered['business_files_verified']==1451 and delivered['observation_seconds']>=120
    assert delivered['bytecode_caches_verified']==843 and not delivered['bytecode_source_mismatches']
    for report in(public,validation,delivered):assert not report['natural_GUI']and not report['natural_battle']
    assert not delivered['local_installed']and not delivered['launcher_changed']and not delivered['player_database_restore']
    data=ARCHIVE/'source/els_server/data/growth_guide_boxes.json'
    boxes=json.loads(data.read_bytes());box=next(b for b in boxes['boxes']if b['template']==721749)
    assert len(box['outputs'])==15 and all(r['option_groups']['0']==[40116]*3+[46616]*3 for r in box['outputs'])
    assert json.loads(data.with_suffix('.manifest.json').read_bytes())['payload_sha256']==digest(data)
    return dict(ok=True,source_files=len(rows),python_sources_compiled=compiled,evidence_files=len(manifest['evidence']),online_already_installed=True,default_engine_activated=False,runtime_tests_reexecuted=False)

if __name__=='__main__':print(json.dumps(verify()))
