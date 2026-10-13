"""Check the added compilation copper overlays with the old metadata retained."""
import argparse
import json
import os
import subprocess
from pathlib import Path

import build as b
import native_check as n


def check(cache=None):
    if cache:
        n.CACHE = cache.resolve()
    n.CACHE.mkdir(parents=True, exist_ok=True)
    subprocess.run(['javac', '--release', '17', '-d', str(n.CACHE),
                    str(b.ROOT / 'tools/NativePackCheck.java')], check=True, capture_output=True)
    repo = b.ROOT.parent
    files = {'pack.mcmeta': (repo / 'pack.mcmeta').read_bytes()}
    files.update({'assets/' + name: data for name, data in b.tree(repo / 'assets').items()})
    for entry in json.loads(files['pack.mcmeta'])['overlays']['entries']:
        directory = entry['directory']
        if (repo / directory).exists():
            files.update({directory + '/' + name: data for name, data in b.tree(repo / directory).items()})
    output = b.ROOT / '.work/compilation-check.zip'
    b.archive(files, output)
    n.universal.ARTIFACT = output
    mc = Path(os.environ['APPDATA']) / '.minecraft' if 'APPDATA' in os.environ else Path.home() / '.minecraft'
    rows = []
    for version in ('1.21.9', '26.3'):
        meta = b.read_json(b.ROOT / 'source/minecraft' / ('minecraft-' + version + '-metadata.json'))
        directory = n.CACHE / version
        directory.mkdir(exist_ok=True)
        jar = n.fetch(meta['downloads']['client'], directory / 'client.jar', (
            mc / 'versions' / version / (version + '.jar'),))
        libraries = n.dependencies(meta, mc)
        names = n.mapped_properties(meta, directory)
        actual = n.probe(version, meta, jar, libraries, names, *b.FORMATS[version])
        expected, selected = b.effective(files, b.FORMATS[version])
        if (actual['compatibility'] != 'COMPATIBLE' or actual['asset_count'] != len(expected)
                or actual['effective_assets_sha256'] != b.tree_hash(expected)
                or actual['selected_overlays'] != '[' + ', '.join(selected) + ']'):
            raise ValueError('Compilation overlay reader mismatch')
        with n.zipfile.ZipFile(b.ROOT / 'dist' / f'VisualWaxedCopperItems-32x-mc-{version}.zip') as archive:
            copper = {name: archive.read(name) for name in archive.namelist() if name.startswith('assets/')}
        if any(expected.get(name) != data for name, data in copper.items()):
            raise ValueError('Compilation copper resources differ from standalone')
        actual['copper_resources_match_standalone'] = True
        rows.append(actual)
    report = {'minecraft_window_or_world_started': False,
              'scope': 'Native metadata and full resource-byte resolution only; broader compilation visuals untested.',
              'checks': rows}
    (b.ROOT / 'docs/compilation-native-check.json').write_bytes(b.json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path)
    check(parser.parse_args().cache)
