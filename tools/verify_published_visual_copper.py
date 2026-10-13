"""Read back all published release metadata/digests and three real downloads."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import publish_visual_copper as p


def verify(plan_path, output):
    plan = p.load_plan(plan_path)
    api = None
    try:
        _, token = p.existing_credential()
        api = p.Github(token, allow_mutations=False)
        del token
        if api.json('GET', '/user')['login'] != p.ACCOUNT:
            raise p.PublicationError('Unexpected authenticated account')
        rows, downloads = [], []
        for release in plan.releases:
            remote, _ = p.inspect_release(api, plan, release, require_complete=True)
            if remote['draft']:
                raise p.PublicationError('A planned release is still a draft')
            assets = {asset['name']: asset for asset in remote['assets']}
            rows.append({'tag': release.tag, 'url': remote['html_url'], 'id': remote['id'],
                         'source_commit': p.tag_commit(api, release.tag), 'draft': False,
                         'assets': [{'name': asset.name, 'sha256': asset.sha256,
                                     'bytes': asset.size, 'url': assets[asset.name]['browser_download_url']}
                                    for asset in release.assets]})
            if release.target == '1.21.9-to-26.3':
                for asset in release.assets:
                    # Force a streamed asset download rather than relying on
                    # the server's digest field for these representative ZIPs.
                    digest = api.asset_hash(dict(assets[asset.name], digest=None))
                    if digest != asset.sha256:
                        raise p.PublicationError('Downloaded combined ZIP differs from local bytes')
                    downloads.append({'name': asset.name, 'sha256': digest, 'download_readback_matches': True})
        latest = api.json('GET', f'/repos/{p.REPOSITORY}/releases/latest')
        if latest['tag_name'] != 'VisualWaxedCopperItems-mc-1.21.9-to-26.3':
            raise p.PublicationError('The combined release is not marked latest')
        report = {'verified_at_utc': datetime.now(timezone.utc).isoformat(),
                  'repository': p.REPOSITORY, 'source_commit': plan.commit,
                  'release_count': len(rows), 'asset_count': sum(len(row['assets']) for row in rows),
                  'releases': rows, 'combined_download_readback': downloads,
                  'latest_release': latest['html_url'], 'minecraft_started': False}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'published_releases_verified': len(rows), 'assets_verified': report['asset_count'],
                          'actual_combined_downloads_verified': len(downloads),
                          'latest_release': report['latest_release']}, indent=2))
    finally:
        if api:
            api.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        verify(args.plan, args.output)
    except p.PublicationError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print('ERROR: Published release readback could not be verified.', file=sys.stderr)
        raise SystemExit(1)
