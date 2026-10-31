"""Weak root index: sessions, queued work and recovery tickets own lifetime.

Role objects stay cached on their live root. Root/role cycles are collected by
Python GC after the last real owner disappears; this is not an idle timeout.
"""
import threading
import weakref


def _retired(cache_ref):
    cache = cache_ref()
    if cache is not None:
        with cache._stats_lock:
            cache._reclaimed += 1


class AccountCache(weakref.WeakValueDictionary):
    def __init__(self):
        super().__init__()
        self._stats_lock = threading.RLock()
        self._tracked = weakref.WeakSet()
        # The native channel handoff retains accepted terms for the process,
        # independently of heavy account/role objects. Holders never own roots.
        self._terms = {}
        self._created = self._reclaimed = self._maximum = 0

    def __setitem__(self, key, value):
        with self._stats_lock:
            holder = self._terms.setdefault(key, [False])
            if getattr(value, 'terms_accepted', False):
                holder[0] = True
            value._account_terms = holder
            value.terms_accepted = holder[0]
            super().__setitem__(key, value)
            if value not in self._tracked:
                self._tracked.add(value)
                self._created += 1
                weakref.finalize(value, _retired, weakref.ref(self))
            self._maximum = max(self._maximum, len(self))

    def snapshot(self):
        # Own these roots while counting; weakref retirement may run on the
        # worker or event-loop thread. Do not expose identities as labels.
        with self._stats_lock:
            roots = list(self.values())
        roles = {id(role) for root in roots
                 for role in list(getattr(root, 'character_accounts', {}).values())}
        with self._stats_lock:
            return dict(roots=len(roots), roles=len(roles),
                        roots_created=self._created, roots_reclaimed=self._reclaimed,
                        roots_maximum=self._maximum, terms_entries=len(self._terms))
