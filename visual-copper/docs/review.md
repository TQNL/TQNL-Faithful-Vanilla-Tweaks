# Independent offline review of VisualWaxedCopperItems V3

Reviewed on 2026-10-14, against the final rebuilt 27 ZIPs and compilation integration based on repository commit `8514066836949be584ddb1fa68e88fcb2db352e3`.

**Result: no unresolved offline correctness findings in the reviewed build.** This is a source, asset, packaging, and overlay review. It does not establish in-game visual acceptance for the new 32x/64x editions. Minecraft was not started by this reviewer.

## Reviewed snapshot

| File | SHA-256 |
| --- | --- |
| `tools/build.py` | `b1803ceed4d69716a092005ae3f42c0f8016bb7e396259f2caa22195a63358b9` |
| `tools/wax_masks.py` | `c36d521c944a8103d364d1b30ff5d17a7c3df78811cb4b8a9cc0b53050e52c77` |
| `tools/mask_patterns.json` | `0069c2cfeacb9a6b8f8c3dbf19c08a71fc9afe2701b4ce4538870e19ffec589e` |
| `docs/build-verification.json` | `270250f32c712205bcd895d725e4131c598d43f61422def399b8d63814f2944c` |

The artifact hashes in the reviewed `build-verification.json` identify the exact final ZIP bytes. Read-only Python checks independently opened the artifacts, resolved overlays without using the builder's resolver, compared source archives, and compared official client assets. The reviewer changed only this report.

## Native statue definitions and formats

All eight official client JARs were SHA-1 checked against the copied Mojang download metadata. Each of the four waxed statue item definitions was compared structurally with its exact client definition: **32 comparisons passed**. The only differences are the four renderer texture substitutions in each definition. Pose selection, standing fallback, sitting/running/star cases, native special renderer, and native base template remain identical.

The native transformation from 26.1 onward is retained exactly: identity rotations, scale `[1,-1,-1]`, and translation `[0.5,1.5,0.5]`. Texture resolution does not alter these definitions. All **2,904 JSON asset instances** in the 24 exact edition packs match the accepted input JSON bytes, so model UVs and display transforms were not rescaled.

The resource formats were independently read from each official JAR's `version.json`:

| Exact clients | Resource format |
| --- | --- |
| 1.21.9, 1.21.10 | 69.0 |
| 1.21.11 | 75.0 |
| 26.1, 26.1.1, 26.1.2 | 84.0 |
| 26.2 | 88.0 |
| 26.3 | 97.1 |

All 16x effective asset digests match the eight immutable accepted-release records. The accepted 1.21 family has 193 assets, including 72 item textures; the accepted 26.x family has 194 assets, including those 72 active textures and one unused gold-only door-outline helper.

## Faithful source and texture checks

All ten retained official Faithful archive SHA-256 values and sizes match the provenance records. Each family's 52 retained native texture files was compared directly with the corresponding archive entry: **520 source files matched byte for byte**. All 1,162 per-client/resolution mapping hashes match the checked-in minimal files. The 64x editions use the actual official 64x source bytes rather than scaled 32x copper artwork.

The archived applicable license file was compared with the retained copy for every family, and the final distribution copies were compared again. All match byte for byte. Every Faithful distribution includes visible attribution and the original applicable license; the combined 64x pack retains both license versions. The current [Faithful license page](https://faithfulpack.net/license/) and [official 32x September 2026 release](https://github.com/Faithful-Resource-Pack/Faithful-32x-Java/releases/tag/september-2026-release) were consulted as primary source checks. This report does not make a broader legal assessment.

Independent pixel comparison of the built editions verified the 1,152 active derived textures against the prepared native Faithful sheets and gold masks. Pixels outside the masks match the prepared sheets; gold application preserves their alpha. The ten unused door-outline helpers retain only the six recorded gold palette colors and transparency. All texture dimensions are the exact expected multiples of the accepted native UV sheets.

The final lightning-rod correction received a separate pixel and UV coverage check across **64 derived textures**: four oxidation stages, eight exact clients, and two Faithful resolutions. Native shaft `[0,4,2,16]`, duplicated shaft `[2,4,4,16]`, and bottom-cap `[4,0,6,2]` regions are fully opaque. The output matches the prepared source plus the wax mask. The required shaft/cap preparation is explicitly recorded in distribution provenance.

The saved texture contact sheet was visually inspected for obvious raster corruption. Atlas previews do not prove pose, lighting, filtering, handedness, shelf, or third-person behavior in a running game.

## Packaging, overlays, and existing compilation

All **27 ZIPs** pass independent ZIP integrity checks, unique-entry checks, byte counts, final SHA-256 checks, and readback against their recorded effective resource digests. Each exact edition includes the complete accepted resource path set and all 72/73 textures.

Independent ordered overlay resolution compared every combined edition against its corresponding exact edition for all eight clients: **24 complete resource comparisons passed**. The 16x and 32x combined packs need the 84.0 transition overlay. The 64x combined pack additionally needs 75.0 and 88.0 transitions. All include the correct 97.1 resources; an additional overlay is unnecessary when those copper resources do not change at that boundary.

The actual root compilation was independently resolved at all eight formats. Every new copper resource matches the corresponding standalone 32x pack: 193 assets for 1.21.x and 194 assets for 26.x. The original `pack` metadata object and all 26 existing overlay declarations are retained. Among the original 938 tracked files, only `pack.mcmeta` is modified; the other 937 files are unchanged. New copper files are confined to the declared `overlay_69` and `overlay_copper_26` directories. No new block, live entity, or atlas overrides are present in these standalone copper resource trees.

The README correctly distinguishes the verified standalone copper packages from the broader pre-existing compilation. Its other tweaks and compatibility declarations are not presented as newly tested.

## Findings resolved during review

1. Historical 64x source textures can differ from the latest contribution metadata. Compact distribution attribution now explicitly limits contribution IDs/dates to the 26.3 reference and does not claim pixel-to-contribution identity for older archives. Exact archive and asset hashes remain the source identity evidence.
2. Lightning-rod UV preparation initially lacked a complete shaft/cap copy. The final builder copies the entire required regions, and the independent opaque-UV and pixel checks pass. Derivation records now disclose the preparation and define pixel equality against the prepared source sheet.

The reviewer read the final saved native proof: all **48 exact-client metadata/resource-loader checks** are compatible, and both root-compilation boundary checks in `compilation-native-check.json` are compatible with copper resources matching the standalone packs. These checks started no Minecraft window or world. The reviewer did not rerun this separate gate; its results come from `tools/native_check.py` and the saved logs. Appending the native proof changed the verification-file hash above; the 27 reviewed artifact ZIP hashes are unchanged. No new in-game visual score is claimed.
