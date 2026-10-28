# Native server attribute route — Issue593

The existing service sends naked B6 inputs and retains the previously accepted
V39/V40 components. This work completes a server-produced native attribute
notification without changing the client or adding a Hook. The current source
archive contains the implementations and portable native-result regressions;
live source assembly and gameplay acceptance are being completed before the
runtime profile selects this route.

`native_attribute_messages.py` encodes the complete original106 grammar.
`native_equipment_attributes.py` includes the original post-enhancement reforge
merge and the source-pinned0.4 alternate-mode coefficient.
`native_passive_attributes.py` and `native_attribute_projection.py` preserve
float32 source order, immutable percentage bases and the original small HP
epsilon. `native_attribute_snapshot.py` obtains the owned role, current title,
skill/force/guild/collection inputs and all attached item instances in one
read-only SQL transaction. It does not borrow cached projections or migrate
an optional table.
It also captures the selected ERP page, every saved page, profile metadata and
account progress under that same read transaction. The canonical allocation
writer must finish synchronization before this reader accepts an enabled
profile. A real two-page fixture verifies switching during an external commit;
missing metadata/pages and stale earned levels never become zero allocations.
The quest-role helper is deliberately narrow. Same-connection attachments add
the actual title/qualification, owned and equipped forces, visible traits,
ordinary-page metadata and LuCiel selector. Nonempty real-store fixtures and
an external multi-field commit verify those inputs independently of fresh
character defaults.

The native power modules retain the complete89B430 arithmetic and988320
normalization. The3F8 map uses the original `(probability, flag)` key so both
flags at the same threshold contribute independently. The conditional phase
ports all25 B26140 types, including native floorf/cap/epsilon behavior in the
qualified finite domain. Context offsets remain explicit until their full
producer is qualified; no omitted input becomes a plausible zero.

The option scalar source normalizes57 leaves, including shared MP restoration
before percentage conversion.136 independent original records agree across63
fields. The original five-field `STAT` dictionary uses `m_fBaseHP`; `m_fMaxHP`
is not that source property. Native scalar/data merging retains unscaled
capability fields, max aggregation, both phase modes and conditional branches.
The wrapper keeps its original phase order, including the data merge before
the class-line scalar predicate. The probability map preserves both flags at
the same threshold and the original zero-threshold fallback30. Capability-map
increments and additional-damage values retain their separate scaling rules.

The current15 ERP coefficient/cap/exclusion entries agree with the whole
original D36B90 Lua registration. Its registered manager feeds the whole
887F00 consumer in both modes;36 phase controls additionally cover dense,
absent, capped and overridden point indexes. The game constructor's guarded
scale defaults to1; caller-supplied later configuration still needs binding.

All70522 current definitions pass the scalar/metadata/map/condition/STAT
source compiler. All639 condition rows additionally pass the original property
body.128 native entry controls and108 duplicate/line/mode append controls
retain the separate qualification and contribution phases. The20 context
producer controls derive the25 condition types from the preceding aggregate;
B26830 writes attack data and extended scalars into separate records.
The copied condition category map is the preceding skill-damage map at778,
distinct from cooldown798. The second collector preserves9873F0/B23F70:
292 original controls qualify category/skill maps, both capability pair flags,
tag sets and integer resistance accumulation.84 property-body controls cover
their additional category/coefficient/resistance inputs. The four ordinary
category damage rates retain two rounded callback-weight multiplications.

The worn selector uses original wrapper+4 equipment slot codes. It must not
receive bag group9 in that field. All40170 combinations of195 current careers
and206 native required-class entries agree with the original class-entry
phase. The inherited74 original slot-side controls are retained. A private
frozen source additionally agrees with the whole cold worn collector in six
selector/resource controls; that evidence does not establish a live owner
context or complete set activation.
The immutable KIM-derived source contains all11422 set records and the shared
item property/option pools, without shipping a client binary. Every set lookup
and171722 threshold/qualifier boundary combinations agree with the original
6DB6A0/70F980 functions. These source-selection results remain distinct from
the caller's actual worn/color/activation qualification.

