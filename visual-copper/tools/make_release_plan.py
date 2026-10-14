"""Prepare the V3 release plan for the exact pushed source commit."""
import json
import subprocess
from pathlib import Path

import build as b


def make_plan():
    repository = b.ROOT.parent
    commit = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()
    record = b.read_json(b.ROOT / 'docs/build-verification.json')
    if len(record.get('native_reader_checks', {}).get('checks', [])) != sum(len(a['checks']) for a in record['artifacts']):
        raise ValueError('Final native pack checks are not complete')
    output = b.ROOT / '.work/release-plan.json'
    output.parent.mkdir(exist_ok=True)
    releases = []
    for target in ('1.21.9-to-26.3',):
        label = '1.21.9–26.3 (Combined)' if target == '1.21.9-to-26.3' else target
        artifacts = [a for a in record['artifacts'] if a['target'] == target]
        source_text = ('Version-aware overlays select the matching official Faithful family and native statue transformation.'
                       if target == '1.21.9-to-26.3' else
                       f"32x source: September 2026. 64x source: " +
                       next(s['release_name'] for s in b.read_json(b.ROOT / 'source/provenance.json')['sources']
                            if s['resolution'] == 64 and s['family'] == b.FAMILIES[target]) + '.')
        base_url = 'https://github.com/TQNL/TQNL-Faithful-Vanilla-Tweaks'
        body = (f'Adds a border around Waxed Copper in the inventory.\n\n'
                f'**Minecraft {label} — VisualWaxedCopperItems V3**\n\n'
                '- **16x Statue Patch:** complete original-derived item tweak with the accepted native statue fix.\n'
                '- **Faithful 32x:** official 32x artwork with a one-pixel wax border.\n'
                '- **Faithful 64x:** official native 64x artwork with a two-pixel border, narrowed on tiny faces.\n\n'
                'Includes all four oxidation stages and pose-aware copper golem statues. Extra nose, antenna, inner-arm, leg-top '
                'and chest-latch accents are included in the new Faithful editions. The owner-approved update adds full wax borders '
                'to all antenna pole faces at 32x and 64x. Placed blocks and live golems are unchanged.\n\n'
                f'{source_text}\n\n'
                'Put one matching ZIP in `.minecraft/resourcepacks` and enable it above other packs. '
                'For consistent world textures, use the matching official Faithful pack underneath.\n\n'
                '**Checks:** ZIP integrity, source pixels/alpha, rendering JSON and exact-client metadata/overlay loading. '
                'The owner reviewed and approved the antenna-border update. No new automated Minecraft visual matrix was run; '
                '16x rendering assets inherit their prior acceptance.\n\n'
                f'[Offline texture preview]({base_url}/blob/{commit}/visual-copper/docs/previews/texture-contact-sheet.png) · '
                f'[Verification and design]({base_url}/blob/{commit}/visual-copper/docs/design-and-verification.md) · '
                f'[SHA-256 checksums]({base_url}/blob/{commit}/visual-copper/dist/SHA256SUMS.txt)\n\n'
                'Credits:\nVanilla Tweaks: https://vanillatweaks.net/\n\n'
                'Faithful 32x/64x: **[Faithful Resource Pack](https://faithfulpack.net/)**. '
                'Texture artists are credited per asset in the ZIP; native 64x copper art by HARYA_. '
                'Wax adaptation and statue fixes by TQNL. This is an independent add-on. '
                '[Faithful license](https://faithfulpack.net/license/) copies are included.\n')
        releases.append({'target': target, 'tag': 'VisualWaxedCopperItems-mc-' + target,
                         'name': 'VisualWaxedCopperItems V3 - Minecraft ' + target, 'body': body,
                         'assets': [{'name': a['filename'], 'path': '../dist/' + a['filename'],
                                     'sha256': a['sha256']} for a in artifacts]})
    plan = {'repository': 'TQNL/TQNL-Faithful-Vanilla-Tweaks', 'target_commitish': commit, 'releases': releases}
    output.write_bytes(b.json_bytes(plan))
    print(json.dumps({'plan': str(output), 'commit': commit, 'releases': len(releases), 'assets': 3}, indent=2))


if __name__ == '__main__':
    make_plan()
