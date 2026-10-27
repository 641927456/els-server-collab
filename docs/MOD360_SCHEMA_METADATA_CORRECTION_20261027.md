# Mod360 lazy-schema metadata correction

Independent review of PR576 source0535d6b9 found two new optional business-lazy
table definitions relative to the accepted selection-town parent:

- `selected_2026_change_force_inventory`: exact rank1 ownership, primary key
  `(owner,skill,rank)`, unique `(owner,source_template)`, owner FK to characters.
- `selected_2026_change_force_slots`: eight slots0..7, primary key `(owner,slot)`,
  unique `(owner,skill)`, composite FK to the corresponding owned rank1 row.

The earlier source/delivery metadata saying new_tables0 and
new_schema_definitions0 was inaccurate. Correct source-archive metadata is
new_tables2, new_schema_definitions2 and new_schema=true. Here new_schema means
new business-lazy schema definitions; it does not mean an eager installation
migration. Installation DDL remains0. The16 business leaves, original recipes,
consumer code, runtime item/source rules and delivery outcome are unchanged.

The verifier now executes the archived initialize_change function and the
exact slot-table DDL against a fresh private SQLite connection/savepoint. It
checks the two actual tables, primary/composite foreign keys and six negative
constraint cases. Rolling back the savepoint must restore the complete initial
sqlite_master, including removal of the generated indexes. The selected parent
source contains neither definition; no production/player database is opened.

Historical frozen delivery manifests, schema observations, failure records and
completion receipts remain immutable. This note corrects their descriptive
schema counts without rewriting those files or claiming that an installation
migration ran. The later quest-lock batch adds12 existing leaves and no new
schema itself; its zero-new-table delta remains correct.

The original360 books are stackable to999, with seal-history cap1. The inherited extraction allocator merges a returned book into an eligible matching-identity unsealed stack with the same seal history; otherwise it allocates a new UID subject to the existing capacity rules. The prior new-UID QA outcome covers only the no-matching-old-stack case. No stacking, capacity or consumer behavior is changed by this metadata correction.
