# V3 design and verification

## Source selection

Official published stable exports are pinned by URL, release date and SHA-256. For each Minecraft family, the newest compatible Faithful export was selected: 32x September 2026 and 64x R11 (1.21.9/10), R12 (1.21.11), R13 (26.1/.1/.2), R14 (26.2), R15 (26.3). All 52 needed textures exist at native resolution. No 32x copper artwork is upscaled to create 64x copper artwork.

The current 32x copper art is identical across those exports. Earlier 64x textures differ, so the combined 64x pack selects the matching family with cumulative overlays. These are item-only add-ons, not redistributions of the full Faithful packs.

## Wax boundaries

The previous TQNL 32x mask topology and six-color gold palette are recorded as text in `tools/mask_patterns.json`. Ordinary UV sheets retain their face boundaries. The 32x band is one texture pixel; 64x uses two pixels, preserving the same fraction of a block face and avoiding a half-width marker that can disappear after downsampling. Both widths were reviewed in native 26.3 inventory captures.

Generated bars, chains and lantern sprites add an exterior gold stroke around the actual current Faithful silhouette, following Vanilla Tweaks' method. All original copper pixels remain unchanged, and a flood fill protects enclosed holes. Door sprites mark their existing outer frame inward. Tiny latch faces use a narrower full frame, retaining copper where the UV island permits it.

Native statue face coordinates were extracted from the official client model, rather than inferred from the unused legacy static mesh. The texture editions retain the nose, antenna caps, inner arm and leg-top accents, and complete wax boundaries on 18 additional exposed body, arm, leg and sole faces. Chest latch thin faces also receive complete frames. Copper interiors remain visible. Shared UV regions retain the same art in every pose.

The owner-approved antenna revision also replaces the four stem-side stripes with complete rectangular borders, matching the top cube and existing cap rings. These six pole faces retain a copper centre at both 32x and 64x. The final rendering resources are byte-identical to the locally reviewed packs.

Stair and slab wax sheets preserve their distinct native cut-copper UV coordinates. Trapdoor side UVs sample only the first three native texture rows. Lightning rods retain VT's custom shaft strip duplication before applying complete rings to both shaft strips and the bottom cap, so their four sides remain consistent when rotated. The unused 48x32 gold-only door-outline helper is retained and scaled with nearest sampling; it contains no Faithful copper artwork and no active model references it.

All model UV coordinates remain unchanged. Entity atlases are 128x128 at 32x and 256x256 at 64x. Blockbench's `texture_size` hint is not a reason to multiply model UVs.

## Statue rendering and formats

All edition item/model JSON is byte-identical to the accepted full VT repairs. Statues select standing/sitting/running/star through `copper_golem_pose` and the native `minecraft:copper_golem_statue` special renderer. From 26.1, the native transformation is retained: scale `[1,-1,-1]`, translation `[0.5,1.5,0.5]` and identity rotations. Texture resolution does not change pose or handedness behavior.

| Clients | Resource format |
| --- | --- |
| 1.21.9, 1.21.10 | 69.0 |
| 1.21.11 | 75.0 |
| 26.1, 26.1.1, 26.1.2 | 84.0 |
| 26.2 | 88.0 |
| 26.3 | 97.1 |

Each exact pack declares the corresponding format pair. Combined packs declare 69.0–97.1; their overlays are cumulative and resource-by-resource compared against every exact pack. These modern standalone packs do not include obsolete `pack_format` or `supported_formats` declarations.

## Evidence and limits

`build-verification.json` records every ZIP hash, size and effective resource tree; per-texture checks prove source hashes, dimensions and unchanged pixels outside the wax mask after required UV mapping. Alpha is preserved for model sheets; generated chain, lantern and bar sprites deliberately add the exterior gold stroke described above. Every ZIP is reopened and compared with the intended files. `wax-validation-summary.json` records 1,162 independently checked texture instances and 6,912 exposed UV border checks.

`native_reader_checks` records all three combined packs through each of the eight exact official client metadata parsers and native resource managers (24 checks). Exact-version candidates are assembled internally for overlay equality and are not separately distributed. No game window, profile, world, F-key swap or freecam session is started by this verification. Native resource loading is not an in-game visual acceptance score.

The 16x archive remains byte-identical to the accepted release. The 32x/64x editions received a targeted native Minecraft 26.3 review: 72 inventory renders per edition across all four oxidation stages and statue poses, plus 12 rotated lightning rods per edition, including four azimuths and two pitched end views. `wax-review-verification.json` records capture hashes and scope. This is a wax review; the historical full per-release lighting, mipmap, filtering, hand, shelf and third-person matrix was not repeated.

The resolution-labelled `source/icons` images are cropped from real in-game screenshots. The builder uses these for the 32x/64x combined packs and explicit ZIP compression level 9, reproducing the reviewed release archives exactly. The original 16x icon and archive packaging are retained.

Primary references: [Faithful downloads](https://faithfulpack.net/downloads), [32x September 2026](https://faithfulpack.net/faithful32x/2026-September), [64x R15](https://faithfulpack.net/faithful64x/R15), [Minecraft 1.21.9](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-9), [Minecraft 26.1](https://www.minecraft.net/en-us/article/minecraft-java-edition-26-1), and [Minecraft 26.3](https://www.minecraft.net/en-us/article/minecraft-java-edition-26-3).
