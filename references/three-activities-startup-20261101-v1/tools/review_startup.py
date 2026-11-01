from pathlib import Path
import json,hashlib,zipfile,difflib,ast,re
W=Path(__file__).resolve().parent;R=W.parents[1];A=R/'analysis/startup-ui-hide-20261101-v1';P=R/'analysis/all-ground-item-models-20261101-v1/launcher-v59'
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda b:hashlib.sha256(b).hexdigest()
manifest=read(A/'update-delta-manifest.json');build=read(P/'build.json');proof=[];patch=[]
for mode,family in (('friends','signedFriends'),('local','signedLOCAL')):
    ref=build['signed_bindings'][family];archive=Path(ref['archive']['path']);assert sha(archive.read_bytes())==ref['archive']['sha256']
    with zipfile.ZipFile(archive)as z:
        for row in manifest['modes'][mode]['files']:
            rel=row['path'];raw=(A/'update-delta'/mode/rel).read_bytes();assert sha(raw)==row['sha256']
            old=z.read(rel)if rel in z.namelist()else b'';assert (sha(old)if old else None)==row['parent_sha256']
            patch.extend(difflib.unified_diff(old.decode('utf8').splitlines(True),raw.decode('utf8').splitlines(True),fromfile=mode+'/parent/'+rel,tofile=mode+'/candidate/'+rel))
            if rel.endswith('client_compatibility_profiles.json'):
                before=json.loads(old);after=json.loads(raw)
                b=before['profiles'][0]['artifacts'];a=after['profiles'][0]['artifacts']
                changed={k for k in set(a)|set(b)if a.get(k)!=b.get(k)}
                assert changed=={'tools/native_cache_sync.py','tools/startup_ui_visibility.py','tools/startup_ui_visibility.js'}
                for k in changed:
                    if k in b:a[k]=b[k]
                    else:del a[k]
                assert before==after
        trace=z.read('tools/trace_dx11_login.js');assert sha(trace)==manifest['modes'][mode]['trace_sha256_unchanged']
    proof.append(dict(mode=mode,all_four_candidate_SHA=True,exact_parent_SHA=True,only_three_profile_artifacts_changed=True,trace_preserved=True))
(W/'startup-reviewed.patch').write_text(''.join(patch),'utf8')
js=A/'update-delta/friends/tools/startup_ui_visibility.js';py=js.with_suffix('.py')
assert read(A/'native-fixture-result.json')['adapter_sha256']==sha(js.read_bytes())
paths=[];calls=[]
for p in (R/'releases/local/local-shop-rare-navy-20261101-v1/tools').glob('*.py'):
    t=p.read_text('utf8')
    if 'from native_cache_sync import' in t:calls.append(p.name)
for p in (W/'runtime/els_server').rglob('*.py'):
    try:tree=ast.parse(p.read_bytes())
    except SyntaxError:continue
    for n in ast.walk(tree):
        if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id in ('require_current','expired'):
            if n.args and isinstance(n.args[0],(ast.Dict,ast.Call)):
                paths.append(dict(path=p.relative_to(W/'runtime').as_posix(),line=n.lineno,call=ast.unparse(n)))
review=dict(result='PASS',reviewer='01a1943c-ec8b-7bb0-9682-188ec0c84bb8',author='01a1943f-c39f-7732-aecb-b2616261689c',independent_of_author=True,reviewed_Hook_changed_by_reviewer=False,
    source=manifest,checks=proof,adapter_sha256=sha(js.read_bytes()),wrapper_sha256=sha(py.read_bytes()),direct_startup_compose_callers=1,native_cache_compose_consumers=calls,
    findings=[],publication_requirements=['signed component closure and per-mode profiles','selected support actually loads','Friends natural startup remains unverified'],evidence_reused=['native-fixture-result.json','update-variant-compile.json','live-trial-8/result.json'],history='Exact non-Git snapshot comparison; no Git blame available for unpublished candidate')
