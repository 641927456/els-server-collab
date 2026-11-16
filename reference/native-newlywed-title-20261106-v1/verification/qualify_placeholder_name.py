"""Correct a public placeholder variable name; prove native output unchanged."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,sys

T=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
save=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
old=T/'candidate-v1';new=T/'candidate-v2';archive=T/'git-archive-v2'
assert not archive.exists()
if new.exists():
    assert all(sha(new/p.relative_to(old))==sha(p)for p in old.rglob('*')if p.is_file())
else:shutil.copytree(old,new)
p=new/'tools/native_title_options.py';before=p.read_text('utf8')
after=before.replace('token','placeholder')
assert before.count('token')==3 and after.replace('placeholder','token')==before
p.write_text(after,'utf8')
spec=importlib.util.spec_from_file_location('qualified_title_placeholder',p)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
snapshot=Path('G:/els/analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
qualified=(T/'composed-title-candidate.js').read_text('utf8')
pins={r:snapshot[r:r+16].hex()for r in(0xfe7560,0x216fe40,0x2181ed0,0xb11a90)}
prefix=(old/'tools/native_title_options.js').read_text('utf8').replace('__TITLE_OPTION_PINS__',json.dumps(pins))+'\n'
assert qualified.startswith(prefix)
anchor=' installElsTitleOptionData();\n installElsGuildNativePower();'
tail=qualified[len(prefix):];assert tail.count(anchor)==1
parent=tail.replace(anchor,' installElsGuildNativePower();')
assert helper.compose(snapshot,parent)==qualified
assert sha(new/'tools/native_cache_sync.py')==sha(old/'tools/native_cache_sync.py')
assert sha(new/'tools/native_title_options.js')==sha(old/'tools/native_title_options.js')
pins={p.relative_to(new).as_posix():sha(p)for p in new.rglob('*')if p.is_file()}
assert len(pins)==3
reuse=dict(ok=True,change='Local Python name token -> placeholder for a public source marker; no credential present.',
    candidate_pins=pins,qualified_native_composed_source_sha256=hashlib.sha256(qualified.encode()).hexdigest(),
    full_composed_native_source_byte_identical=True,original_120_second_native_result_reused=True,
    native_result='native-candidate-title-proof-v1.json',native_runtime_JS_file_unchanged=True,
    exact_v2_Python_file_not_executed_inside_Game=True,CI_failure_retained=dict(run=42216552452,job=127887903689),
    main_merged=False,installed=False,public_progress_updated=False)
save(T/'composition-reuse-v2.json',reuse)
shutil.copytree(T/'git-archive-v1',archive)
for rel in pins:(archive/'source'/rel).write_bytes((new/rel).read_bytes())
binding=json.loads((archive/'source-binding.json').read_bytes())
for row in binding['source_files']:
    row['sha256']=pins[row['path']];row['size']=(new/row['path']).stat().st_size
binding['source_qualification']='v1 actual Game run plus byte-identical complete generated native script proof in composition-reuse-v2.json'
save(archive/'source-binding.json',binding)
(archive/'composition-reuse-v2.json').write_bytes((T/'composition-reuse-v2.json').read_bytes())
(archive/'verification/qualify_placeholder_name.py').write_bytes(Path(__file__).read_bytes())
with (archive/'README.md').open('a',encoding='utf8')as f:
    f.write('\nCI把公开源码占位符变量名识别为疑似凭据；v2仅改该局部变量名。完整生成脚本与已通过实际Game的v1逐字节相同，复用其运行结果；原失败CI保留。\n')
save(T/'candidate-manifest-v2.json',dict(schema_version=2,parent_PR=900,
    parent_head='8ebfa613a3097429aaef7b80f7693e3bcd1e392a',
    files=[dict(path=k,sha256=v,size=(new/k).stat().st_size)for k,v in sorted(pins.items())],
    native_result_reuse='composition-reuse-v2.json'))
print(json.dumps(dict(ok=True,files=len(pins),archive_files=sum(p.is_file()for p in archive.rglob('*')),manifest_sha256=sha(T/'candidate-manifest-v2.json'))))