Portable tests include292 original passive/composition vectors, eight dense
original power vectors,251 condition vectors, 136 independent option scalar records,120 scalar merges,135 data merges,
120 combined wrapper cases,243 cooldown maps,84 power-map merges,
full wire contracts and a real
SQLite external-commit race. The independent native source investigations also
cover315 legal class/stage encodings and30722 original rank queries,15-family
SQL fixtures, and the original106 reader followed by guarded Unit/Actor
setters in both modes. These are controlled source/consumer proofs and do not
claim natural gameplay or a complete live dispatcher test.

The same-SQL capture now reads active pet identity, progression, accessories and
committed mount runtime without invoking mount settlement or login/schema
writers. Six real source controls cover nonempty state, concurrent commits,
ownership and expiry guards. Selected ERP allocations additionally pass a
60-query product106/original reader/point-map replacement chain; old points
are cleared before the selected page is applied.

The added immutable auxiliary sources cover all331 original pet templates,
932 titles,15 Master Artifacts and300 Collection definitions. Original loader
and collector controls include9480 pet branches,2796 title lookups and180
Artifact stage/potential branches. Pet gear contributes socket option IDs,
not equipment template IDs. Artifact's fourth potential is masked at stages3/4.
The Game+5F0 manager is independently identified as CX2ArtifactManager by RTTI
and ArtifactTemplet.lua loading; adjacent offsets are not riding-mount inputs.
All600 canonical CollectionData active/inactive cases pass the product encoder,
whole DB1080 reader and complete8A365F..8A3955 collector block, using the
unchanged GetTickCount import bound to its identical actual Windows export.

One real nonempty SQL fixture combines title ownership/deadline, pet and gear,
Master Artifact potentials and account Collection state in both modes. Its
arithmetic runs after releasing the read transaction and never reopens player
SQL. Deadline expiry invalidates the stale source; a fresh read removes only
the expired title's inputs. The four-group auxiliary assembler preserves the
original source order and remains separate from worn/set and active-buff
producers. It is not a claim that the whole collector or live path is enabled.

World-effect capture reuses the installed ordinary, supplement and economic
readers, including retained consumers and their exact source receipts. Actual
ONLINE and LOCAL six-group fixtures agree at one SQL generation and preserve
expiry boundaries without capture writes. Clock-only encoder metadata does not
enter the modifier digest. The same sampled validity time is passed to title,
pet and world-effect readers. An absent world schema avoids importing the
resource-heavy economic writer on cold character capture.
The base309 BuffManager definitions and927 explicit-active-vector controls are
retained as a source checkpoint. The additional INT75 definitions bring the
available registry to383 unique IDs. All384 original registrations retain the
existing1540 row;1153 original getter controls include a mixed ordered vector.
These checks cover the whole constructor, ID/socket property registration and
2DECA30 option getter. The notification dispatch independently identifies
3A2 ->2DEA410. Persisted elixir rows are not silently treated as the manager's
active vector; upstream global/unit buff qualification is a separate binding.

The immutable option-color index preserves all70522 records and288 distinct
type/Elianode/Artifact/Tenebrous/circuit color/shape profiles. Every profile
matches the original option property body. These color domains are separate:
the Elianode four-bin collector reads430, Artifact434 and Tenebrous470.
The fresh item constructor projection additionally matches71 original
DB4F80/7EBC80 controls across all33 groups, duplicate and zero values, the
18..21 first-nonempty priority and the803..806 derived socket selection.
It explicitly requires the canonical writer's empty legacy mutation map.

Canonical saved item bindings now supply scalar defaults from that exact
writer seed, immutable template pools, source-only option vectors and the
separate colors. A private22-item source agrees with12 whole native worn/set
compositions and six canonical-binding controls. Three of the latter decode
the installed main equipment DTO with fishing map keys39..42 through whole
DB0AC0. Group24 is Master Artifact equipment, gated by Artifact evolution;
ordinary costumes remain in group9. The tested cold owner/preset and empty
secondary/registration controls do not claim a complete live owner lifecycle.

The three post-power Forces900407/900410/900411 now have200 whole89C9D0
controls, including the original rank/definition/numerical getters and floorf.
All five current source ranks and eight eligibility combinations retain the
native threshold, cap and mixed float/double rounding. Their prepared rank
indexes are explicit phase controls, separate from the final live SQL binding.

