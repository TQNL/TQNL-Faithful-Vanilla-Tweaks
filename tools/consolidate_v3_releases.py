"""Publish legacy first, then replace the explicitly retired V3 release set.

--inspect is read-only. --apply implements the owner's approved consolidation.
Old IDs and tag commits are pinned to the recorded first publication; unrelated
releases/tags and newly recreated V3 IDs are never deleted.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote

import publish_visual_copper as p

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_COMMIT = 'c9bd0fc37a18954ff9da99e4a908b35219c6ae44'
LEGACY_BASE = '8514066836949be584ddb1fa68e88fcb2db352e3'
LEGACY_TAG = 'TQNL-Faithful-Vanilla-Tweaks-mc-1.21-to-1.21.8'
COMBINED_TAG = 'VisualWaxedCopperItems-mc-1.21.9-to-26.3'


def legacy_plan():
    info = json.loads((ROOT / 'visual-copper/docs/legacy-build-verification.json').read_text())
    path = ROOT / info['artifact']
    if hashlib.sha256(path.read_bytes()).hexdigest() != info['sha256']:
        raise p.PublicationError('Legacy artifact changed since verification')
    body = (
        'The original **full 32x Faithful / Vanilla Tweaks compilation**, packaged for **Minecraft 1.21â€“1.21.8**.\n\n'
        'Includes block and entity appearance tweaks, refined held utilities, painting and coloured axolotl bucket items, '
        'infested-block indicators, Visual Waxed Copper Items and the other add-ons listed in the included `report.txt`. '
        'These other tweaks remain in the repository root. CTM features need Continuity; CIT features need CIT Resewn or a compatible implementation.\n\n'
        'Built from the original repository snapshot `'+LEGACY_BASE+'`. Its base format 34 and populated overlays 42/46/53 '
        'show a combined-version design. This pre-1.21.9 release bounds metadata to formats 34â€“64, replacing the old oversized 7500 maximum. '
        'All 937 original files apart from `pack.mcmeta` are byte-identical. Dormant files for later items are retained; features apply where those items exist.\n\n'
        'Metadata/resource selection and ZIP integrity are verified; this is not a new in-game visual test of every included tweak. '
        'Use above the matching Faithful 32x base pack. The newer copper-only V3 download covers 1.21.9â€“26.3 separately.\n\n'
        'Credits:\nVanilla Tweaks: https://vanillatweaks.net/\n\n'
        'Faithful 32x and add-ons: **[Faithful Resource Pack](https://faithfulpack.net/)**. Original contributor credits are retained in `report.txt`; '
        'original Faithful license copies are included.\n\n'
        'Format references: [Minecraft 1.21](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21), '
        '[Minecraft 1.21.7](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-7), '
        '[Minecraft 1.21.8](https://www.minecraft.net/en-us/article/minecraft-java-edition-1-21-8). '
        'The official 1.21.8 client JAR confirms resource format 64.\n')
    asset = p.Asset(path.resolve(), path.name, info['sha256'], path.stat().st_size)
    release = p.Release('1.21-to-1.21.8', LEGACY_TAG,
                        'TQNL Faithful Vanilla Tweaks - Legacy 32x Compilation - Minecraft 1.21-1.21.8', body, (asset,))
    return p.Plan(LEGACY_BASE, (release,))


def old_receipt():
    return json.loads(subprocess.check_output(['git', '-C', str(ROOT), 'show',
        RECEIPT_COMMIT + ':visual-copper/docs/publication-verification.json']))


def retired_preflight(api, receipt, new_commit):
    rows = []
    for planned in receipt['releases']:
        if not planned['tag'].startswith('VisualWaxedCopperItems-mc-'):
            raise p.PublicationError('Historical receipt contains a tag outside V3 scope')
        remote = p.find_release(api, planned['tag'])
        commit = p.tag_commit(api, planned['tag'])
        if remote and remote['id'] == planned['id']:
            if commit != receipt['source_commit']:
                raise p.PublicationError('An old release tag changed unexpectedly')
            expected = {a['name']: a for a in planned['assets']}
            actual = {a['name']: a for a in remote['assets']}
            if set(actual) != set(expected) or any(api.asset_hash(actual[name]) != item['sha256'] for name, item in expected.items()):
                raise p.PublicationError('An old release asset set changed unexpectedly')
            state = 'retire original release and tag'
        elif remote:
            if planned['tag'] != COMBINED_TAG or commit not in (None, new_commit) or remote.get('target_commitish') != new_commit:
                raise p.PublicationError('A release tag belongs to an unexpected new publication')
            state = 'retain recreated combined release'
        elif commit not in (None, receipt['source_commit'], new_commit):
            raise p.PublicationError('Unexpected tag commit')
        else:
            state = 'original release already absent'
        rows.append({'tag': planned['tag'], 'original_id': planned['id'], 'state': state})
    return rows


def delete_originals(api, receipt, new_commit):
    deleted = []
    for planned in receipt['releases']:
        remote = p.find_release(api, planned['tag'])
        if remote and remote['id'] == planned['id']:
            if p.tag_commit(api, planned['tag']) != receipt['source_commit']:
                raise p.PublicationError('Original tag changed before deletion')
            with api._request('DELETE', f'/repos/{p.REPOSITORY}/releases/{planned["id"]}') as response:
                if response.status != 204:
                    raise p.PublicationError('Release deletion was not acknowledged')
            deleted.append({'id': planned['id'], 'tag': planned['tag']})
            print('Deleted previous V3 release: ' + planned['tag'], flush=True)
        commit = p.tag_commit(api, planned['tag'])
        if commit == receipt['source_commit']:
            with api._request('DELETE', f'/repos/{p.REPOSITORY}/git/refs/tags/{quote(planned["tag"], safe="")}') as response:
                if response.status != 204:
                    raise p.PublicationError('Old tag deletion was not acknowledged')
        elif commit not in (None, new_commit):
            raise p.PublicationError('Refusing to delete a changed tag')
    return deleted


def main(plan_path, apply):
    combined = p.load_plan(plan_path)
    if len(combined.releases) != 1 or combined.releases[0].tag != COMBINED_TAG:
        raise p.PublicationError('Only the combined V3 release may be published')
    legacy = legacy_plan()
    receipt = old_receipt()
    api = None
    try:
        _, token = p.existing_credential()
        api = p.Github(token, allow_mutations=apply)
        del token
        if api.json('GET', '/user')['login'] != p.ACCOUNT:
            raise p.PublicationError('Unexpected authenticated account')
        if api.json('GET', f'/repos/{p.REPOSITORY}/git/commits/{combined.commit}')['sha'] != combined.commit:
            raise p.PublicationError('Approved new source commit is not pushed')
        rows = retired_preflight(api, receipt, combined.commit)
        print(json.dumps({'legacy_asset': legacy.releases[0].assets[0].name, 'retirement_plan': rows}, indent=2), flush=True)
        if not apply:
            return
        # Publish and verify the requested older compilation before the new V3.
        p.run(api, 'stage', legacy)
        p.run(api, 'publish', legacy)
        retired_preflight(api, receipt, combined.commit)
        deleted = delete_originals(api, receipt, combined.commit)
        p.run(api, 'stage', combined)
        p.run(api, 'publish', combined)
        current = api.json('GET', f'/repos/{p.REPOSITORY}/releases?per_page=100')
        if {item['tag_name'] for item in current} != {LEGACY_TAG, COMBINED_TAG} or any(item['draft'] for item in current):
            raise p.PublicationError('Final release set is not the requested two published releases')
        legacy_remote, _ = p.inspect_release(api, legacy, legacy.releases[0], True)
        latest_remote, _ = p.inspect_release(api, combined, combined.releases[0], True)
        if legacy_remote['published_at'] > latest_remote['published_at']:
            raise p.PublicationError('Legacy compilation was not published first')
        record = {'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'repository': p.REPOSITORY,
                  'approved_source_commit': combined.commit, 'deleted_previous_v3_releases': deleted,
                  'legacy_release': {'url': legacy_remote['html_url'], 'tag': LEGACY_TAG, 'published_at': legacy_remote['published_at'],
                                     'sha256': legacy.releases[0].assets[0].sha256},
                  'combined_release': {'url': latest_remote['html_url'], 'tag': COMBINED_TAG, 'published_at': latest_remote['published_at'],
                                        'assets': [asset.name for asset in combined.releases[0].assets]},
                  'published_release_count': 2, 'individual_v3_releases': 0}
        (ROOT / 'visual-copper/docs/consolidated-publication.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(record, indent=2), flush=True)
    finally:
        if api:
            api.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--inspect', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        main(args.plan, args.apply)
    except p.PublicationError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print('ERROR: Release consolidation failed; completed operations can be inspected before resuming.', file=sys.stderr)
        raise SystemExit(1)
