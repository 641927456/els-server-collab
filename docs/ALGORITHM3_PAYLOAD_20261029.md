# Algorithm 2/3 payload decoding — 2026-10-29

Status: **blocked, root cause identified, known-plaintext corpus prepared.** No
Algorithm 2/3 payload in this client can be decoded from disk alone. This note
records what was ruled out so the next attempt does not repeat it.

## The correction that changes the scope

Earlier notes treated only `Algorithm=3` as encrypted. A full census of all 407
archives (`419,970` payloads) shows `Algorithm=2` is encrypted too:

| Algorithm | Payloads | Uncompressed bytes | State |
|---|---|---|---|
| 0 | 87,796 | 4.84 GB | readable (plain zlib) |
| 2 | 314,540 | 39.80 GB | blocked |
| 3 | 17,634 | 0.58 GB | blocked |

`Algorithm=0` inflates with plain `zlib.decompress` and starts `78 9c`. Both 2 and
3 do not inflate at any window bits, have `CompressedSize % 8 == 0`, and sit at
entropy ≈ 7.90. Census by extension: **every one of the 15,299 `.lua` files is
`Algorithm=3`**, so no Lua table is readable today. `.ogg` (71,299) and
`.xet`/`.tet` are `Algorithm=0`; `.dds`/`.tga`/`.x` are mostly `Algorithm=2`.

## Why it cannot be solved from disk

`x2_dx11.exe` and `x2.exe` are both Themida-packed. The code section declares
`VSize=0x3ea66d5` against `RawSize=0x1641000`, i.e. 65.6 MB of virtual code backed
by 23.3 MB on disk. Measured printable-ASCII density in the code region is 0.334,
against 0.371 expected for uniform random bytes; the longest readable run is
`(tvTjrJNQI1hy3`. So the on-disk code bytes are ciphertext, and no static
disassembly is possible.

The witnessed directory seed table sits at RVA `0x3e11940`
(`tools/client_compatibility_profiles.json`), which falls past the raw data of
that section — it only exists after unpacking. No crypto constants survive in the
file either: Blowfish `P[0]`, AES `Te0[0]`, SHA-1/SHA-256 IVs are all absent; only
`0x9E3779B9` (TEA delta) and the CRC32 polynomial appear.

The earlier work decoded these payloads with "original 374E40 in private Unicorn
memory" (`analysis/integration-20261015/*/native-offline-proof.json`). That
harness and the unpacked image it ran against are **not in this repository**, and
`unicorn` is not installed. `analysis/client-6c6b5180/native-prefixes.bin` is not
the missing image: it is 110 MB of zeros with 0.000 printable density.

## What was tried against an exact oracle

Oracle: a candidate decode is only accepted when the result inflates to exactly
the byte string of the known decoded Lua, so a false positive is impossible.

| Family | Search space | Result |
|---|---|---|
| Blowfish ECB/CBC | 201 seeds × 5 key derivations × skip 0..64 | no hit |
| Blowfish CFB/OFB, AES-128/192/256, DES | seed/name/MappedID derived keys | no hit |
| TEA / XTEA / XXTEA | seed quadruples + `sha1(str(seed))` | no hit |
| RC4 | seed/name/MappedID derived keys | no hit |
| PRNG keystream XOR | MSVC `rand`, ANSI LCG, xorshift32, MT19937; seeds 0..300 × skip 0..64 | no hit |
| zlib offset scan | skip 0..32 on raw payload | no hit |

The `key` values recorded in the proofs (66, 76, 108, 124, 133, 146, 210, 213, 275)
exceed the 201-entry seed table, so they index something the repository does not
contain.

## What this note does deliver

Eleven Algorithm=3 payloads now have a **verified known-plaintext counterpart** —
decoded Lua source in `analysis/`, with the archive's declared `Size` matching the
decoded length exactly. That is the asset a real solution needs:

| Resource | Archive | Declared Size | proof `key` |
|---|---|---|---|
| ManufactureItem.lua | data036 | 3,728,375 | 133 |
| RandomItem.lua | data036 | 3,648,445 | 124 |
| NPCTemplet.lua | data037 | 1,279,710 | — |
| Enum.lua | data036 | 1,214,274 | — |
| PackageItemData_INT.lua | data036 | 1,085,260 | 108 |
| PackageItemData.lua | data036 | 728,734 | 76 |
| ShopItem.lua | data036 | 46,492 | 213 |
| ProfessionTemplet.lua | data036 | 8,959 | 146 |
| AllowPeriodItemManufacture_Exchange.lua | data036 | 1,108 | 275 |
| CanUseInventoryItem.lua | data036 | 434 | 210 |
| LimitManufactureData.lua | data036 | 364 | 66 |

Note that the client's compressor is not stock zlib: recompressing these files
gives lengths that differ from `CompressedSize` by 35–1,486 bytes that are not
block padding. So a known-plaintext attack has to work on the decompressed text
via the oracle, not on a reproduced deflate stream.

## The two viable routes

1. **Unpack and read the routine.** Start the client, take a read-only dump of the
   `x2_dx11.exe` module image, then disassemble `0x374E40` with capstone
   (now installed) and reimplement it in Python. This produces a real offline
   decryptor for all 332,174 blocked payloads.
2. **Emulate the routine.** Same dump, then run `0x374E40` under Unicorn with the
   recorded `(key, skip)` pair per resource, which is how the October proofs were
   made.

Both need the unpacked image. Neither needs the game server, the database, or any
player state. Nothing in this note modifies the client.

## Reproduction

```
python -B "…/census.py"          # algorithm census over 407 archives
python -B "…/battery.py"         # cipher battery against the oracle
python -B "…/prng_xor.py"        # PRNG keystream hypothesis
```

Output bundle: `Algorithm3诊断-20261029/` in the workspace (per-archive census,
algorithm × extension table, readability summary, known-plaintext corpus).