The capability-row producer now preserves the original six append gates,
required factor/nonzero level and signed float32 accumulation. All833 distinct
current source profiles,33 boundary controls and46 full source-to-second-merge
chains agree with the original parser and both base/INT factor registries.
Packed regressions caught and fixed negative zero being lost by a default-value
shortcut; the original failed comparison and superseded receipts remain local.

The MP limit phase retains the exact order of66 skill sources and the original
300 base, equipment, rate, flat and extension contributions.414 whole895790
controls include original rank/definition/numerical readers in both phase modes.
Its separate1984460 equipment collector has534 whole native controls, including
slot-side, all selectors, both additional-item modes, exclusions and duplicates.
All181836 current templates contain finite MP fields;267 are nonzero with actual
values5/20/30. This MP selector differs from the general worn selector when
selector2 is used. Corrupt stored wrappers or added items without a template
are rejected before entering a native state that dereferences them.
A further96 whole895790 chains combine current nonzero equipment MP and ERP17
allocations/caps/overrides with both skill source modes and replacement vectors.
The prepared rank context remains distinct from the live character lifecycle.

The Unit3940 CP factor is now sourced from the original89C6D0 leaf and
ItemTierData's three binary64 coefficients.128 current set-threshold chains
qualify activation before individual effect-entry gates; eight leaf controls
retain sorted unique IDs, identity1 for absent definitions and double precision.
All three registrations and the original first-registration retention execute.

The class attack-kind map is generated by the original current relative-stat
registry. Its120 second/third-class entries select physical or magical by
float32 coefficients, with ties selecting2.75 current base/first classes retain
the original missing-entry path.585 original CP branch controls connect all195
classes to the actual registered map. Resource loading and Lua script-service
closures remain outside this table-registration phase proof.

The per-item option collector now has277 original wire/constructor/collector
controls covering all33 saved groups, source order, duplicates, zero values,
template versus character level and conditional group gates. It uses the exact
canonical trailing uint64 source for the circuit-state default; nonzero test
overrides remain explicit qualification controls.

The ordinary callback's51-scalar/13-data subset has154 whole88A180 controls,
including nonempty capability/probability/additional maps and conditional stat
rows. Six whole988D70 controls establish its separate pre-merge scaling and
unscaled11C leaf. PvP level-linked sources bypass callback weight; rank-linked
and PvE-rank-linked paths have distinct pre-scaling and PvP-rate behavior.
Five distinct current metadata profiles span all70522 definitions, with20
source-parser-to-whole-callback comparisons. Prepared rank/class contexts,
other scalar leaves and actor event-effect containers are separate contracts.

Independent composition of a private22-item source now reproduces25 callbacks
per pass from saved fields, template pools, set selection and the title source.
It matches the full original897100/8889F0 collectors in their qualified cold
context, using the complete858ED0..859402 Unit initialization prefix and real
inventory owner/caches. The original constructor initializes67 extra inventory
slots; these are traversed rather than replaced with an empty zeroed object.
This composition caught a missing source default: absent or Lua-nil probability
direction is1.32 new original parser/merge controls cover that default and
explicit0/1. First51 scalar leaves,13 data leaves and relevant CP maps now
agree, as do second-pass category/capability maps. Private player inputs and
native temporary pointers remain outside Git; full CP/lifecycle is separate.

Learned flat STAT collection now follows the complete8F8D50 channel ordering.
Nine original9BFE30 controls cover all five distinct profiles in the current
4483 skill definitions, including four nonempty STAT definitions, plus nil and
unequal-vector controls.63 whole-collector comparisons cover types, rank bounds,
selected-page gates, duplicate extra entries and missing templates. An invalid
selected page skips both later channels; a valid empty selected map still
permits the extra channel. Unsafe unchecked main-channel source rows are
rejected before calculation. Current ownership and preset lifecycle remain
separate source contracts, rather than invented empty inputs.

The integer maximum-MP option leaf now preserves its distinct conversion
rules: source m_iAddMpValue, float32 pre-scaling, cvttss2si truncation, and
float32 accumulation followed by a second signed32 conversion.132 whole
original callback controls include rank/PvE-rank, entry/class gates and
signed32/float32 boundaries. The current84 reforge stat registrations also
execute through the whole original setter;8118 complete getter comparisons
cover all369 admitted templates and levels0..21.

