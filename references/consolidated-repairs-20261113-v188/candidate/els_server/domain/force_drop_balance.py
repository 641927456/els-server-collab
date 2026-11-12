"""Independent local Force draws, restricted to each original clear pool."""
import functools
import hashlib
import uuid


@functools.lru_cache(maxsize=1)
def books():
    from els_server.domain.native_force_catalog import catalog
    return {row['item']: row for row in catalog()['books']}


def managed(template):
    return template in (135911, 136174) or template in books()


def _random(run_id, identity, owner, category):
    seed = uuid.UUID(run_id).bytes + f':{identity}:{owner}:force-balance-v1:{category}'.encode()
    return hashlib.sha256(seed).digest()


def clear_draws(identity, run_id, owner, *, group, drop_bp, multiplier):
    from els_server.domain.formal_pve_economy import policy
    from els_server.domain.elixir_economy import hit
    from els_server.domain.gm_rates import formal_drop_chance
    p = policy()
    row = p['maps'][str(identity)]
    if not row['additional_clear_drop']:
        return []
    config = p['force_drop_balance']
    pool = {t for values in row['current_display_pool'].values() for t in values}
    definitions = books()
    graded = sorted(t for t in pool if t in definitions and definitions[t]['native_grade'] in (1, 2, 3))
    legends = sorted(t for t in pool if t in definitions and definitions[t]['native_grade'] == 6)
    result = []

    def roll(category, rate, candidates, *, weighted=False):
        if not candidates:
            return
        digest = _random(run_id, identity, owner, category)
        chance = formal_drop_chance(rate, 10000, multiplier)
        if not hit(*chance, lambda size: int.from_bytes(digest[:16], 'big') % size, drop_bp):
            return
        if weighted:
            mark = int.from_bytes(digest[16:24], 'big') % 100
            end = 0
            for grade, weight in config['grade_weights'].items():
                end += weight
                if mark < end:
                    candidates = [t for t in candidates if definitions[t]['native_grade'] == int(grade)]
                    break
        result.append(candidates[int.from_bytes(digest[24:], 'big') % len(candidates)])

    if graded:
        unique_only = all(definitions[t]['native_grade'] == 1 for t in graded)
        roll('skill', config['standalone_unique_bp'] if unique_only else config['graded_book_bp'],
             graded, weighted=not unique_only)
    # The original Hall of El legendary book remains solo-only.
    if not group or identity not in (140010, 140020, 140030):
        roll('legendary', config['legendary_bp'], legends)
    if 135911 in pool:
        master = any(definitions[t]['required_master'] for t in graded)
        roll('material-a', config['master_material_a_bp'] if master else config['material_a_bp'], [135911])
    if 136174 in pool:
        roll('material-e', config['material_e_bp'], [136174])
    return result
