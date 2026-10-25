"""Pinned original category77 (PC cafe equipment) membership.

Derived from the three original DivisionItem resources, including all Cobo
alias pairs. Verified with native insertion, loader suffix and lookup. This
does not infer the owner+7BD field, select a preset, or enable an Apply route.
"""
import hashlib
import json

CATALOG_SHA256 = 'e674a022382bfabbed417fdbe83d4667683407d92b1a80b573ae6596fbf861a7'


def load_original_category77(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError('Pinned original category77 catalog required')
    data = json.loads(raw)
    if data['schema'] != 1 or data['category'] != 77:
        raise ValueError('Unsupported original registry')
    return frozenset(data['item_ids'])


def classify_templates(templates, *, registry):
    """Return explicit membership; callers retain all other admission gates."""
    if type(registry) is not frozenset or type(templates) not in (tuple, frozenset):
        raise ValueError('Explicit registry and immutable template IDs required')
    if any(type(t) is not int or not 0 < t < 2**31 for t in templates):
        raise ValueError('Invalid original item template')
    return {t: t in registry for t in templates}
