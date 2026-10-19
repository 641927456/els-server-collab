"""Current native crafting definitions, with no inferred reward probabilities."""
import copy
import functools
import hashlib
import json
from els_server.game_data import DATA_DIR, CLIENT_SHA, client_data

COUNTS = dict(recipes=12360, result_groups=12646, result_registrations=27067,
              village_registrations=1684, limits=1, period_item_allowlist=45)


def counts(data):
    return dict(recipes=len(data['recipes']), result_groups=len(data['result_groups']),
                result_registrations=sum(map(len, data['result_groups'].values())),
                village_registrations=len(data['village_registrations']),
                limits=len(data['limits']), period_item_allowlist=len(data['period_item_allowlist']))


class ManufactureData:
    def __init__(self, directory=DATA_DIR):
        raw = (directory/'manufacture.json').read_bytes()
        manifest = json.loads((directory/'manufacture.manifest.json').read_text(encoding='utf8'))
        data = json.loads(raw)
        if (manifest.get('schema_version') != 1 or manifest.get('client_sha256') != CLIENT_SHA
                or manifest.get('sha256') != hashlib.sha256(raw).hexdigest()
                or manifest.get('source_catalog_sha256') != client_data().manifest['catalog_sha256']
                or manifest.get('counts') != COUNTS or counts(data) != COUNTS):
            raise ValueError('Manufacture catalog identity')
        self._data, self._manifest = data, manifest

    @property
    def manifest(self):
        return copy.deepcopy(self._manifest)

    def ids(self):
        return tuple(sorted(map(int, self._data['recipes'])))

    def recipe(self, identity):
        if type(identity) is not int or str(identity) not in self._data['recipes']:
            raise ValueError('Unknown manufacture definition')
        recipe = self._data['recipes'][str(identity)]
        result = dict(definition=recipe,
            result_registrations=self._data['result_groups'].get(str(recipe['m_ResultGroupID']), []),
            village_registrations=[r for r in self._data['village_registrations'] if r[0] == identity],
            limits=[r for r in self._data['limits'] if r['LimitManufactureID'] == identity],
            transaction_implemented=False,
            caveat='Result registrations specify candidate IDs, not quantities, probability or availability.')
        return copy.deepcopy(result)

    def period_rules(self):
        return copy.deepcopy({k:self._data[k] for k in ('global_reset','limits','period_item_allowlist')})


@functools.lru_cache(maxsize=1)
def manufacture_data():
    return ManufactureData()