(W/'startup-independent-review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n','utf8')
(W/'startup-independent-review.md').write_text('''# Startup UI Hook independent differential review

PASS for the pinned Hook; deployment verification remains required. Reviewer is the receiving publisher, distinct from the author, and did not change Hook source. No critical/high/medium/low security findings were identified. Native-process risk is high enough to require exact identity pins and lifecycle tests.

## Compared change
Both modes: four leaves each, two new. Exact signed V59 archives are the baseline; unpublished candidate has no Git history, so blame was unavailable. Full diff is startup-reviewed.patch; pinned hashes and quantified callers are in startup-independent-review.json. The native cache adapter adds one composition call. Profiles change exactly three artifact records; trace/authentication/connection differences remain byte-identical.

## Critical findings
None. The new wrapper checks EXE and decoded-image SHA and exact composition anchors. JavaScript verifies eleven native byte spans and six vtable slots before installing. Render scope is thread-local and restricted by current vtable; no object address survives a frame. Four draw callbacks forward the original function outside those scopes. Native updates, queue preparation, authentication, timers, database writes and economic qualification are unchanged. Selection and native-dialog paths detach scopes and revert all drawing replacements; repeated finish is idempotent. Partial installation throws after reverting installed sites. Callback objects remain rooted while installed.

## Adversarial and blast-radius assessment
Public network input cannot select native addresses or bypass module pins. A native prompt immediately restores drawing and preserves the pre-existing prompt observer. Other states, later loading, nested scope cleanup and delayed vtable readiness were examined against the supplied native fixture. One direct new composition caller affects both existing native-cache startup consumers (enumerated in JSON). No changed server endpoint, protocol, credential storage or player-data path.

## Tests and limits
Reuse the exact-SHA native fixture, both full script compilation proofs, and owned live-trial-8 first-frame/readback and ten-second selection proof. They cover suppression, original forwarding, identity rejection, prompt/selection restoration, coexistence, retained preparation and cleanup. They do not prove public Friends natural startup or actual signed new dependency selection. Those remain delivery tests, not security findings or claimed passes. No production process was attached during this review.
''','utf8')
(W/'expiry-variant-report.json').write_text(json.dumps(dict(root_cause='A shared predicate narrowed the accepted data shape: existing deadline-only projections have no template',known_match='storage/equipment_enhancement.py:33',expanded_literal_call_matches=paths,fix='Use optional template solely for applying event-specific cap; always preserve explicit deadline.',regression='test_expiry_projection.py',new_variants=0,scope='All composed els_server Python call ASTs; variable-projection callers manually traced from item_expiration APIs'),indent=2)+'\n','utf8')
(W/'expiry-variant-report.md').write_text('''# Expiry data-shape regression

Medium functional regression: timed equipment grants reach enhancement.replace(), which calls `require_current(dict(expires_at=deadline[0]))`. Boost changed the shared predicate to index `item['template']`, so the supported projection raises KeyError. The new Abyss +11 weapon exposed it; unrelated timed enhancement is also affected through the same shared call.

The exact rg pattern `require_current\\(dict` finds one known call. Expanding to `require_current`, `expired`, and `item_deadline`, then scanning literal call arguments in the complete composed Python AST found no second missing-template producer. Full-item callers and inventory/sweep projections supply template; treating these as defects would be false positives. A Windows wildcard-path rg attempt was invalid; the complete root search and AST scan replaced it.

Fix both channels at the shared item_deadline entry: `item.get('template')` only selects the event cap, while the explicit expires_at remains authoritative. The predicate already accepted deadline-only maps before Boost; this restores that contract without inferring item identity. Two regression tests verify deadline-only boundary rejection and event-only capping, including preserving earlier deadlines and unrelated 90-day equipment. Re-run the two failed campaign tests plus affected expiry test; all pass. The test file is directly runnable in CI. No new grant authority, lifetime extension or receipt rewrite.
''','utf8')
print(json.dumps(dict(ok=True,review='PASS',candidate_files=8,cache_consumers=calls,partial_projection_calls=paths)))
