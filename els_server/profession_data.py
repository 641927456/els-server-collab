"""Pinned profession definitions; no inferred advancement or crafting outcomes."""
import copy
import functools
import hashlib
import json
from els_server.game_data import DATA_DIR, CLIENT_SHA


REGISTRATION_COUNTS = {
    'AddProfessionTemplet_LUA': 3,
    'SetMaxAccumulatedBonusCount': 1,
    'SetMaxAccumulatedEDByLevel': 10,
    'SetAccumulatedEDSpecialItem': 10,
    'SetResetAnvilPeriod': 1,
    'AddSpecialMaterialItemDataByLevel': 13,
    'AddMaxBlackSmithHammerByLevel': 10,
    'SetSpecialMaterialItemID': 1,
    'AddResolveMaterialQuantity': 14,
    'SetDiscountPercentageReforgingFee': 10,
    'SetProfessionItemUseCountByLevel': 11,
    'SetProfessionFreeChangeMaxCount': 1,
    'SetProfessionFreeChangeCostED': 3,
}


def validate_registrations(calls):
    if not isinstance(calls, list) or len(calls) != sum(REGISTRATION_COUNTS.values()):
        raise ValueError('Profession registration coverage')
    grouped = {key: [] for key in REGISTRATION_COUNTS}
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get('function'), str):
            raise ValueError('Profession registration type')
        prefix = 'g_pProfessionManager.'
        name = call['function'].removeprefix(prefix)
        args = call.get('arguments')
        if (not call['function'].startswith(prefix) or name not in grouped
                or not isinstance(args, list) or len(args) < 2
                or args[0] != {'global': 'g_pProfessionManager'}):
            raise ValueError('Profession registration owner/name')
        grouped[name].append(args[1:])
    if any(len(grouped[k]) != n for k, n in REGISTRATION_COUNTS.items()):
        raise ValueError('Profession registration family coverage')
    templates = grouped['AddProfessionTemplet_LUA']
    if any(len(args) != 1 or not isinstance(args[0], dict) for args in templates):
        raise ValueError('Profession template registration')
    if sorted(args[0].get('m_eType', -1) for args in templates) != [1, 2, 3]:
        raise ValueError('Profession type coverage')
    for args in templates:
        titles = args[0]['m_wstrTitleList']
        # Bytecode tables use integer keys; JSON represents the same keys as strings.
        if len(titles) != 10 or {str(k) for k in titles} != set(map(str, range(1, 11))):
            raise ValueError('Profession title level coverage')
    return grouped


class ProfessionData:
    def __init__(self, directory=DATA_DIR):
        raw = (directory/'professions.json').read_bytes()
        manifest = json.loads((directory/'professions.manifest.json').read_text(encoding='utf8'))
        if (manifest.get('schema_version') != 1 or manifest.get('client_sha256') != CLIENT_SHA
                or manifest.get('sha256') != hashlib.sha256(raw).hexdigest()
                or manifest.get('registration_counts') != REGISTRATION_COUNTS):
            raise ValueError('Profession catalog identity')
        calls = json.loads(raw)['__symbolic_calls__']
        self._grouped = validate_registrations(calls)
        self._templates = {args[0]['m_eType']: args[0] for args in self._grouped['AddProfessionTemplet_LUA']}
        self._manifest = manifest

    @property
    def manifest(self):
        return copy.deepcopy(self._manifest)

    def template(self, profession):
        if type(profession) is not int or profession not in self._templates:
            raise ValueError('Unknown profession template')
        return copy.deepcopy(self._templates[profession])

    def registrations(self, method):
        """Original callback arguments after the receiver, with no fee assumptions."""
        if not isinstance(method, str) or method not in self._grouped:
            raise ValueError('Unknown profession registration method')
        return copy.deepcopy(self._grouped[method])

    def settings(self):
        return {method: self.registrations(method) for method in self._grouped if method != 'AddProfessionTemplet_LUA'}


@functools.lru_cache(maxsize=1)
def profession_data():
    return ProfessionData()
