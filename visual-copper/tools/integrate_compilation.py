"""Integrate only the new 32x copper resources into the existing compilation.

Original compilation assets and other overlay entries are left untouched.
"""
import json
import zipfile

import build as b


def integrate():
    repository = b.ROOT.parent
    checks = []
    for directory, target in (('overlay_69', '1.21.9'), ('overlay_copper_26', '26.3')):
        path = b.ROOT / 'dist' / 'VisualWaxedCopperItems-32x-mc-1.21.9-to-26.3.zip'
        with zipfile.ZipFile(path) as archive:
            all_files = {n: archive.read(n) for n in archive.namelist()}
        assets, _ = b.effective(all_files, b.FORMATS[target])
        destination = repository / directory
        existing = b.tree(destination) if destination.exists() else {}
        if set(existing) - set(assets):
            raise ValueError('Overlay contains resources outside copper scope: ' + directory)
        for name, data in assets.items():
            output = destination / name
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(data)
        if b.tree(destination) != assets:
            raise ValueError('Integrated bytes differ')
        checks.append({'directory': directory, 'source_artifact': path.name,
                       'assets': len(assets), 'effective_assets_sha256': b.tree_hash(assets)})
    metadata_path = repository / 'pack.mcmeta'
    text = metadata_path.read_text(encoding='utf-8')
    metadata = json.loads(text)
    current = [entry for entry in metadata['overlays']['entries'] if entry['directory'] == 'overlay_69']
    if len(current) != 1 or current[0]['min_format'] != 69 or current[0]['max_format'] != 75:
        raise ValueError('Existing overlay_69 changed; review before integrating')
    new_entry = {'directory': 'overlay_copper_26',
                 'formats': {'min_inclusive': 84, 'max_inclusive': 97},
                 'min_format': [84, 0], 'max_format': [97, 1]}
    matches = [entry for entry in metadata['overlays']['entries'] if entry['directory'] == new_entry['directory']]
    if matches and matches != [new_entry]:
        raise ValueError('Conflicting compilation overlay metadata')
    if not matches:
        # Retain the formatting and bytes of every original metadata entry.
        closing = text.rfind('\n\t\t]')
        if closing < 0:
            raise ValueError('Unexpected original metadata layout')
        entry_text = json.dumps(new_entry, indent=4).splitlines()
        insertion = ',\n' + '\n'.join('\t\t\t' + line for line in entry_text)
        text = text[:closing] + insertion + text[closing:]
        metadata_path.write_text(text, encoding='utf-8', newline='\n')
    readback = json.loads(metadata_path.read_text(encoding='utf-8'))
    old_entries = [e for e in readback['overlays']['entries'] if e['directory'] != new_entry['directory']]
    if old_entries != [e for e in metadata['overlays']['entries'] if e['directory'] != new_entry['directory']] or readback['pack'] != metadata['pack']:
        raise ValueError('Original compilation metadata changed')
    record = {'method': 'Only copper item resources added in late-version overlays.', 'checks': checks,
              'other_compilation_assets_replaced': False,
              'broader_compilation_visual_status': 'Not tested in this pass.'}
    (b.ROOT / 'docs/compilation-integration.json').write_bytes(b.json_bytes(record))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    integrate()
