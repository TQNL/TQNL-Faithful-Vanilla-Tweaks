"""Build the complete Visual Waxed Copper item add-ons, without starting Minecraft.

Inputs are pinned minimal official Faithful textures and the accepted full VT
repair. UV coordinates and native statue item definitions are never rescaled.
"""
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
from wax_masks import canonical_texture_name, mask_for_texture

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {'1.21.9': '1.21.10', '1.21.10': '1.21.10',
            '1.21.11': '1.21.11', '26.1': '26.1', '26.1.1': '26.1',
            '26.1.2': '26.1', '26.2': '26.2', '26.3': '26.3'}
VERSIONS = tuple(FAMILIES)
FORMATS = {'1.21.9': [69, 0], '1.21.10': [69, 0], '1.21.11': [75, 0],
           '26.1': [84, 0], '26.1.1': [84, 0], '26.1.2': [84, 0],
           '26.2': [88, 0], '26.3': [97, 1]}
EDITION_NAMES = {16: '16x Statue Patch', 32: 'Faithful 32x', 64: 'Faithful 64x'}
STATUES = {f'assets/minecraft/items/waxed_{stage}copper_golem_statue.json'
           for stage in ('', 'exposed_', 'weathered_', 'oxidized_')}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def tree(path):
    result = {}
    for entry in sorted(path.rglob('*')):
        if entry.is_symlink() or entry.is_junction():
            raise ValueError('Linked source entry is not allowed: ' + str(entry))
        if entry.is_file():
            result[entry.relative_to(path).as_posix()] = entry.read_bytes()
    return result


def tree_hash(files):
    return digest(''.join(f'{digest(data)}  {name}\n' for name, data in sorted(files.items())).encode())


def bound(value, upper=False):
    return (value, 2147483647 if upper else 0) if isinstance(value, int) else tuple(value)


def effective(files, fmt):
    metadata = json.loads(files['pack.mcmeta'])
    if not bound(metadata['pack']['min_format']) <= tuple(fmt) <= bound(metadata['pack']['max_format'], True):
        raise ValueError('Format outside metadata')
    assets = {n: b for n, b in files.items() if n.startswith('assets/')}
    selected = []
    for overlay in metadata.get('overlays', {}).get('entries', []):
        if bound(overlay['min_format']) <= tuple(fmt) <= bound(overlay['max_format'], True):
            prefix = overlay['directory'] + '/'
            assets.update({n[len(prefix):]: b for n, b in files.items()
                           if n.startswith(prefix + 'assets/')})
            selected.append(overlay['directory'])
    return assets, selected


