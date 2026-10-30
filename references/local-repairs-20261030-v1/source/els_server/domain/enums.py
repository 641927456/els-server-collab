"""Native client symbol table for the pinned DX11 client.

Every entry is a literal integer taken from the client's own Enum chunk: 29 flat
constants plus 718 named tables, 36,578 literals in total. The reason this file
exists is that earlier imports had to hand-pick the symbol slices they needed
(355 PET_UNIT_ID values here, 30 CUSTOMIZING_TYPE values there). With the whole
table resident, a later importer can ask for `lookup('PET_UNIT_ID.PUI_TEST')`
and get the same number the client uses.

Resolving a symbol is not a capability. Nothing here grants, unlocks or
authorises anything; a caller still needs an explicit native reason to use the
number it gets back.

Eleven C-enum END sentinels are emitted by the client as `{"global": NAME}`
instead of a number. They are kept verbatim in `opaque()` rather than given an
invented value, so a caller that needs one has to say so explicitly.
"""
import functools
import hashlib
import json

from els_server.game_data import CLIENT_SHA
from els_server.paths import PROJECT_ROOT

DATA = PROJECT_ROOT / 'els_server/data/enums.json'


@functools.lru_cache(maxsize=1)
def _payload():
    data = json.loads(DATA.read_text(encoding='utf8'))
    if data.get('client_sha256') != CLIENT_SHA:
        raise ValueError('Enum client mismatch')
    for source in data.get('sources', []):
        path = PROJECT_ROOT / source['path']
        # The analysis artifacts ship in the runtime asset archive, not in git.
        # Verify them whenever they are present so drift cannot pass silently.
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Enum source changed: %s' % source['path'])
    return data


def constants():
    """Flat top-level constants such as TRUE/FALSE/NULL and the font ids."""
    return dict(_payload()['constants'])


def tables():
    """Every named table as `{table: {symbol: int}}`."""
    return {name: dict(body) for name, body in _payload()['tables'].items()}


def table(name):
    """One named table, or ValueError when the client has no such table."""
    body = _payload()['tables'].get(name)
    if body is None:
        raise ValueError('Unknown enum table: %r' % (name,))
    return dict(body)


def table_names():
    """Sorted table names, for discovery without loading the bodies."""
    return tuple(sorted(_payload()['tables']))


def value(name, symbol):
    """The integer for `symbol` inside table `name`."""
    body = table(name)
    if symbol not in body:
        raise KeyError('%s.%s' % (name, symbol))
    return body[symbol]


def lookup(text):
    """Resolve `"TABLE.SYMBOL"`, or a bare flat constant such as `"TRUE"`.

    A bare symbol is only accepted when it is a top-level constant; searching
    every table for it would be ambiguous, because names like `SGI_END` and
    `AET_MAX` are reused across tables.
    """
    if not isinstance(text, str) or not text:
        raise ValueError('Symbol text required')
    if '.' in text:
        name, _, symbol = text.partition('.')
        return value(name, symbol)
    held = _payload()['constants']
    if text not in held:
        raise KeyError(text)
    return held[text]


@functools.lru_cache(maxsize=None)
def _reverse(name):
    index = {}
    for symbol, number in table(name).items():
        index.setdefault(number, []).append(symbol)
    return {number: tuple(sorted(symbols)) for number, symbols in index.items()}


def reverse(name, number):
    """Every symbol in `name` that carries `number` (the client reuses values)."""
    return tuple(_reverse(name).get(int(number), ()))


def aliases(name):
    """`{number: symbols}` for the entries of `name` that share a number."""
    return {number: symbols for number, symbols in _reverse(name).items()
            if len(symbols) > 1}


def opaque():
    """The END sentinels the client emits as `{"global": NAME}`, kept verbatim."""
    return {name: dict(body) for name, body in _payload()['opaque'].items()}


def summary():
    return dict(_payload()['summary'])
