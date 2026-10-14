"""Refresh only the approved copper overlays in the full root compilation."""
import json
import zipfile
import build as b


def integrate():
    repository = b.ROOT.parent
    source = b.ROOT / 'dist/VisualWaxedCopperItems-32x-mc-1.21.9-to-26.3.zip'
    with zipfile.ZipFile(source) as archive:
        files = {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()}
    metadata_path = repository / 'pack.mcmeta'
    metadata = json.loads(metadata_path.read_bytes())
    checks = []
    for directory, prefix, minimum in (
        ('overlay_copper_items', '', 69),
        ('overlay_copper_items_26_1', 'copper_26_1/', 84),
    ):
        expected_entry = {'directory': directory,
                          'formats': {'min_inclusive': minimum, 'max_inclusive': 97},
                          'min_format': [minimum, 0], 'max_format': [97, 1]}
        entries = [e for e in metadata['overlays']['entries'] if e['directory'] == directory]
        if entries != [expected_entry]:
            raise ValueError('Compilation metadata differs; review before refreshing overlays')
        assets = {name.removeprefix(prefix): data for name, data in files.items()
                  if name.startswith(prefix + 'assets/')}
        destination = repository / directory
        existing = b.tree(destination)
        if set(existing) - set(assets):
            raise ValueError('Existing overlay contains extra assets')
        for name, data in assets.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        assert b.tree(destination) == assets
        checks.append({'directory': directory, 'assets': len(assets),
                       'resource_tree_sha256': b.tree_hash(assets)})
    print(json.dumps({'overlays_refreshed': checks, 'other_pack_files_changed': False}, indent=2))


if __name__ == '__main__':
    integrate()
