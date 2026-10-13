"""Check all exact and combined ZIPs with each exact client's native pack reader.

Client JARs, mappings and any missing Java libraries are cached outside the
Minecraft installation. All downloads are verified against the retained Mojang
metadata. This does not launch Minecraft or create a game profile/world.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

import argparse
from types import SimpleNamespace
import build as b
w = SimpleNamespace(ROOT=b.ROOT, load=b.read_json, digest=b.digest)
universal = SimpleNamespace(ARTIFACT=None)

CACHE = w.ROOT / '.work/native-pack-check'
ALIASES = {
    'SharedConstants': 'net.minecraft.SharedConstants',
    'Bootstrap': 'net.minecraft.server.Bootstrap',
    'Component': 'net.minecraft.network.chat.Component',
    'Location': 'net.minecraft.server.packs.PackLocationInfo',
    'Source': 'net.minecraft.server.packs.repository.PackSource',
    'FileSupplier': 'net.minecraft.server.packs.FilePackResources$FileResourcesSupplier',
    'Supplier': 'net.minecraft.server.packs.repository.Pack$ResourcesSupplier',
    'PackType': 'net.minecraft.server.packs.PackType',
    'Format': 'net.minecraft.server.packs.metadata.pack.PackFormat',
    'Pack': 'net.minecraft.server.packs.repository.Pack',
    'Metadata': 'net.minecraft.server.packs.repository.Pack$Metadata',
    'Manager': 'net.minecraft.server.packs.resources.MultiPackResourceManager',
    'Resource': 'net.minecraft.server.packs.resources.Resource',
    'Identifier': 'net.minecraft.resources.Identifier',
}


def matches(path, info):
    return path.is_file() and hashlib.sha1(path.read_bytes()).hexdigest() == info['sha1']


def fetch(info, target, existing=()):
    for path in (*existing, target):
        if matches(path, info):
            return path
    target.parent.mkdir(parents=True, exist_ok=True)
    print('Downloading', target.name, flush=True)
    with urllib.request.urlopen(info['url'], timeout=45) as response:
        data = response.read()
    if hashlib.sha1(data).hexdigest() != info['sha1']:
        raise ValueError('Downloaded hash mismatch: ' + info['url'])
    target.write_bytes(data)
    return target


def mapped_properties(meta, directory):
    aliases = dict(ALIASES)
    mapping = {}
    info = meta['downloads'].get('client_mappings')
    if info:
        text = fetch(info, directory / 'client-mappings.txt').read_text(encoding='utf-8')
        if '\nnet.minecraft.resources.Identifier -> ' not in text:
            aliases['Identifier'] = 'net.minecraft.resources.ResourceLocation'
        current = None
        for line in text.splitlines():
            if line and not line.startswith((' ', '#')) and ' -> ' in line:
                original, obfuscated = line[:-1].split(' -> ')
                current = original if original in aliases.values() else None
                if current:
                    mapping[current] = {'class': obfuscated, 'methods': {}, 'fields': {}}
            elif current and line.startswith(' ') and ' -> ' in line:
                left, obfuscated = line.strip().split(' -> ')
                if '(' in left:
                    match = re.search(r' ([^ :()]+)\(', left)
                    if match:
                        name = match.group(1)
                        mapping[current]['methods'].setdefault(name, set()).add(obfuscated)
                else:
                    mapping[current]['fields'][left.split()[-1]] = obfuscated
    lines = []
    for alias, original in aliases.items():
        entry = mapping.get(original, {'class': original, 'methods': {}, 'fields': {}})
        if info and original not in mapping:
            raise ValueError('Missing official class mapping: ' + original)
        lines.append(alias + '.class=' + entry['class'])
        for name, values in entry['methods'].items():
            lines.append(alias + '.method.' + name + '=' + ','.join(sorted(values)))
        for name, value in entry['fields'].items():
            lines.append(alias + '.field.' + name + '=' + value)
    target = directory / 'names.properties'
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return target


def dependencies(meta, mc):
    paths = []
    for library in meta['libraries']:
        artifact = library.get('downloads', {}).get('artifact')
        if not artifact or not artifact['path'].endswith('.jar'):
            continue
        # The pack reader uses Java classes only; platform-native classifiers are unnecessary.
        if 'natives-' in library['name']:
            continue
        coordinates = library['name'].split(':')
        if len(coordinates) > 3 and any(os_name in coordinates[3]
                                       for os_name in ('linux', 'osx', 'macos')):
            continue
        rules = library.get('rules', [])
        if rules:
            allowed = False
            for rule in rules:
                platform = rule.get('os', {}).get('name')
                if platform in (None, 'windows') and 'features' not in rule:
                    allowed = rule['action'] == 'allow'
            if not allowed:
                continue
        installed = mc / 'libraries' / artifact['path']
        paths.append(fetch(artifact, CACHE / 'libraries' / artifact['path'], (installed,)))
    return paths


def probe(version, meta, jar, libraries, names, major, minor):
    classpath = os.pathsep.join(map(str, (CACHE, jar, *libraries)))
    command = ['java', '-Djava.awt.headless=true', '-cp', classpath, 'local.copperpack.NativePackCheck',
               str(names), str(universal.ARTIFACT), str(major), str(minor)]
    run = subprocess.run(command, cwd=CACHE, capture_output=True, text=True,
                         encoding='utf-8', errors='replace', timeout=45)
    log = CACHE / version / (universal.ARTIFACT.stem + '-native-' + str(major) + '-' + str(minor) + '.log')
    log.write_text(run.stdout + '\n' + run.stderr, encoding='utf-8')
    if run.returncode:
        raise RuntimeError('Native check failed; see ' + str(log) + '\n' + run.stderr[-5000:])
    values = dict(line.removeprefix('NATIVE_').split('=', 1)
                  for line in run.stdout.splitlines() if line.startswith('NATIVE_'))
    return {'client_version': version, 'client_jar_sha1': meta['downloads']['client']['sha1'],
            'format': [major, minor], 'compatibility': values['COMPATIBILITY'],
            'selected_overlays': values['OVERLAYS'],
            'asset_count': int(values['ASSET_COUNT']),
            'effective_assets_sha256': values['ASSET_HASH']}


def verify_native(cache=None):
    global CACHE
    if cache:
        CACHE = cache.resolve()
    if not shutil.which('java') or not shutil.which('javac'):
        raise RuntimeError('Java 25+ JDK is required')
    CACHE.mkdir(parents=True, exist_ok=True)
    subprocess.run(['javac', '--release', '17', '-d', str(CACHE),
                    str(b.ROOT / 'tools/NativePackCheck.java')], check=True,
                   capture_output=True, text=True)
    record_path = b.ROOT / 'docs/build-verification.json'
    record = b.read_json(record_path)
    mc = Path(os.environ['APPDATA']) / '.minecraft' if 'APPDATA' in os.environ else Path.home() / '.minecraft'
    checks = []
    for version in b.VERSIONS:
        directory = CACHE / version
        directory.mkdir(exist_ok=True)
        meta = b.read_json(b.ROOT / 'source/minecraft' / ('minecraft-' + version + '-metadata.json'))
        jar = fetch(meta['downloads']['client'], directory / 'client.jar', (
            mc / 'versions' / version / (version + '.jar'),))
        with zipfile.ZipFile(jar) as zip_file:
            game = json.loads(zip_file.read('version.json'))
        if game['id'] != version or [game['pack_version']['resource_major'],
                                    game['pack_version']['resource_minor']] != b.FORMATS[version]:
            raise ValueError('Exact client identity mismatch')
        libraries = dependencies(meta, mc)
        names = mapped_properties(meta, directory)
        for artifact in record['artifacts']:
            target = next((row for row in artifact['checks'] if row['version'] == version), None)
            if target is None:
                continue
            universal.ARTIFACT = b.ROOT / 'dist' / artifact['filename']
            if b.digest(universal.ARTIFACT.read_bytes()) != artifact['sha256']:
                raise ValueError('Artifact changed after build')
            actual = probe(version, meta, jar, libraries, names, *target['format'])
            if (actual['compatibility'] != 'COMPATIBLE'
                    or actual['selected_overlays'] != '[' + ', '.join(target['selected_overlays']) + ']'
                    or actual['asset_count'] != target['asset_count']
                    or actual['effective_assets_sha256'] != target['effective_assets_sha256']):
                raise ValueError('Native reader differs from exact expected resource tree: ' + artifact['filename'])
            actual['artifact'] = artifact['filename']
            checks.append(actual)
        print(version + ': all 3 exact packs and all 3 combined packs parsed and resolved natively', flush=True)
    record['native_reader_checks'] = {'harness_sha256': b.digest((b.ROOT / 'tools/NativePackCheck.java').read_bytes()),
        'method': 'Exact official client JAR metadata parser and native MultiPackResourceManager; full byte tree comparison.',
        'minecraft_window_or_world_started': False, 'checks': checks}
    record_path.write_bytes(b.json_bytes(record))
    print(json.dumps({'native_checks_passed': len(checks), 'minecraft_window_or_world_started': False}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Offline exact-client metadata and overlay checks; no game launch.')
    parser.add_argument('--cache', type=Path, help='Optional existing external client JAR/library cache')
    args = parser.parse_args()
    verify_native(args.cache)
