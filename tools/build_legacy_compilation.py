"""Build the original 32x repository compilation for pre-1.21.9 clients."""
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'visual-copper/tools'))
import build as b

BASE = '77028434d8b2d9960dede0733c2abf19be9d5001'
NAME = 'TQNL-Faithful-Vanilla-Tweaks-32x-mc-1.21-to-1.21.8.zip'


def main():
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'archive', '--format=zip', BASE])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        original = {name: archive.read(name) for name in archive.namelist() if not name.endswith('/')}
    old_meta = json.loads(original['pack.mcmeta'])
    actual_overlays = sorted({name.split('/')[0] for name in original if name.startswith('overlay_')})
    files = dict(original)
    entries = []
    for directory in actual_overlays:
        source = next(entry for entry in old_meta['overlays']['entries'] if entry['directory'] == directory)
        lower = source['min_format']
        upper = min(source['max_format'], 64)
        if lower <= upper:
            entries.append({'directory': directory, 'formats': {'min_inclusive': lower, 'max_inclusive': upper},
                            'min_format': lower, 'max_format': upper})
    metadata = {'pack': {'pack_format': 34, 'supported_formats': {'min_inclusive': 34, 'max_inclusive': 64},
                        'min_format': 34, 'max_format': 64,
                        'description': "TQNL's Faithful 32x / Vanilla Tweaks compilation\nMinecraft 1.21 - 1.21.8"},
                'overlays': {'entries': entries}}
    files['pack.mcmeta'] = b.json_bytes(metadata)
    files['README.txt'] = (
        'TQNL Faithful Vanilla Tweaks - Legacy 32x compilation\nMinecraft 1.21 - 1.21.8\n\n'
        'This is the original complete repository compilation from commit '+BASE+'.\n'
        'It retains the original block, entity, item, utility, painting/bucket and visual indicator tweaks,\n'
        'including VisualWaxedCopperItems. See report.txt for the original contents and contributors.\n'
        'The repository remains a full compilation; newer copper-only V3 editions are separate downloads.\n\n'
        'Use above the matching Faithful 32x base pack. Continuity is needed for included CTM effects;\n'
        'CIT Resewn or a compatible CIT implementation is needed for included CIT effects.\n'
        'Features apply only where the corresponding items/entities exist in that client.\n'
        'Dormant files for later copper items are preserved from the historical repository.\n\n'
        'The historical metadata began at resource format34 and used version overlays,\n'
        'so it was intended for a combined interval. Its oversized7500 maximum is replaced\n'
        'here by the pre-1.21.9 formats34-64. All original resource bytes are unchanged.\n'
        'Metadata and resource selection were checked; no new all-feature in-game test was run.\n\n'
        'Credits:\nVanilla Tweaks: https://vanillatweaks.net/\nFaithful: https://faithfulpack.net/\n'
        'Faithful License: https://faithfulpack.net/license/\n').encode()
    files['credits.txt'] = b'Credits:\nVanilla Tweaks: https://vanillatweaks.net/\nFaithful 32x and add-ons: https://faithfulpack.net/\nTQNL compilation; original individual credits retained in report.txt.\n'
    files['Faithful-License-v3.txt'] = (b.ROOT / 'source/licenses/Faithful-64x-License-v3.txt').read_bytes()
    files['Faithful-License-v4.txt'] = (b.ROOT / 'source/licenses/Faithful-32x-License-v4.txt').read_bytes()
    checks = []
    for versions, fmt in ((['1.21', '1.21.1'], 34), (['1.21.2', '1.21.3'], 42), (['1.21.4'], 46),
                          (['1.21.5'], 55), (['1.21.6'], 63), (['1.21.7', '1.21.8'], 64)):
        before, _ = b.effective(original, [fmt, 0])
        after, selected = b.effective(files, [fmt, 0])
        if before != after:
            raise ValueError('Legacy resource selection differs from original repository')
        checks.append({'versions': versions, 'resource_format': fmt, 'overlays': selected,
                       'asset_count': len(after), 'effective_assets_sha256': b.tree_hash(after),
                       'original_resources_identical': True})
    if any(files[name] != data for name, data in original.items() if name != 'pack.mcmeta'):
        raise ValueError('Original compilation file changed')
    path = ROOT / 'legacy-dist' / NAME
    sha = b.archive(files, path)
    report = {'artifact': str(path.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha,
              'bytes': path.stat().st_size, 'original_commit': BASE,
              'original_files': len(original), 'original_files_preserved_except_metadata': len(original) - 1,
              'actual_original_overlays': actual_overlays, 'pack_metadata': metadata, 'checks': checks,
              'intent': 'Historical base format34 and three populated overlays form a combined compilation; cap this release before1.21.9.',
              'minecraft_started': False,
              'sources': ['https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21',
                          'https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-4',
                          'https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-5',
                          'https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-6',
                          'https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-7',
                          'https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-8']}
    (b.ROOT / 'docs/legacy-build-verification.json').write_bytes(b.json_bytes(report))
    print(json.dumps({'artifact': report['artifact'], 'files': len(files), 'sha256': sha,
                      'supported_interval': '1.21 - 1.21.8', 'format_checks': len(checks)}, indent=2))


if __name__ == '__main__':
    main()
