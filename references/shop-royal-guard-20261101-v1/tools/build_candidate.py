"""Add the omitted CN-preview Royal Guard machine to an isolated runtime."""
from pathlib import Path
import collections, hashlib, json, shutil, struct, sys

W = Path(__file__).resolve().parent
R = W.parents[1]
C = W/'candidate'
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
binding = {ch: read(R/f'releases/{ch}/current.json') for ch in ('online', 'local')}
P = R/binding['online']['path']
manifest = P/'rollup-manifest.json'
assert sha(manifest) == binding['online']['manifest_sha256']
assert not C.exists()
for row in read(manifest)['files']:
    src = P/row['path']
    assert src.stat().st_size == row['size'] and sha(src) == row['sha256'], row['path']
    dst = C/row['path']
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
(W/'binding.json').write_text(json.dumps(dict(parents=binding, parent_root=str(P)), indent=2)+'\n', 'utf8')

B = C/'analysis/client-6c6b5180'
preview = '20261014-062215/ice-resources/IceHeaterPreView.tables.json'
machine = 163483
mapping = collections.defaultdict(set)
for call in read(B/preview)['__symbolic_calls__']:
    if call['function'].endswith('.AddIceHeaterItemData'):
        _, m, reward, role, *_ = call['arguments']
        if m == machine:
            assert type(role) is int and 1 <= role <= 11
            mapping[str(role)].add(reward)
assert set(mapping) == {str(n) for n in range(1, 12)}

native = read(B/'native-ice-shop-catalog.json')
roles = read(B/'role-ice-catalog.json')
assert machine not in {r['template'] for r in native['offers']}
assert str(machine) not in roles['pools']
records = {r['id']: r for r in read(B/'20261014-172532/all-ice-candidates.json')['rows']}
record = records[machine]
raw = bytes.fromhex(record['record_hex'])
flags4, flags8 = struct.unpack_from('<II', raw, 4)
assert len(raw) == 232 and not flags4 & 33 and (flags8 >> 3) & 31 == 7
definitions = [r['arguments'][1] for r in read(B/'20261014-062215/ice-resources/RandomItem.all-tables.json')['__symbolic_calls__']
               if r['function'].endswith('.AddRandomItemTemplet') and r['arguments'][1]['m_ItemID'] == machine]
assert len(definitions) == 1
definition = definitions[0]
assert definition['m_KeyItemID'] == definition['m_RequiredKeyCount'] == 0 and definition['m_iGiveCount'] == -1
assert definition['m_UseCondition'] == {'global': 'USE_CONDITION.UC_ONE_UNIT'}
rewards = {r['template']: r for r in roles['rewards']}
for role, pool in mapping.items():
    # These are identical native series members already supported for this role.
    assert pool == set(roles['pools']['900167'][role])
    assert all(t in rewards for t in pool)
offer = dict(template=machine, name=record['name'], metadata=raw[7] & 15, group=4,
             max_stack=99, category=34, price=30, record_hex=raw.hex(),
             reward_pool=sorted(mapping['1']), random_definition=definition, character_type=1)
native['offers'].append(offer)
native['offers'].sort(key=lambda r: r['template'])
roles['pools'][str(machine)] = {role: sorted(pool) for role, pool in mapping.items()}
source = dict(path=preview, sha256=sha(B/preview))
for data in (native, roles):
    assert preview not in {r['path'].replace('\\', '/') for r in data['sources']}
    data['sources'].append(source)

# Execute the original reader/classifier for the sole new template. Existing
# unchanged definition proofs are reused; no live process or player data.
sys.path[:0] = [str(R/'tools'), str(R/'tools/pylibs')]
from role_native_replay import Replay, IMAGE_SHA
replay = Replay()
seed = read(B/'item-body-candidate.json')
wire = bytearray.fromhex(seed['wire_hex'])
values = {0: machine, 4: offer['metadata'], 5: 1}
for field in seed['fields']:
    offset = int(field['offset'], 0)
    if offset in values:
        size = 1 if offset == 4 else 4
        wire[field['wire_offset']:field['wire_offset']+size] = values[offset].to_bytes(size, 'big')
decoded = replay.item(bytes(wire))
assert decoded['ok'] == 1 and decoded['consumed'] == len(wire) == 304
dto = bytes.fromhex(decoded['dto'])
for field in seed['expected_memory']:
    expected = (values[field['offset']].to_bytes(field['size'], 'little')
                if field['offset'] in values else bytes.fromhex(field['hex']))
    assert dto[field['offset']:field['offset']+field['size']] == expected
vectors = [struct.unpack_from('<QQQ', dto, o) for o in (0xd, *[0x25+i*0x18 for i in range(33)])]
assert all(a == b and a <= cap for a, b, cap in vectors)
ptr = replay.alloc(232)
replay.write(ptr, raw)
assert replay.call(0x19803a0, 0, ptr) == 4
proof_row = dict(template=machine, ok=1, consumed=304, fields_match=True, vectors_empty=True,
                 native_template_id=machine, native_name=offer['name'], native_group=4,
                 private_data_item=dict(template_id=machine, metadata=offer['metadata'], count=1),
                 applied_to_game=False, no_reward_persistence=True, record_sha256=hashlib.sha256(raw).hexdigest(),
                 evidence='Original D9A550/19803A0 in private Unicorn memory', image_sha256=IMAGE_SHA)

def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', 'utf8')

for name, data in (('native-ice-shop', native), ('role-ice', roles)):
    catalog_path = B/(name+'-catalog.json')
    proof_path = B/(name+'-body-proof.json')
    proof = read(proof_path)
    proof['previous_catalog_sha256'] = sha(catalog_path)
    save(catalog_path, data)
    proof['catalog_sha256'] = sha(catalog_path)
    if name == 'native-ice-shop':
        proof['rows'].append(proof_row)
    save(proof_path, proof)

common_path = C/'analysis/shop-standalone-20261015/ice-common.json'
common = read(common_path)
assert str(machine) not in common['machine_profiles']
common['machine_profiles'][str(machine)] = 'ice'
proof_path = common_path.with_name('ice-common-body-proof.json')
proof = read(proof_path)
proof['previous_catalog_sha256'] = sha(common_path)
save(common_path, common)
proof['catalog_sha256'] = sha(common_path)
save(proof_path, proof)
delta = [row['path'] for row in read(manifest)['files'] if sha(C/row['path']) != row['sha256']]
assert len(delta) == 6, delta
save(W/'scope.json', dict(machine=machine, name=offer['name'], roles=sorted(map(int, mapping)),
     pool_sizes={r: len(p) for r, p in mapping.items()}, price_ED=30, cosmetic_weight=1000,
     common_weight=9000, delta=delta, native_reader_cases=1, new_rewards=0,
     source_preview=source, original_EXE_KOM_modified=False, installed=False))
print(json.dumps(dict(ok=True, delta=delta, roles=len(mapping), native_reader_cases=1)))