The private complete888CA0/896870/89B430 chain now executes with the unchanged
current CharacterStatTable KL bytecode and original math library, source
reforge registration, typed Unit prefix, consistent complete definition caches
and original skill DTO producers. An independent saved-source composition
matches both full kernel outputs, every kernel scalar/map, final seven and MP
in both modes for one frozen source. Earlier incomplete-context results remain
retained failures/controls. This still leaves live source/lifecycle acceptance
before runtime selection and publication.

The remaining integration must bind every actual modifier/context and CP
aggregate, qualify the current HP clamp/refresh lifecycle in the unmodified
client, then enable and publish in the ordinary queue from the actual latest
ONLINE/LOCAL parents.106 always includes CP; zero is not a preservation
sentinel. Equipment totals must never replace naked B6 inputs. No player data,
runtime image, raw capture, authentication material or production configuration
is included here.

The complete106 copy/CP/HP core now has28 original controls using the real
Actor/Vitality/stat constructors. Both selectors and the selector2 side fallback
retain the native branch. Rising maximum HP never heals; falling maximum clamps
current HP, including zero. CP uses float32 addition before rounding and zero
replaces an old positive value. These isolated Actor controls do not replace
world dispatch, modifier replacement, post-core MP refresh or live acceptance.

The17-byte DB29A0 record is now bound to canonical ERP profile fields21/25/29/31,
preserving signed32/signed32/unsigned64/unsigned8 values without interpretation.
Original D3AD14..D3AD3D stores the same four fields in Unit28BD/28C1/28C5/28CD;
four boundary profiles pass the current106 reader and native store phase.
Disabled profiles retain C832F0's17 zero bytes. An owned real-store two-page
snapshot also preserves a nonzero opaque record across a concurrent page commit,
without reader writes or player database access.

The reusable option collector now combines the source-ordered ordinary and
extended passes, including the integer MP leaf. Sixteen complete original
88A180/889610 controls cover duplicate/missing IDs, differing source levels,
positive/negative weights, rank/PvE-rank/linked-level and ERP entry gates.
The entries remain separate around the ERP phase, so each extended callback
adds to the actual existing ERP map in native float32 order. Nonempty initial
maps are included in the whole-callback controls.
Both modes of the private source also match the complete original collectors
through this product entry point. This consolidates source aggregation without
changing a client or selecting the runtime route before lifecycle acceptance.

The reusable power aggregate preserves the ordinary -> ERP -> each extended
callback -> cooldown -> normalization -> conditional data -> MP -> kernel
order. Four public compositions execute the original stages with nonempty ERP
and a crossed condition threshold, matching every kernel argument and both
outputs. Both modes of the private saved-source composition also match the
complete original builder. These explicit contexts remain separate from live
source acquisition and runtime admission.

The former feature77 context is now resolved as resource division-template
membership. The original6AEFB0 loader and6ADD70 reader accept all135 current
IDs and reject10 neighbor/control IDs. The source resource matches the existing
pinned growth-avatar registry byte for byte; the worn source binder reuses that
registry instead of creating a second catalog or assuming a uniform flag.

Complete BAA6F0 notification consumption has additionally passed in a private
constructed original Actor/CX2Game context: wrong UID rejection, CP rounding,
positive HP preservation, and MP clamp without healing. Original scene modes
exclude/include two dungeon-only options totaling24 MP, yielding400/424. Earlier
failed context constructions remain in private evidence. Live unmodified-client
acceptance and dual deployment are still required.

The current PVPData registry now supplies all11 original rank coefficients.
Thirty original insertion/lookup/complete ordinary-callback controls cover
every registered rank and absent signed-byte keys. None/arrange have coefficient1;
an absent key has coefficient0. Callers still supply the qualified actor rank,
so a cold test's zero coefficient cannot silently become a runtime default.

Original profile0 rank updates now preserve the previous initialized rank
when that profile is absent;16 constructor/update controls include a retained
nonzero rank. The resistance consumer has its own24 entry controls and16
complete option callbacks. Its PvE-rank branch uses a separate registry and
must not borrow the ordinary callback's forced-zero coefficient.

