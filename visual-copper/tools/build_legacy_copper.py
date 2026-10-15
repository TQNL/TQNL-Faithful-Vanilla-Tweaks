"""Extend the reviewed 32x/64x copper item packs to Minecraft 1.17-26.3.

The original Faithful-derived artwork and every modern rendering resource are
retained byte for byte. Older clients receive only their native copper items;
overlays add later items and the 1.21.4 item-definition schema where supported.
No blockstate, block texture, entity texture or live-golem resource is changed.
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import zipfile

import build as b

ROOT = b.ROOT
DEFAULT_MANIFEST = ROOT / 'source/minecraft/legacy-client-manifest.json'
OUTPUT_REPORT = ROOT / 'docs/legacy-copper-build-verification.json'
EARLIEST_FORMAT = (7, 0)
DECLARED_MINIMUM = (7, 0)
LEGACY_PACK_MARKER = 15
LATEST_FORMAT = (97, 1)


def read_archive(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError('Invalid source archive: ' + path.name)
        files = {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}
        if len(files) != len([info for info in archive.infolist() if not info.is_dir()]):
            raise ValueError('Duplicate archive entries')
    return files


def effective(files, fmt):
    """Resolve legacy or modern format predicates in declaration order."""
    metadata = json.loads(files['pack.mcmeta'])
    major, minor = tuple(fmt)
    minimum = b.bound(metadata['pack']['min_format'])
    maximum = b.bound(metadata['pack']['max_format'], True)
    # Pre-overlay clients ignore supported_formats and can manually enable
    # this pack's compatible legacy models despite their TOO_NEW warning.
    legacy_manual_enable = major < 18 and EARLIEST_FORMAT <= (major, minor) <= maximum
    if not legacy_manual_enable and not minimum <= (major, minor) <= maximum:
        raise ValueError('Requested format outside supported interval')
    assets = {name: data for name, data in files.items() if name.startswith('assets/')}
    selected = []
    # Overlays did not exist before 1.20.2 / resource format 18.
    if major < 18:
        return assets, selected
    for overlay in metadata.get('overlays', {}).get('entries', []):
        if major < 65:
            formats = overlay['formats']
            enabled = formats['min_inclusive'] <= major <= formats['max_inclusive']
        else:
            enabled = b.bound(overlay['min_format']) <= (major, minor) <= b.bound(overlay['max_format'], True)
        if enabled:
            prefix = overlay['directory'] + '/'
            assets.update({name[len(prefix):]: data for name, data in files.items()
                           if name.startswith(prefix + 'assets/')})
            selected.append(overlay['directory'])
    return assets, selected


def item_id(value):
    name = value.replace('assets/minecraft/models/item/', '').removesuffix('.json')
    return name.removeprefix('minecraft:')


def load_clients(path):
    data = b.read_json(path)
    clients = data['clients']
    if not clients or clients[0]['version'] != '1.17' or clients[-1]['version'] != '26.3':
        raise ValueError('Manifest must cover stable clients chronologically from 1.17 through 26.3')
    seen = set()
    for client in clients:
        if client['version'] in seen:
            raise ValueError('Duplicate stable client')
        seen.add(client['version'])
        if len(client['format']) != 2:
            raise ValueError('Expected explicit format major/minor pair')
        if client['format'][0] < 69 and not client.get('waxed_item_models'):
            raise ValueError('Older client needs native waxed item model inventory')
    return data, clients


def resource_path(value, kind):
    namespace, separator, location = value.partition(':')
    if not separator:
        namespace, location = 'minecraft', namespace
    suffix = '.json' if kind == 'models' else '.png'
    return f'assets/{namespace}/{kind}/{location}{suffix}'


def model_closure(modern, ids, include_definitions):
    """Copy only reviewed item models/textures needed by native item IDs."""
    result = {}
    pending = [f'assets/minecraft/models/item/{name}.json' for name in sorted(ids)]
    while pending:
        name = pending.pop()
        if name in result:
            continue
        if name not in modern:
            # Native vanilla parent models/textures remain supplied by Minecraft.
            continue
        result[name] = modern[name]
        model = json.loads(modern[name])
        if model.get('parent') and not model['parent'].startswith('builtin/'):
            pending.append(resource_path(model['parent'], 'models'))
        for value in model.get('textures', {}).values():
            if not value.startswith('#'):
                texture = resource_path(value, 'textures')
                if texture in modern:
                    result[texture] = modern[texture]
    if include_definitions:
        for name in ids:
            path = f'assets/minecraft/items/{name}.json'
            definition = json.loads(modern[path])
            # Older item definitions need only the simple model type. Statue
            # selectors/special renderers are not introduced before format 69.
            if definition != {'model': {'type': 'minecraft:model', 'model': f'minecraft:item/{name}'}}:
                raise ValueError('Unexpected legacy item definition: ' + name)
            result[path] = modern[path]
    if not result:
        raise ValueError('Empty legacy copper resource tree')
    return result


@lru_cache(maxsize=1)
def historical_sources():
    return b.read_json(ROOT / 'source/legacy-faithful-sources.json')


@lru_cache(maxsize=None)
def historical_texture(family, name):
    """Apply the same reviewed wax mask to a pinned historical original."""
    source_record = historical_sources()['families'][family]
    coverage = b.read_json(ROOT / 'source/source-coverage.json')
    mapping_row = next(row for row in coverage['coverage'] if row['client'] == '1.21.9' and row['resolution'] == 64)
    mapping = dict(next(row for row in mapping_row['mapping'] if row['vt_path'] == name))
    native = mapping['native_source']
    mapping['sha256'] = source_record['textures'][native]['sha256']
    source_root = ROOT / 'source/faithful/64x/legacy' / family
    vt = (ROOT / 'source/vanilla-tweaks/1.21' / name).read_bytes()
    data, derivation = b.derive_texture(name, vt, mapping, source_root, 64)
    derivation['historical_source_family'] = family
    derivation['historical_source_id'] = source_record['source_id']
    return data, derivation


def expected_assets(source, client):
    version, fmt = client['version'], client['format']
    if version in b.FORMATS:
        # This is the actual byte tree reviewed for each modern exact client.
        return b.effective(source, fmt)[0]
    modern, _ = b.effective(source, [69, 0])
    ids = {item_id(name) for name in client['waxed_item_models']}
    known = {name.removeprefix('assets/minecraft/models/item/').removesuffix('.json')
             for name in modern if name.startswith('assets/minecraft/models/item/')}
    missing = ids - known
    if missing:
        raise ValueError('Native copper items missing from reviewed artwork: ' + ', '.join(sorted(missing)))
    assets = model_closure(modern, ids, include_definitions=fmt[0] >= 46)
    resolution = b.image(modern['assets/minecraft/textures/item/waxed_copper_block.png']).width
    if resolution == 64:
        binding = historical_sources()['clients'][version]
        family = binding['family']
        if family:
            overrides = historical_sources()['families'][family]['textures']
            coverage = b.read_json(ROOT / 'source/source-coverage.json')
            mapping_row = next(row for row in coverage['coverage'] if row['client'] == '1.21.9' and row['resolution'] == 64)
            for mapping in mapping_row['mapping']:
                name = mapping['vt_path']
                if name in assets and mapping.get('native_source') in overrides:
                    assets[name] = historical_texture(family, name)[0]
    return assets


def overlay(directory, fmt):
    return {'directory': directory,
            'formats': {'min_inclusive': fmt[0], 'max_inclusive': 97},
            'min_format': list(fmt), 'max_format': list(LATEST_FORMAT)}


def build_edition(resolution, clients):
    source_path = ROOT / 'dist' / f'VisualWaxedCopperItems-{resolution}x-mc-1.21.9-to-26.3.zip'
    source = read_archive(source_path)
    source_meta = json.loads(source['pack.mcmeta'])
    source_prefixes = tuple(entry['directory'] + '/' for entry in source_meta['overlays']['entries'])
    files = {name: data for name, data in source.items()
             if not name.startswith('assets/') and not name.startswith(source_prefixes)}
    files['pack.mcmeta'] = b.json_bytes({'pack': {
        'pack_format': LEGACY_PACK_MARKER,
        'supported_formats': {'min_inclusive': DECLARED_MINIMUM[0], 'max_inclusive': LATEST_FORMAT[0]},
        'min_format': list(DECLARED_MINIMUM), 'max_format': list(LATEST_FORMAT),
        'description': f'Visual Waxed Copper Items V3 - Faithful {resolution}x | 1.17-26.3'},
        'overlays': {'entries': []}})
    metadata = json.loads(files['pack.mcmeta'])
    previous = None
    expected_by_version = {}
    for client in clients:
        assets = expected_assets(source, client)
        expected_by_version[client['version']] = assets
        if previous is None:
            files.update(assets)
        else:
            removed = previous.keys() - assets.keys()
            if removed:
                raise ValueError('A cumulative overlay cannot delete resources: ' + ', '.join(sorted(removed)))
            changes = {name: data for name, data in assets.items() if previous.get(name) != data}
            if changes:
                if client['format'][0] < 18:
                    raise ValueError('Pre-overlay native resource requirements differ: ' + client['version'])
                directory = 'copper_' + client['version'].replace('.', '_')
                metadata['overlays']['entries'].append(overlay(directory, client['format']))
                files.update({directory + '/' + name: data for name, data in changes.items()})
        previous = assets
    files['pack.mcmeta'] = b.json_bytes(metadata)
    files['Selected Packs.txt'] = (f'Visual Waxed Copper (Items)\nVersion: 1.17 - 26.3\n'
                                  f'Edition: Faithful {resolution}x\n').encode()
    files['README.txt'] = (
        f'VisualWaxedCopperItems V3 - Faithful {resolution}x\nMinecraft 1.17 - 26.3\n\n'
        'Enable this item-only add-on above a matching Faithful pack.\n'
        'Pinned original Faithful artwork is used for the corresponding copper items.\n'
        'Later copper items and item-definition schemas are selected through format overlays.\n'
        'Modern 1.21.9-26.3 item textures and rendering resources match the reviewed V3 packs exactly.\n'
        'Placed blocks, their textures, and live copper golems are unchanged.\n\n'
        'Before Minecraft 1.20.2, clients only recognize one pack_format. The root uses format 15\n'
        '(1.20/1.20.1), because modern range readers require this legacy marker to be at least 15.\n'
        'The declared supported range still begins at format 7 / 1.17. Minecraft 1.17-1.19.4\n'
        'therefore show an unavoidable compatibility warning and require manual enabling.\n'
        'Those clients can still load the legacy item models; the warning is not a green compatibility claim.\n'
        'See the release documentation for exact native, structural and visual test scope.\n\n'
        'Credits: Vanilla Tweaks, Faithful artists and TQNL. See credits.txt, source-provenance.json\n'
        'and the included Faithful license files.\n').encode()
    provenance = json.loads(files['source-provenance.json'])
    provenance['legacy_compatibility'] = {
        'method': 'Reuse the pinned original Faithful artwork through version-appropriate item models and overlays.',
        'modern_artifact': source_path.name, 'modern_artifact_sha256': b.digest(source_path.read_bytes()),
        'modern_resource_bytes_unchanged': True,
        'native_item_inventory': 'source/minecraft/legacy-client-manifest.json'}
    if resolution == 64:
        provenance['legacy_faithful_sources'] = historical_sources()
        provenance['legacy_texture_derivations'] = []
        # The cache entries cover only actual historical target textures; the
        # explicit mapping keeps the provenance independent of cache internals.
        coverage = b.read_json(ROOT / 'source/source-coverage.json')
        mappings = next(row for row in coverage['coverage'] if row['client'] == '1.21.9' and row['resolution'] == 64)['mapping']
        for family, record in historical_sources()['families'].items():
            for mapping in mappings:
                if mapping.get('native_source') in record['textures']:
                    name = mapping['vt_path']
                    if any(name in assets for assets in expected_by_version.values()):
                        provenance['legacy_texture_derivations'].append(historical_texture(family, name)[1])
        for name in historical_sources()['licenses']:
            files[name] = (ROOT / 'source/licenses' / name).read_bytes()
    files['source-provenance.json'] = b.json_bytes(provenance)
    checks = []
    for client in clients:
        actual, selected = effective(files, client['format'])
        expected = expected_by_version[client['version']]
        if actual != expected:
            raise ValueError('Effective resources differ for ' + client['version'])
        native_ids = sorted(item_id(name) for name in client.get('waxed_item_models', []))
        checks.append({'version': client['version'], 'format': client['format'],
                       'native_waxed_item_ids': native_ids,
                       'selected_overlays': selected, 'asset_count': len(actual),
                       'effective_assets_sha256': b.tree_hash(actual),
                       'modern_reviewed_resources_byte_identical': client['version'] in b.FORMATS,
                       'pre_1_20_2_compatibility_warning': client['format'][0] < 15,
                       'declared_metadata_compatibility': client['format'][0] >= 15})
    name = f'VisualWaxedCopperItems-{resolution}x-mc-1.17-to-26.3.zip'
    target = ROOT / 'dist' / name
    archive_sha = b.archive(files, target, compression_level=9)
    return {'resolution': resolution, 'filename': name, 'sha256': archive_sha,
            'bytes': target.stat().st_size, 'files': len(files),
            'modern_reference_sha256': b.digest(source_path.read_bytes()),
            'checks': checks, 'overlays': metadata['overlays']['entries']}


def build(manifest=DEFAULT_MANIFEST):
    _, clients = load_clients(manifest)
    originals = {path: b.digest(path.read_bytes()) for path in (
        ROOT/'dist/VisualWaxedCopperItems-16x-mc-1.21.9-to-26.3.zip',
        ROOT.parent/'dist/TQNL Faithful Vanilla Tweaks.zip')}
    artifacts = [build_edition(resolution, clients) for resolution in (32, 64)]
    if any(b.digest(path.read_bytes()) != original for path, original in originals.items()):
        raise ValueError('A preserved archive changed')
    report = {'schema_version': 1,
              'scope': 'Offline deterministic build and expected resource maps; native/visual verification is separate.',
              'manifest': 'source/minecraft/legacy-client-manifest.json',
              'manifest_sha256': b.digest(manifest.read_bytes()),
              'full_releases': [client['version'] for client in clients],
              'minecraft_started': False, 'preserved_16x_and_full_compilation_archives': True,
              'declared_pack_format': 15,
              'declared_min_format': [7, 0],
              'declared_max_format': [97, 1],
              'functional_legacy_resource_min_format': [7, 0],
              'pre_1_20_2_warning': '1.17-1.19.4 ignore supported_formats and show TOO_NEW for the legacy pack_format marker 15, requiring manual enabling. Their legacy models remain compatible, and the declared supported range begins at format 7. 1.20/1.20.1 match format 15. Modern native readers require the legacy pack_format marker to be at least 15, not the minimum supported format.',
              'artifacts': artifacts}
    OUTPUT_REPORT.write_bytes(b.json_bytes(report))
    (ROOT/'dist/SHA256SUMS-1.17-to-26.3.txt').write_text(''.join(
        f"{artifact['sha256']}  {artifact['filename']}\n" for artifact in artifacts),
        encoding='utf-8', newline='\n')
    print(json.dumps({'artifacts': [{k: row[k] for k in ('filename','sha256','bytes')} for row in artifacts],
                      'full_release_count': len(clients), 'modern_resource_bytes_unchanged': True,
                      'minecraft_started': False}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    build(parser.parse_args().manifest)
