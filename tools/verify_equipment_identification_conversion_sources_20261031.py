"""Portable six-leaf identity and exact conversion interval verification.

Native catalog/record identity needs the locked runtime assets. This portable
check verifies the committed archive and executes its real selection algorithm
against explicit in-memory item registration fixtures only.
"""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
AREA = ROOT / 'references/equipment-identification-conversion-20261031-v1'


def read(path):
    return json.loads(path.read_bytes())


def verify():
    contract = read(AREA / 'source-contract.json')
    assert len(contract['files']) == 6
    for row in contract['files']:
        path = ROOT / row['source']
        assert path.resolve().is_relative_to(AREA.resolve())
        raw = path.read_bytes()
        assert len(raw) == row['size']
        assert hashlib.sha256(raw).hexdigest() == row['sha256']
        if path.suffix == '.py':
            ast.parse(raw)
    data = AREA / 'source/els_server/data'
    identification = read(data / 'identification_ui.json')
    assert len(identification['native_templates']) == 917
    assert len(identification['hero_common_policy']['templates']) == 16
    assert set(map(int, identification['unresolved_native_templates'])) == {
        118332, 118333, 118334, 118335,
    }
    for row in identification['native_templates'].values():
        assert len(row['native_groups']) == len(row['pool_groups'])
        assert all(str(group) in identification['native_pools'] for group in row['pool_groups'])
    accessories = read(data / 'accessory_identification_groups.json')
    screened = contract['screened_accessory_templates']
    assert len(screened) == 65 and len(set(screened)) == 65
    used = {str(group) for row in identification['native_templates'].values() for group in row['pool_groups']}
    for template in screened:
        row = accessories['templates'][str(template)]
        used.update(str(group) for group in row['native_groups'])
        assert all(str(group) in accessories['pools'] for group in row['native_groups'])
    assert len(used) == 194
    for pool in identification['native_pools'].values():
        assert sum(row['weight'] for row in pool['outcomes']) == 10000

    catalog = read(data / 'market_conversion.json')
    reference = read(AREA / 'nebulon-published-weights.json')
    armor = catalog['rules']['1']
    expected = {str(row['native_group']): row['group_weight'] for row in reference['families']}
    assert armor['group_weights'] == expected
    assert len(expected) == 18 and sum(expected.values()) == 100000
    assert [expected[str(i)] for i in (1, 2, 3)] == [833, 833, 834]
    assert all(expected[str(i)] == 6500 for i in range(4, 19))
    assert sum(row['index'] == 1 for row in catalog['targets'].values()) == 60
    for family in reference['families']:
        ids = armor['groups'][str(family['native_group'])]
        assert len(ids) == 10 and set(ids) == {row['option'] for row in family['outcomes']}
        assert all(row['conditional_weight'] == 10 for row in family['outcomes'])
    weapon = catalog['rules']['0']
    assert weapon['group_weights'] == {key: 1 for key in weapon['groups']}

    # Supply only the external identity dependencies; draw/validate/target are
    # executed from the exact archived business module, without reimplementing it.
    game_data = types.ModuleType('els_server.game_data')
    game_data.CLIENT_SHA = contract['client_sha256']
    def no_runtime_assets():
        raise AssertionError('Portable validation must not claim native identity validation')
    game_data.client_data = no_runtime_assets
    inventory = types.ModuleType('els_server.domain.inventory_items')
    ids = list(map(int, catalog['targets']))
    inventory.VERIFIED_TEMPLATES = dict.fromkeys(ids, 1)
    inventory.TEMPLATE_BAG_GROUPS = dict.fromkeys(ids, 1)
    inventory.TEMPLATE_MAX_STACKS = dict.fromkeys(ids, 1)
    fixtures = {'els_server.game_data': game_data, 'els_server.domain.inventory_items': inventory}
    prior = {key: sys.modules.get(key) for key in fixtures}
    sys.modules.update(fixtures)
    try:
        path = AREA / 'source/els_server/domain/market_conversion_rules.py'
        spec = importlib.util.spec_from_file_location('qualified_equipment_conversion', path)
        rules = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rules)
        assert rules.DATA_SHA == hashlib.sha256((data / 'market_conversion.json').read_bytes()).hexdigest()
        rules.catalog = lambda: catalog
        template = next(int(key) for key, row in catalog['targets'].items() if row['index'] == 1)
        keys = list(armor['groups'])
        cases = 0
        for first in keys:
            remaining = [key for key in keys if key != first]
            for second in remaining:
                final = [key for key in remaining if key != second]
                for third in final:
                    selected = [first, second, third]
                    for high in (False, True):
                        draws = []
                        for family, available in zip(selected, (keys, remaining, final)):
                            base = sum(expected[key] for key in available[:available.index(family)])
                            draws.extend((base + (expected[family] - 1 if high else 0), 9 if high else 0))
                        bounds = []
                        def rng(limit):
                            bounds.append(limit)
                            return draws.pop(0)
                        assert rules.draw(template, rng) == [armor['groups'][key][9 if high else 0] for key in selected]
                        assert bounds == [100000, 10, 100000 - expected[first], 10,
                                          100000 - expected[first] - expected[second], 10]
                        cases += 1
        assert cases == 9792
    finally:
        for key, value in prior.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return dict(ok=True, files=6, conversion_interval_cases=cases,
                native_runtime_identity_checked=False, player_data_included=False)


if __name__ == '__main__':
    print(json.dumps(verify()))
