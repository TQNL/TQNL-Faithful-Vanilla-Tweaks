"""Build local antenna-border review ZIPs without replacing published artifacts."""
import json
import io
import subprocess
import zipfile

from PIL import Image, ImageDraw

import build as b


def read_zip(path):
    # Retired exact-version artifacts remain available in the original V3
    # Git snapshot; current distribution contains only combined ZIPs.
    source = path if path.exists() else io.BytesIO(subprocess.check_output([
        'git', '-C', str(b.ROOT.parent), 'show',
        'ec3cee6d7c447f6564b7d7c1dec740621121c897:' + path.relative_to(b.ROOT.parent).as_posix()]))
    with zipfile.ZipFile(source) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def main():
    coverage = b.read_json(b.ROOT / 'source/source-coverage.json')
    output = b.ROOT / '.work/antenna-review'
    output.mkdir(parents=True, exist_ok=True)
    rectangles = [face['rect_native'] for face in
                  b.read_json(b.ROOT / 'tools/mask_patterns.json')['additional_faces']['waxed_copper_golem_statue']
                  if face['part'] == 'antenna_stem']
    records, atlas_previews = [], []
    for resolution in (32, 64):
        packs, family_cache = {}, {}
        scale, band = resolution // 16, resolution // 32
        for version in b.VERSIONS:
            files = read_zip(b.ROOT / 'dist' / f'VisualWaxedCopperItems-{resolution}x-mc-{version}.zip')
            family = b.FAMILIES[version]
            if family not in family_cache:
                row = next(row for row in coverage['coverage']
                           if row['client'] == version and row['resolution'] == resolution)
                mappings = {m['vt_path']: m for m in row['mapping']}
                baseline = b.ROOT / 'source/vanilla-tweaks' / ('1.21' if version.startswith('1.21') else '26.1')
                source_root = b.ROOT / 'source/faithful' / f'{resolution}x' / family
                textures, infos = {}, {}
                for stage in ('', 'exposed_', 'weathered_', 'oxidized_'):
                    name = f'assets/minecraft/textures/item/waxed_{stage}copper_golem_statue.png'
                    textures[name], infos[name] = b.derive_texture(name, (baseline / name).read_bytes(),
                                                                  mappings[name], source_root, resolution)
                    before, after = b.image(files[name]), b.image(textures[name])
                    allowed = Image.new('L', after.size)
                    draw = ImageDraw.Draw(allowed)
                    for rect in rectangles:
                        x0, y0, x1, y1 = [value * scale for value in rect]
                        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
                        mask, _ = b.mask_for_texture(name, b.image((source_root / mappings[name]['native_source']).read_bytes()), scale, band)
                        for y in range(y0, y1):
                            for x in range(x0, x1):
                                border = min(x - x0, x1 - 1 - x, y - y0, y1 - 1 - y) < band
                                if bool(mask.getpixel((x, y))) != border:
                                    raise ValueError('Antenna face is not an exact perimeter ring')
                    if before.getchannel('A').tobytes() != after.getchannel('A').tobytes():
                        raise ValueError('Alpha changed')
                    changed = 0
                    for y in range(after.height):
                        for x in range(after.width):
                            if before.getpixel((x, y)) != after.getpixel((x, y)):
                                if not allowed.getpixel((x, y)):
                                    raise ValueError('Change outside antenna stem')
                                changed += 1
                    records.append({'resolution': resolution, 'family': family, 'texture': name,
                                    'changed_pixels': changed, 'only_stem_changed': True,
                                    'all_six_faces_have_exact_perimeters': True, 'alpha_unchanged': True})
                    if family == '26.3' and stage == 'oxidized_':
                        atlas_previews.append((resolution, before.crop((37 * scale, 8 * scale, 45 * scale, 14 * scale)),
                                               after.crop((37 * scale, 8 * scale, 45 * scale, 14 * scale))))
                family_cache[family] = (textures, infos)
            textures, infos = family_cache[family]
            files.update(textures)
            provenance = json.loads(files['source-provenance.json'])
            provenance['texture_derivations'] = [infos.get(info['path'], info) for info in provenance['texture_derivations']]
            provenance['local_review'] = 'All six antenna stem faces use full perimeter rings.'
            files['source-provenance.json'] = b.json_bytes(provenance)
            packs[version] = files
        files = b.combined(resolution, packs)
        metadata = json.loads(files['pack.mcmeta'])
        metadata['pack']['description'] = f'LOCAL REVIEW: Antenna wax borders - Faithful {resolution}x\nMinecraft 1.21.9 - 26.3'
        files['pack.mcmeta'] = b.json_bytes(metadata)
        files['README.txt'] += b'\nLOCAL ANTENNA REVIEW: full wax borders on every antenna pole face. Not published.\n'
        path = output / f'VisualWaxedCopperItems-{resolution}x-mc-1.21.9-to-26.3.zip'
        sha = b.archive(files, path)
        original = read_zip(b.ROOT / 'dist' / path.name)
        for name, data in original.items():
            if name.endswith('.json') and '/items/' in name or '/models/' in name:
                if files[name] != data:
                    raise ValueError('Rendering JSON changed')
        records.append({'artifact': path.name, 'sha256': sha, 'bytes': path.stat().st_size,
                        'combined_versions_verified': len(b.VERSIONS), 'rendering_json_unchanged': True})
    sheet = Image.new('RGB', (750, 350), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    for row, (resolution, before, after) in enumerate(atlas_previews):
        for col, (label, im) in enumerate((('Before', before), ('After', after))):
            draw.text((col * 375 + 10, row * 175 + 10), f'{resolution}x {label}: antenna UV faces', fill='white')
            im = im.resize((192, 144), Image.Resampling.NEAREST)
            sheet.paste(im, (col * 375 + 10, row * 175 + 30), im)
    sheet.save(output / 'antenna-before-after.png')
    (output / 'verification.json').write_bytes(b.json_bytes({'minecraft_started': False,
            'published': False, 'checks': records}))
    print(json.dumps({'local_review_packs': 2, 'texture_checks': len(records) - 2,
                      'output': str(output)}, indent=2))


if __name__ == '__main__':
    main()