def png_bytes(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG', optimize=False, compress_level=9)
    return stream.getvalue()


def image(data):
    return Image.open(io.BytesIO(data)).convert('RGBA')


def prepare_source(name, source, vt, scale):
    """The custom stair sheets and thin side use only these native UV islands."""
    result = source.copy()
    if any(part in name for part in ('_stairs1', '_stairs2', '_trapdoor_side')):
        geometry_alpha = vt.getchannel('A').resize(source.size, Image.Resampling.NEAREST)
        result.putalpha(ImageChops.multiply(source.getchannel('A'), geometry_alpha))
    if 'lightning_rod' in name:
        # VT's custom shaft uses the copper strip from native x=0 at x=2.
        # Copy at the true Faithful pixel scale; model UVs stay unchanged.
        strip = source.crop((0, 4 * scale, 2 * scale, 16 * scale))
        result.paste(strip, (2 * scale, 4 * scale))
        cap = source.crop((0, 4 * scale, 2 * scale, 6 * scale))
        result.paste(cap, (4 * scale, 0))
    return result


def derive_texture(name, data, mapping, source_root, resolution):
    scale = resolution // 16
    vt = image(data)
    if not name.endswith('/waxed_copper_door_outline.png') and mapping.get('native_source'):
        source_file = source_root / mapping['native_source']
        source = Image.open(source_file).convert('RGBA')
        if digest(source_file.read_bytes()) != mapping['sha256']:
            raise ValueError('Pinned source hash mismatch: ' + str(source_file))
    else:
        if not name.endswith('/waxed_copper_door_outline.png'):
            raise ValueError('Unknown auxiliary texture: ' + name)
        # This unused VT helper contains only gold and transparency, no copper
        # artwork to replace with Faithful. Retain its topology and palette.
        source = vt.resize((vt.width * scale, vt.height * scale), Image.Resampling.NEAREST)
        return png_bytes(source), {'path': name, 'source': 'Vanilla Tweaks gold-only auxiliary outline',
                'dimensions': list(source.size), 'active_model_reference': False,
                'method': 'Nearest scale of the retained unused gold-only helper',
                'sha256': digest(png_bytes(source))}
    if source.size != (vt.width * scale, vt.height * scale):
        raise ValueError('Source dimensions disagree with native UV atlas: ' + name)
    original = prepare_source(name, source, vt, scale)
    mask, gold = mask_for_texture(Path(name).name, original, scale, 1 if resolution == 32 else 2)
    if mask.mode != 'L' or mask.size != original.size or gold.size != original.size:
        raise ValueError('Invalid wax mask: ' + name)
    result = original.copy()
    pixels, base, mask_pixels, gold_pixels = result.load(), original.load(), mask.load(), gold.load()
    count = 0
    added_alpha = 0
    exterior_stroke = canonical_texture_name(name) in {
        'waxed_copper_bars', 'waxed_copper_chain', 'waxed_copper_lantern'}
    for y in range(result.height):
        for x in range(result.width):
            if mask_pixels[x, y]:
                if base[x, y][3] == 0 and not exterior_stroke:
                    raise ValueError('Wax mask recolors a transparent pixel: ' + name)
                if not base[x, y][3]:
                    added_alpha += 1
                pixels[x, y] = (*gold_pixels[x, y][:3], base[x, y][3] or gold_pixels[x, y][3])
                count += 1
    if not exterior_stroke and result.getchannel('A').tobytes() != original.getchannel('A').tobytes():
        raise ValueError('Wax changed source alpha: ' + name)
    if exterior_stroke and any(base[x, y][3] and pixels[x, y] != base[x, y]
                              for y in range(result.height) for x in range(result.width)):
        raise ValueError('Exterior wax stroke changed original Faithful copper: ' + name)
    if not count:
        raise ValueError('Empty wax mask: ' + name)
    output_bytes, original_bytes = result.tobytes(), original.tobytes()
    changed = sum(output_bytes[i:i + 4] != original_bytes[i:i + 4]
                  for i in range(0, len(output_bytes), 4))
    if changed > count:
        raise ValueError('Pixels outside wax mask changed')
    return png_bytes(result), {
        'path': name, 'source': mapping.get('native_source', 'custom native door UV composite'),
        'source_sha256': mapping.get('sha256'), 'dimensions': list(result.size),
        'wax_pixels': count, 'changed_pixels': changed,
        'source_alpha_preserved_after_uv_mapping': not bool(added_alpha),
        'exterior_gold_pixels_added': added_alpha,
        'original_opaque_pixels_preserved': exterior_stroke,
        'outline_method': 'Exterior gold stroke, enclosed holes retained' if exterior_stroke else 'Inward wax on model face or door frame',
        'unmasked_prepared_source_pixels_identical': True,
        'pixel_equality_reference': 'Faithful source after the explicitly recorded VT UV preparation',
        'uv_crop': any(part in name for part in ('_stairs1', '_stairs2', '_trapdoor_side')),
        'uv_strip_copy': 'lightning_rod' in name,
        'uv_preparation': ({'shaft_source_native': [0, 4, 2, 16], 'shaft_destination_native': [2, 4, 4, 16],
                            'cap_source_native': [0, 4, 2, 6], 'cap_destination_native': [4, 0, 6, 2]}
                           if 'lightning_rod' in name else
                           {'alpha_crop_to_custom_vt_uv_islands': True}
                           if any(part in name for part in ('_stairs1', '_stairs2', '_trapdoor_side')) else {}),
        'sha256': digest(png_bytes(result))}


def metadata(resolution, target, minimum, maximum):
    return {'pack': {'description': f'Visual Waxed Copper (Items) - {EDITION_NAMES[resolution]}\n'
                     f'Minecraft {target} | TQNL | Vanilla Tweaks' + (' | Faithful' if resolution > 16 else ''),
                     'min_format': minimum, 'max_format': maximum}}


def build_version(version, resolution, coverage, provenance):
    base_family = '1.21' if version.startswith('1.21') else '26.1'
    files = tree(ROOT / 'source/vanilla-tweaks' / base_family)
    files['pack.mcmeta'] = json_bytes(metadata(resolution, version, FORMATS[version], FORMATS[version]))
    files['Selected Packs.txt'] = (f'Visual Waxed Copper (Items)\nVersion: {version}\n'
                                   f'Edition: {EDITION_NAMES[resolution]}\n').encode()
    texture_rows = []
    selected = []
    if resolution > 16:
        family = FAMILIES[version]
        row = next(r for r in coverage['coverage'] if r['client'] == version and r['resolution'] == resolution)
        mappings = {m['vt_path']: m for m in row['mapping']}
        source_root = ROOT / 'source/faithful' / f'{resolution}x' / family
        for name, data in tuple(files.items()):
            if name.startswith('assets/') and name.endswith('.png'):
                files[name], info = derive_texture(name, data, mappings[name], source_root, resolution)
                texture_rows.append(info)
        selected = [s for s in provenance['sources'] if s['resolution'] == resolution and s['family'] == family]
    files['credits.txt'] = ('Credits:\nVanilla Tweaks: https://vanillatweaks.net/\n'
                            'Statue repair, masks and adaptation: TQNL\n' +
                            (f'Faithful {resolution}x: https://faithfulpack.net/\n'
                             'Official source assets and contributors: see source-provenance.json\n'
                             'Faithful License: https://faithfulpack.net/license/\n' if resolution > 16 else '')).encode()
    if selected:
        source = selected[0]
        attribution = provenance['artist_attribution'][f'{resolution}x']
        artists = sorted({author for asset in attribution['assets'] for author in asset['authors']})
        files['credits.txt'] += ('Faithful copper texture artists: ' + ', '.join(artists) + '\n').encode()
        license_path = ROOT / 'source/licenses' / source['license_file']
        files['LICENSE-Faithful.txt'] = license_path.read_bytes()
        files['source-provenance.json'] = json_bytes({'sources': selected,
                'texture_derivations': texture_rows,
                'attribution': attribution})
    files['README.txt'] = (f'VisualWaxedCopperItems V3 - {EDITION_NAMES[resolution]}\nMinecraft {version}\n\n'
        'Place this ZIP in .minecraft/resourcepacks and enable it above other packs.\n'
        'This contains the complete item-only tweak, including native pose-aware statue fixes.\n'
        'Placed copper blocks and live golems are unchanged. No full Faithful pack is bundled.\n' +
        (f'Use above the matching official Faithful {resolution}x pack for a consistent world.\n'
         f'Wax bands: {1 if resolution == 32 else 2} pixels on ordinary faces, narrowed on tiny UV islands.\n'
         'See the release documentation for the scope of source, UV and in-game visual checks.\n'
         if resolution > 16 else
         '16x rendering assets are identical to the previously accepted exact-release repair.\n') +
        '\nSources: https://vanillatweaks.net/ and https://faithfulpack.net/\n'
        'Faithful License: https://faithfulpack.net/license/\n').encode()
    # Rendering behavior must remain byte-identical to the corrected baseline.
    accepted = tree(ROOT / 'source/vanilla-tweaks' / base_family)
    if any(files[n] != data for n, data in accepted.items() if n.startswith('assets/') and n.endswith('.json')):
        raise ValueError('Rendering JSON unexpectedly changed')
    if resolution == 16 and effective(files, FORMATS[version])[0] != {n: b for n, b in accepted.items() if n.startswith('assets/')}:
        raise ValueError('16x accepted assets changed')
    if resolution == 16:
        pinned = next(row for row in read_json(ROOT / 'source/accepted-releases.json') if row['version'] == version)
        if tree_hash(effective(files, FORMATS[version])[0]) != pinned['effective_assets_sha256']:
            raise ValueError('16x resources disagree with the immutable accepted completion record')
    return files, texture_rows


def combined(resolution, version_files):
    files = dict(version_files[VERSIONS[0]])
    files['pack.mcmeta'] = json_bytes(metadata(resolution, '1.21.9 - 26.3', [69, 0], [97, 1]))
    meta = json.loads(files['pack.mcmeta'])
    previous = effective(version_files[VERSIONS[0]], FORMATS[VERSIONS[0]])[0]
    overlays = []
    for version in ('1.21.11', '26.1', '26.2', '26.3'):
        target = effective(version_files[version], FORMATS[version])[0]
        if previous.keys() - target.keys():
            raise ValueError('Overlay cannot delete a resource')
        changes = {n: b for n, b in target.items() if previous.get(n) != b}
        if changes:
            directory = 'copper_' + version.replace('.', '_')
            overlays.append({'directory': directory, 'min_format': FORMATS[version], 'max_format': [97, 1]})
            files.update({directory + '/' + n: b for n, b in changes.items()})
        previous = target
    meta['overlays'] = {'entries': overlays}
    files['pack.mcmeta'] = json_bytes(meta)
    files['Selected Packs.txt'] = f'Visual Waxed Copper (Items)\nVersion: 1.21.9 - 26.3\nEdition: {EDITION_NAMES[resolution]}\n'.encode()
    files['README.txt'] = files['README.txt'].replace(b'Minecraft 1.21.9\n', b'Minecraft 1.21.9 - 26.3\n') + b'Overlays select exact-family textures and the 26.1+ statue transformation.\n'
    if resolution > 16:
        records = [json.loads(version_files[v]['source-provenance.json']) for v in ('1.21.9', '1.21.11', '26.1', '26.2', '26.3')]
        files['source-provenance.json'] = json_bytes({'families': records})
        licenses = {source['license_file'] for record in records for source in record['sources']}
        for name in sorted(licenses):
            files[name] = (ROOT / 'source/licenses' / name).read_bytes()
        files.pop('LICENSE-Faithful.txt', None)
    for version in VERSIONS:
        actual, _ = effective(files, FORMATS[version])
        expected, _ = effective(version_files[version], FORMATS[version])
        if actual != expected:
            raise ValueError('Combined assets differ from exact-version pack: ' + version)
    # Reviewed native screenshot icons distinguish the two Faithful editions.
    # Icons affect pack presentation only; all validated resource maps above
    # and the original 16x archive remain unchanged.
    if resolution > 16:
        files['pack.png'] = (ROOT / 'source/icons' / f'pack-{resolution}x.png').read_bytes()
    return files


def archive(files, path, compression_level=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
        for name in sorted(files, key=lambda n: tuple(n.split('/'))):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            zip_file.writestr(entry, files[name], compresslevel=compression_level)
    with zipfile.ZipFile(path) as zip_file:
        if zip_file.testzip() or {n: zip_file.read(n) for n in zip_file.namelist()} != files:
            raise ValueError('ZIP readback failed')
    return digest(path.read_bytes())


def preview(packs):
    names = ['waxed_copper_block.png', 'waxed_cut_copper.png', 'waxed_copper_stairs1.png',
             'waxed_copper_trapdoor.png', 'waxed_copper_chain.png', 'waxed_copper_lantern.png',
             'waxed_copper_golem_statue.png', 'waxed_oxidized_copper_golem_statue.png',
             'waxed_copper_chest.png']
    sheet = Image.new('RGB', (len(names) * 190, 3 * 285), (38, 38, 38))
    draw = ImageDraw.Draw(sheet)
    for row, resolution in enumerate((16, 32, 64)):
        for col, name in enumerate(names):
            im = image(packs[resolution]['assets/minecraft/textures/item/' + name])
            size = (160, round(im.height / im.width * 160))
            im = im.resize(size, Image.Resampling.NEAREST)
            x, y = col * 190 + 10, row * 285 + 60
            sheet.paste(im, (x, y), im)
            draw.text((x, row * 285 + 8), f'{resolution}x', fill='white')
            draw.text((x, row * 285 + 26), name.replace('waxed_', '').replace('.png', '')[:26], fill='white')
    (ROOT / 'docs/previews').mkdir(exist_ok=True)
    sheet.save(ROOT / 'docs/previews/texture-contact-sheet.png')


def build():
    coverage = read_json(ROOT / 'source/source-coverage.json')
    provenance = read_json(ROOT / 'source/provenance.json')
    all_packs, artifacts, derivations = {}, [], {}
    for resolution in (16, 32, 64):
        packs = {}
        for version in VERSIONS:
            packs[version], rows = build_version(version, resolution, coverage, provenance)
            derivations[f'{resolution}x/{version}'] = rows
        packs['1.21.9-to-26.3'] = combined(resolution, packs)
        all_packs[resolution] = packs
        # Exact versions are assembled in memory for overlay equivalence;
        # the owner publishes only one combined ZIP per edition.
        for target, files in [('1.21.9-to-26.3', packs['1.21.9-to-26.3'])]:
            filename = f'VisualWaxedCopperItems-{resolution}x-mc-{target}.zip'
            path = ROOT / 'dist' / filename
            # Preserve the accepted 16x archive, and reproduce the final
            # reviewed 32x/64x release packaging at explicit compression 9.
            sha = archive(files, path, compression_level=9 if resolution > 16 else None)
            checks = []
            for version in VERSIONS if target == '1.21.9-to-26.3' else (target,):
                assets, selected = effective(files, FORMATS[version])
                checks.append({'version': version, 'format': FORMATS[version], 'selected_overlays': selected,
                               'asset_count': len(assets), 'effective_assets_sha256': tree_hash(assets)})
            artifacts.append({'resolution': resolution, 'target': target, 'filename': filename,
                              'sha256': sha, 'bytes': path.stat().st_size, 'files': len(files), 'checks': checks})
    preview({r: all_packs[r]['26.3'] for r in all_packs})
    report = {'schema_version': 1, 'minecraft_started': False,
              'visual_status': 'Offline build only. Targeted native Minecraft 26.3 wax review for the matching 32x/64x resources is recorded separately in docs/wax-review-verification.json; earlier accepted statue rendering is inherited.',
              'artifacts': artifacts, 'texture_checks': derivations}
    (ROOT / 'docs/build-verification.json').write_bytes(json_bytes(report))
    (ROOT / 'dist/SHA256SUMS.txt').write_text(''.join(f"{a['sha256']}  {a['filename']}\n" for a in artifacts), encoding='utf-8')
    print(json.dumps({'artifacts': len(artifacts), 'targets': 1, 'editions': 3, 'minecraft_started': False}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build()
