# Combined copper add-on: Minecraft 1.17–26.3

The 32x and 64x standalone editions extend the reviewed V3 copper artwork back to copper's first Java release, 1.17. They use pinned original Faithful artwork and the existing precise wax masks. No older version is simulated by resizing textures or changing the modern models.

The extension affects only the standalone copper item add-ons. The full TQNL Faithful Vanilla Tweaks compilation keeps its existing format 34–97.1 interval, and the accepted 16x archive remains unchanged.

## Resource transitions

| Clients | Copper items and resource layout |
| --- | --- |
| 1.17–1.20.2 | The sixteen original waxed full-block, cut-copper, stair and slab items; legacy `models/item` layout. |
| 1.20.3–1.21.3 | Twenty further waxed copper items add chiseled copper, grates, bulbs, doors and trapdoors. The 1.20.3–1.20.6 clients contain these as experimental 1.21 features; the pack does not enable experiments or create items. |
| 1.21.4–1.21.8 | The same 36 items, with the new native `items` definitions selecting the corrected item models. |
| 1.21.9–26.3 | The complete 60-item V3 add-on, including the waxed rod, bars, chain, lantern, chest and statue families. Every effective resource path and byte matches the reviewed modern V3 edition for that exact client. |

Overlays start with the first added copper resources at format 22 / 1.20.3. They also select the 1.21.4 item-definition schema, 1.21.9 item additions, later 64x Faithful texture families, and the accepted 26.1+ statue transformation. The model UV coordinates and waxed artwork are preserved.

The audited older 32x source pixels are identical to the modern source. Historical 64x copper artwork differs, so six original PNGs are retained and the same wax masks are applied to them. The early family serves 1.17–1.20.2; the intermediate cut-copper artwork serves 1.20.3–1.21.5; 1.21.6 and later use the reviewed modern artwork. Every later modern exact-family overlay is retained.

No exact official 64x export was found on the audited distribution channels for 1.17/1.18, so those clients receive a native-UV backport of original Faithful 1.19 copper art. The missing exact 1.20, 1.20.5 and 1.21.6 listings use the corresponding neighboring source family. Minecraft 1.20.3 and 1.20.4 share resource format 22, so one combined ZIP cannot select their differing historical textures separately; both use the newer original 1.20.4 family. Experimental copper items absent from an older Faithful export use the already pinned later original Faithful artwork. These source choices and archive license links are recorded in `source/legacy-faithful-sources.json` and in the ZIP's provenance.

The default root resources use format 7 and the legacy item-model layout, because overlays were introduced only in 1.20.2. A client before 1.20.2 ignores the declared version range and recognizes only one `pack_format`. Therefore **1.18–1.20.1 display an unavoidable compatibility warning** for the shared ZIP. Formats 7–97 are declared through `supported_formats`, and modern readers also receive `min_format` 7 and `max_format` 97.1. All overlay entries declare both legacy `formats` and modern format bounds.

There are no blockstates, block models, block textures or entity textures in the add-on. Placed copper blocks and live copper golems retain their native or lower-priority pack resources.

## Build and verification

```powershell
python visual-copper/tools/build.py
python visual-copper/tools/build_legacy_copper.py
```

The first command reproduces the reviewed modern V3 packs. The second reads the pinned official full-release manifest at `source/minecraft/legacy-client-manifest.json`, follows the reviewed item-model texture dependencies for legacy clients, and builds the combined 1.17–26.3 ZIPs. Its expected resource maps cover all 34 full releases; no snapshots or future releases are included.

`legacy-copper-build-verification.json` records every exact-client format, overlay selection and complete resource-tree digest. The independent native validation record states which native readers, model graphs and rendering checks were actually run. Metadata parsing and model-reference checks do not establish a visual pass on every client. The existing targeted 26.3 visual wax review is retained; a historical full per-release visual matrix is not claimed.

## Primary sources

- [Mojang's official version manifest](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json), with per-client metadata and client JAR digests pinned in the local manifest.
- [Minecraft Java 1.20.2](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-20-2): resource overlays and supported format ranges, including older clients' single-format behavior.
- [Snapshot 25w31a resource-pack changes](https://www.minecraft.net/en-us/article/minecraft-snapshot-25w31a): legacy and modern format declarations for ranges that include old formats.
- [Faithful downloads](https://faithfulpack.net/downloads), with exact original texture sources and contributors retained in each ZIP's provenance and license files.