Resistance source work also covers the complete four-skill phase in48 original
controls and all2401 four-slot element tuples through the original classifier
and armor switch. The45 switch cases preserve75/110/135 tier values and summed
identifier collisions. These are source arithmetic phases, with worn selection
and remaining resistance source integration still explicit.

The separate current PVEData normal and MP coefficient registries have now
passed24 original registration/lookup controls and34 complete resistance
callbacks, including all ten grades and signed count overflow. The MP reader's
unregistered-key behavior is deliberately outside the qualified input domain.
Five original character-to-Unit copy controls also establish the four PvE
context fields and their signed widths. The installed packed25-byte source
field remains canonical zero; this is bound to the actual writer and fixture,
rather than inferred from an empty emulator registry.

The distinct main and secondary resistance item source paths now pass136
original phase controls through the canonical item reader/constructor. The
main path does not consume the secondary1C8/200 groups; source order and
duplicates remain intact. D0 capacity and weighted circuit activation remain
explicit, separately supplied inputs.

The optional resistance service source is now traced to the original311
unsigned16 threshold producer: threshold2 allocates six100 values, and later
lower or zero inputs retain that allocation. Seven original producer controls
and six ordered finalization controls cover this lifecycle, float32 additions
and the500 upper-only cap. Fresh original construction has a null source;
packet meaning and actual runtime source admission are separate.

The current character source projector additionally passes the complete
installed writer and D9B170 reader with five signed PvE boundary records.
It preserves the previous rank for the writer's canonical empty profile map,
decodes the exact25-byte PvE record, and applies the original unconditional
Unit2738 clear at a full-character copy boundary. Later independent updates
must retain their own lifecycle rather than silently invoking this reset.

Circuit attribute inputs now preserve the complete6C9010 propagation order:
each positive multiplier influences its shape's neighboring slots, overlapping
influences combine in float32, and output follows active traversal order.
Thirty-six original controls include four roots, fractional/nil/negative rates,
and eight actual current-ID branched grids with all four T shapes. The latter
also pass the installed topology and product entry. The private emulator uses
the original CRT's SSE fallback because its captured AVX2 dispatch mode selects
an instruction the emulator cannot execute; executable instructions and
gameplay returns are unchanged. These weighted sources still need integration
at each original collector call site before runtime selection.

The four-armor activation producer now passes93 original controls. The4A and
4E gates require all four non-avatar positions and a nonempty corresponding
option vector; a vector containing ID0 remains nonempty. Circuit activation50
requires the four properties without adding that vector gate. Selection order
and the native first eligible item at each position are retained.

The per-item source factory keeps normal and weighted circuit options separate.
Eight complete original897290/889A20 wrapper compositions cover both modes,
missing/all-four activation, and a nonempty initial extended map. Actual current
circuit grids reproduce every callback ID, order and weight, ordinary fields,
integer MP and extended maps. Public tests replay the independent circuit
goldens; the private original compositions also run the current catalog and
topology. Live source lifecycle and runtime admission remain separate.

The legacy resistance D0 gate now preserves1991230's first qualifying template
option, extraction short circuit, and separate application quantity and signed
piece threshold. Seventy-three original producer controls include ordered pairs
and missing IDs. All70522 current source definitions classify into two nonempty
gate profiles (24744 records); the current condition thresholds are zero. The
native samples validate those two profiles without claiming24744 native parses.
Sixty-four additional complete resistance item phases execute original inventory
counting, positive/rejected D0 cases and weighted circuits. Both modes retain
their complementary option gates, including dungeon-only circuit exclusions.

The Unit stat-query source now merges ordinary learned ranks with the canonical
visible three passive Force slots. Fifty-six original DTO/8FA130/8F7600 controls
cover all currently admitted passive book ranks, owned-only and equipped states,
Master visibility, third-slot Artifact locks, and clearing previous equipment
on the same native manager. Original9CD180/9CE5E0 supplies Force membership;
queried ranks are not prefilled. Actor action-skill bonuses use a different
consumer and are not added to these Unit stat-query ranks.
