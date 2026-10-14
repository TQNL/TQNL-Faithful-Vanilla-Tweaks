"""Build the full merged compilation from root pack files, without game launch.

The released ZIP retains the installed archive packaging. Regenerating produces
a deterministic ZIP with equivalent pack files; archive metadata may differ.
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'visual-copper/tools'))
import build as b


def main(output):
    reference = ROOT / 'dist/TQNL Faithful Vanilla Tweaks.zip'
    with zipfile.ZipFile(reference) as archive:
        expected = {i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()}
    files = {}
    for name, data in expected.items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError('Unsafe pack path')
        actual = path.read_bytes()
        if actual != data:
            raise ValueError('Pack source differs from approved compilation: ' + name)
        files[name] = actual
    sha = b.archive(files, output)
    print(json.dumps({'artifact': output.name, 'files': len(files), 'sha256': sha,
                      'resource_bytes_match_released_pack': True,
                      'minecraft_started': False}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.work/TQNL Faithful Vanilla Tweaks.zip')
    main(parser.parse_args().output)
