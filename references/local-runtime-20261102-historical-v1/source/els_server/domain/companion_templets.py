"""Native pet and mount behaviour templates for the pinned DX11 client.

`companions.catalog()` only answers "which unit does this activation item create"
because it is built from the native PetData / RidingPetData create-item records.
This module adds the behaviour layer decoded from the native templets:

  * pet evolution EXP tiers, scripts, appetite and caprice, inventory slot size,
    attribute, and the per-tier attack / cheer / aura skill symbols
  * mount stamina rates, viewer size, and the per-tier attack / buff skill symbols

Nothing here activates a pet or a mount. It is a read-only catalog: the feeding,
evolution, skill and stamina business rules remain unimplemented, and the
`mount_globals` block carries closure indices only, not decoded formulas.
"""
import functools
import hashlib
import json
from pathlib import Path

from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT

DATA = PROJECT_ROOT / 'els_server/data/companion_templets.json'
KINDS = ('pet', 'mount')


@functools.lru_cache(maxsize=1)
def _payload():
    data = json.loads(DATA.read_text(encoding='utf8'))
    if data.get('client_sha256') != CLIENT_SHA:
        raise ValueError('Companion templet client mismatch')
    for source in data.get('sources', []):
        path = PROJECT_ROOT / source['path']
        # The analysis artifacts ship in the runtime asset archive, not in git.
        # Verify them whenever they are present so drift cannot pass silently.
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Companion templet source changed: %s' % source['path'])
    data['pet'] = {int(k): v for k, v in data['pet'].items()}
    data['mount'] = {int(k): v for k, v in data['mount'].items()}
    return data


def catalog(kind):
    """Return {unit_id: templet} for 'pet' or 'mount'."""
    if kind not in KINDS:
        raise ValueError('Unknown companion kind: %r' % (kind,))
    return _payload()[kind]


def templet(kind, unit_id):
    """Return one native templet, or None when the client has no entry for it."""
    return catalog(kind).get(int(unit_id))


def evolution_exp(unit_id):
    """Native per-tier evolution EXP thresholds, or [] when unknown."""
    entry = templet('pet', unit_id)
    return list(entry.get('evolution_exp') or []) if entry else []


def skill_symbols(kind, unit_id):
    """Per-tier native skill symbols, e.g. {'attack': [...], 'cheer': [...]}."""
    entry = templet(kind, unit_id)
    return dict(entry.get('skills') or {}) if entry else {}


def mount_rules():
    """Mount stamina / speed globals. Formulas are NOT decoded; see `decoded`."""
    return dict(_payload().get('mount_globals') or {})
