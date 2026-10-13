#!/usr/bin/env python3
"""Publish the reviewed VisualWaxedCopperItems plan using existing Git auth.

Read only: python tools/publish_visual_copper.py --check [--plan PLAN.json]
Stage drafts: python tools/publish_visual_copper.py --stage --plan PLAN.json
Publish verified drafts: python tools/publish_visual_copper.py --publish --plan PLAN.json

Plan schema (paths are relative to the plan, unless absolute):
{
  "repository": "TQNL/TQNL-Faithful-Vanilla-Tweaks",
  "target_commitish": "<40-character commit SHA already pushed to GitHub>",
  "releases": [{
    "target": "1.21.9",
    "tag": "VisualWaxedCopperItems-mc-1.21.9",
    "name": "VisualWaxedCopperItems V3 - Minecraft 1.21.9",
    "body": "Reviewed release description and attribution.",
    "assets": [
      {"path": "pack-16x.zip", "name": "pack-16x.zip", "sha256": "<SHA256>"},
      {"path": "pack-32x.zip", "name": "pack-32x.zip", "sha256": "<SHA256>"},
      {"path": "pack-64x.zip", "name": "pack-64x.zip", "sha256": "<SHA256>"}
    ]
  }]
}

--check never sends a mutating request. --stage creates or updates drafts and
uploads missing assets. --publish only publishes drafts whose metadata, tag
commit, complete asset names, sizes, and SHA256 hashes match the plan. An
existing same-name asset with different bytes is always an error; this tool
never deletes or replaces an asset. A published release is never edited.
Credentials travel only through subprocess pipes and API headers in process
memory. They are never printed, persisted, or passed in command arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


REPOSITORY = "TQNL/TQNL-Faithful-Vanilla-Tweaks"
ACCOUNT = "TQNL"
API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_ASSET_BYTES = 512 * 1024 * 1024


class PublicationError(Exception):
    """A safe error message that does not contain authentication data."""


class GithubHTTPError(PublicationError):
    def __init__(self, status: int, method: str, endpoint: str):
        self.status = status
        super().__init__(f"GitHub returned HTTP {status} for {method} {endpoint}.")


class SafeRedirects(HTTPRedirectHandler):
    """GitHub asset redirects must not carry an Authorization header."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urlparse(newurl)
        host = destination.hostname or ""
        if destination.scheme != "https" or not (
            host == "github.com"
            or host.endswith(".github.com")
            or host.endswith(".githubusercontent.com")
            or host.endswith(".blob.core.windows.net")
        ):
            raise PublicationError("GitHub returned an unsupported asset redirect.")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header("Authorization")
        return redirected


def existing_credential() -> tuple[str, str]:
    """Ask Git's configured helper through private stdin/stdout pipes."""
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    try:
        result = subprocess.run(
            ["git", "-c", "credential.interactive=false", "credential", "fill"],
            input=b"protocol=https\nhost=github.com\nusername=TQNL\n\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise PublicationError("Could not read existing authentication from Git's helper.") from None
    if result.returncode:
        # Helper output may include credential details. Do not echo it.
        raise PublicationError(
            f"Git's credential helper could not authenticate (exit {result.returncode})."
        )
    output = bytearray(result.stdout)
    result.stdout = b""
    result.stderr = b""
    values: dict[str, str] = {}
    try:
        for line in output.splitlines():
            key, separator, value = line.partition(b"=")
            if separator and key in (b"username", b"password"):
                values[key.decode("ascii")] = value.decode("utf-8")
        login = values.get("username", "")
        token = values.get("password", "")
        if not login or not token:
            raise PublicationError("Git's credential helper returned no usable GitHub credential.")
        return login, token
    finally:
        output[:] = b"\x00" * len(output)
        values.clear()


class Github:
    def __init__(self, token: str, allow_mutations: bool = False):
        self._token = token
        self._allow_mutations = allow_mutations
        self._opener = build_opener(SafeRedirects())

    def close(self):
        # Python cannot promise erasure of immutable strings; drop references
        # as soon as the bounded operation is done. No secret reaches disk.
        self._token = ""
        self._opener = None

    def _request(self, method: str, endpoint: str, data=None, content_type=None):
        if method not in ("GET", "HEAD") and not self._allow_mutations:
            raise PublicationError("Read-only mode refuses a mutating GitHub request.")
        url = endpoint if endpoint.startswith("https://") else API_ROOT + endpoint
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in (
            "api.github.com", "uploads.github.com"
        ):
            raise PublicationError("Refusing an unsupported GitHub API endpoint.")
        headers = {
            "Authorization": "Bearer " + self._token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "TQNL-VisualWaxedCopperItems-Publication",
        }
        if method in ("GET", "HEAD"):
            # Release lists and asset metadata may otherwise lag a completed
            # mutation. Every safety decision requires a fresh authenticated
            # read, including same-process staging and publication readbacks.
            headers["Cache-Control"] = "no-cache, no-store"
            headers["Pragma"] = "no-cache"
        if content_type:
            headers["Content-Type"] = content_type
        if data is not None:
            headers["Content-Length"] = str(len(data))
        request = Request(url, data=data, headers=headers, method=method)
        try:
            return self._opener.open(request, timeout=90)
        except HTTPError as error:
            status = error.code
            error.close()
            # Never include request headers, response bodies, or signed URLs.
            safe_endpoint = parsed.path
            raise GithubHTTPError(status, method, safe_endpoint) from None
        except (URLError, OSError):
            raise PublicationError("The GitHub request failed before completion.") from None

    def json(self, method: str, endpoint: str, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        with self._request(method, endpoint, data, "application/json" if data else None) as response:
            raw = response.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise PublicationError("GitHub JSON response exceeded the safe size limit.")
        try:
            return json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            raise PublicationError("GitHub returned an invalid JSON response.") from None

    def upload(self, url: str, data: bytes):
        with self._request("POST", url, data, "application/zip") as response:
            raw = response.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise PublicationError("GitHub upload response exceeded the safe size limit.")
        try:
            return json.loads(raw)
        except (UnicodeError, json.JSONDecodeError):
            raise PublicationError("GitHub returned an invalid upload response.") from None

    def asset_hash(self, asset: dict) -> str:
        digest = asset.get("digest") or ""
        if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            return digest[7:].lower()
        endpoint = f"/repos/{REPOSITORY}/releases/assets/{asset['id']}"
        request = Request(API_ROOT + endpoint, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/octet-stream",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "TQNL-VisualWaxedCopperItems-Publication",
        })
        try:
            with self._opener.open(request, timeout=90) as response:
                digest_object = hashlib.sha256()
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_ASSET_BYTES:
                        raise PublicationError("Remote asset exceeded the safe size limit.")
                    digest_object.update(chunk)
            if total != asset["size"]:
                raise PublicationError(f"Remote asset size changed: {asset['name']}.")
            return digest_object.hexdigest()
        except HTTPError as error:
            status = error.code
            error.close()
            raise GithubHTTPError(status, "GET", endpoint) from None
        except (URLError, OSError):
            raise PublicationError("The GitHub asset verification request failed.") from None


@dataclass(frozen=True)
class Asset:
    path: Path
    name: str
    sha256: str
    size: int

    def bytes(self) -> bytes:
        data = self.path.read_bytes()
        if len(data) != self.size or hashlib.sha256(data).hexdigest() != self.sha256:
            raise PublicationError(f"Local asset changed after plan validation: {self.name}.")
        return data


@dataclass(frozen=True)
class Release:
    target: str
    tag: str
    name: str
    body: str
    assets: tuple[Asset, ...]


@dataclass(frozen=True)
class Plan:
    commit: str
    releases: tuple[Release, ...]


def load_plan(path: Path) -> Plan:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise PublicationError("Could not read the release plan JSON.") from None
    if not isinstance(raw, dict) or raw.get("repository") != REPOSITORY:
        raise PublicationError(f"The plan must target {REPOSITORY}.")
    commit = raw.get("target_commitish", "")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise PublicationError("target_commitish must be an exact 40-character Git commit SHA.")
    groups = raw.get("releases")
    if not isinstance(groups, list) or not groups:
        raise PublicationError("The plan must contain release groups.")
    releases = []
    tags = set()
    for group in groups:
        if not isinstance(group, dict):
            raise PublicationError("Every release group must be a JSON object.")
        target = group.get("target", "")
        if not isinstance(target, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", target):
            raise PublicationError("Release target has unsupported characters.")
        tag = "VisualWaxedCopperItems-mc-" + target
        name = "VisualWaxedCopperItems V3 - Minecraft " + target
        if group.get("tag") != tag or group.get("name") != name:
            raise PublicationError(f"Release tag/title does not match the established family format: {target}.")
        if tag in tags:
            raise PublicationError(f"Duplicate release tag in plan: {tag}.")
        tags.add(tag)
        body = group.get("body")
        if not isinstance(body, str) or not body.strip():
            raise PublicationError(f"Release body is empty: {tag}.")
        entries = group.get("assets")
        if not isinstance(entries, list) or len(entries) != 3:
            raise PublicationError(f"Exactly three edition ZIP assets are required: {tag}.")
        assets = []
        names = set()
        editions = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise PublicationError(f"Asset plan entry is invalid: {tag}.")
            asset_name = entry.get("name", "")
            if not isinstance(asset_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.zip", asset_name):
                raise PublicationError(f"Asset name must be a plain ZIP filename: {tag}.")
            if asset_name in names:
                raise PublicationError(f"Duplicate asset filename: {asset_name}.")
            names.add(asset_name)
            edition = re.findall(r"(?<!\d)(?:16|32|64)x(?!\d)", asset_name, re.IGNORECASE)
            if len(edition) != 1:
                raise PublicationError(f"Asset filename must identify one edition: {asset_name}.")
            editions.add(edition[0].lower())
            expected_hash = entry.get("sha256", "")
            if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
                raise PublicationError(f"Plan SHA256 is invalid: {asset_name}.")
            source_path = entry.get("path")
            if not isinstance(source_path, str) or not source_path:
                raise PublicationError(f"Plan asset path is invalid: {asset_name}.")
            source = Path(source_path)
            if not source.is_absolute():
                source = path.resolve().parent / source
            try:
                size = source.stat().st_size
                if not source.is_file() or not 0 < size <= MAX_ASSET_BYTES:
                    raise PublicationError(f"Local asset is missing or too large: {asset_name}.")
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
            except OSError:
                raise PublicationError(f"Could not read local asset: {asset_name}.") from None
            if digest != expected_hash.lower():
                raise PublicationError(f"Local asset SHA256 differs from plan: {asset_name}.")
            assets.append(Asset(source.resolve(), asset_name, digest, size))
        if editions != {"16x", "32x", "64x"}:
            raise PublicationError(f"Release must contain 16x, 32x, and 64x editions: {tag}.")
        releases.append(Release(target, tag, name, body, tuple(assets)))
    return Plan(commit.lower(), tuple(releases))


def tag_commit(api: Github, tag: str) -> str | None:
    try:
        reference = api.json("GET", f"/repos/{REPOSITORY}/git/ref/tags/{quote(tag, safe='')}")
    except GithubHTTPError as error:
        if error.status == 404:
            return None
        raise
    obj = reference["object"]
    for _ in range(8):
        if obj["type"] == "commit":
            return obj["sha"].lower()
        if obj["type"] != "tag":
            break
        obj = api.json("GET", f"/repos/{REPOSITORY}/git/tags/{obj['sha']}")["object"]
    raise PublicationError(f"Release tag does not resolve to a commit: {tag}.")


def find_release(api: Github, tag: str) -> dict | None:
    try:
        remote = api.json("GET", f"/repos/{REPOSITORY}/releases/tags/{quote(tag, safe='')}")
        if remote.get("tag_name") != tag:
            raise PublicationError(f"GitHub returned another release tag: {tag}.")
        return remote
    except GithubHTTPError as error:
        if error.status != 404:
            raise
    # GitHub's by-tag endpoint returns 404 for an unpublished draft. The
    # authenticated list exposes drafts even before their tag ref exists.
    found = []
    for page in range(1, 100):
        items = api.json("GET", f"/repos/{REPOSITORY}/releases?per_page=100&page={page}")
        found.extend(item for item in items if item["tag_name"] == tag)
        if len(items) < 100:
            break
    else:
        raise PublicationError("Repository release enumeration exceeded the safe page limit.")
    if len(found) > 1:
        raise PublicationError(f"Several releases use the same tag: {tag}.")
    return found[0] if found else None


def metadata_matches(remote: dict, planned: Release) -> bool:
    return (
        remote.get("name") == planned.name
        and (remote.get("body") or "").replace("\r\n", "\n") == planned.body.replace("\r\n", "\n")
        and remote.get("prerelease") is False
    )


def inspect_release(api: Github, plan: Plan, release: Release, require_complete=False, release_id=None):
    commit = tag_commit(api, release.tag)
    if commit is not None and commit != plan.commit:
        raise PublicationError(f"Existing tag points to another commit: {release.tag}.")
    if release_id is None:
        remote = find_release(api, release.tag)
    else:
        # A successful create/update response already supplies the stable ID.
        # Re-read that resource directly rather than relying on immediate
        # visibility of a new draft in a potentially lagging release list.
        remote = api.json("GET", f"/repos/{REPOSITORY}/releases/{int(release_id)}")
    if remote is None:
        if require_complete:
            raise PublicationError(f"Release has not been staged: {release.tag}.")
        return None, []
    if remote.get("tag_name") != release.tag:
        raise PublicationError(f"Release ID points to another tag: {release.tag}.")
    if not remote.get("draft") and not metadata_matches(remote, release):
        raise PublicationError(f"Published release metadata differs from plan: {release.tag}.")
    if remote.get("draft") and commit is None and remote.get("target_commitish", "").lower() != plan.commit:
        raise PublicationError(f"Draft targets another commit: {release.tag}.")
    if require_complete and not metadata_matches(remote, release):
        raise PublicationError(f"Release metadata is not ready to publish: {release.tag}.")
    if not remote.get("draft") and commit is None:
        raise PublicationError(f"Published release tag is missing: {release.tag}.")
    remote_assets = remote.get("assets", [])
    names = [asset["name"] for asset in remote_assets]
    if len(names) != len(set(names)):
        raise PublicationError(f"Duplicate remote asset names: {release.tag}.")
    by_name = {asset["name"]: asset for asset in remote_assets}
    expected_names = {asset.name for asset in release.assets}
    extras = set(by_name) - expected_names
    if extras:
        raise PublicationError(f"Unexpected remote assets on {release.tag}: {', '.join(sorted(extras))}.")
    missing = []
    for asset in release.assets:
        existing = by_name.get(asset.name)
        if existing is None:
            missing.append(asset)
            continue
        if existing.get("state") != "uploaded" or existing.get("size") != asset.size:
            raise PublicationError(f"Existing asset differs from plan: {asset.name}.")
        if api.asset_hash(existing) != asset.sha256:
            raise PublicationError(f"Existing asset SHA256 differs; refusing replacement: {asset.name}.")
    if missing and (require_complete or not remote.get("draft")):
        raise PublicationError(f"Release is missing planned assets: {release.tag}.")
    return remote, missing


def run(api: Github, mode: str, plan: Plan | None):
    user = api.json("GET", "/user")
    if user.get("login", "").lower() != ACCOUNT.lower():
        raise PublicationError("Existing GitHub credential belongs to an unexpected account.")
    repository = api.json("GET", f"/repos/{REPOSITORY}")
    permissions = repository.get("permissions") or {}
    summary = {
        "mode": mode,
        "login": user["login"],
        "repository": repository["full_name"],
        "private": repository["private"],
        "default_branch": repository["default_branch"],
        "permissions": {name: bool(permissions.get(name)) for name in ("pull", "push", "admin")},
    }
    print(json.dumps(summary, indent=2))
    if mode != "check" and not permissions.get("push"):
        raise PublicationError("The existing GitHub account has no push permission for this repository.")
    if plan is None:
        items = api.json("GET", f"/repos/{REPOSITORY}/releases?per_page=100")
        print(json.dumps({"releases": [{
            "id": item["id"], "tag": item["tag_name"], "name": item["name"],
            "draft": item["draft"], "assets": [a["name"] for a in item.get("assets", [])]
        } for item in items]}, indent=2))
        return
    pushed = api.json("GET", f"/repos/{REPOSITORY}/git/commits/{plan.commit}")
    if pushed.get("sha", "").lower() != plan.commit:
        raise PublicationError("GitHub does not contain the plan's exact commit.")
    # Preflight every group before creating or changing anything.
    for release in plan.releases:
        remote, missing = inspect_release(api, plan, release, mode == "publish")
        print(json.dumps({"tag": release.tag, "state": (
            "missing" if remote is None else "draft" if remote["draft"] else "published"
        ), "missing_assets": [asset.name for asset in missing]}, indent=2))
    if mode == "check":
        print("Read-only release plan check passed.")
        return
    if mode == "stage":
        for release in plan.releases:
            remote, _ = inspect_release(api, plan, release)
            if remote is None:
                remote = api.json("POST", f"/repos/{REPOSITORY}/releases", {
                    "tag_name": release.tag, "target_commitish": plan.commit,
                    "name": release.name, "body": release.body, "draft": True,
                    "prerelease": False, "make_latest": "false",
                })
                print(f"Created draft: {release.tag}")
            elif not remote["draft"]:
                print(f"Already published and verified: {release.tag}")
                continue
            elif not metadata_matches(remote, release):
                remote = api.json("PATCH", f"/repos/{REPOSITORY}/releases/{remote['id']}", {
                    "name": release.name, "body": release.body, "draft": True,
                    "prerelease": False, "make_latest": "false",
                })
                print(f"Updated draft metadata: {release.tag}")
            release_id = remote["id"]
            # Re-read after metadata operations and before each asset operation.
            for asset in release.assets:
                current, missing = inspect_release(api, plan, release, release_id=release_id)
                if not current or not current["draft"]:
                    raise PublicationError(f"Release draft state changed: {release.tag}.")
                if asset.name not in {item.name for item in missing}:
                    continue
                data = asset.bytes()
                upload_url = current["upload_url"].split("{", 1)[0]
                uploaded = api.upload(upload_url + "?" + urlencode({"name": asset.name}), data)
                del data
                if uploaded.get("name") != asset.name or uploaded.get("size") != asset.size:
                    raise PublicationError(f"Uploaded asset metadata differs: {asset.name}.")
                if api.asset_hash(uploaded) != asset.sha256:
                    raise PublicationError(f"Uploaded asset SHA256 differs: {asset.name}.")
                print(f"Uploaded and verified: {asset.name}")
            inspect_release(api, plan, release, require_complete=True, release_id=release_id)
        print("All planned draft releases and assets are staged and verified.")
        return
    for release in plan.releases:
        remote, _ = inspect_release(api, plan, release, require_complete=True)
        if remote["draft"]:
            api.json("PATCH", f"/repos/{REPOSITORY}/releases/{remote['id']}", {
                "draft": False,
                "make_latest": "true" if release.target == "1.21.9-to-26.3" else "false",
            })
        final, _ = inspect_release(api, plan, release, require_complete=True, release_id=remote["id"])
        if final["draft"]:
            raise PublicationError(f"Release publication could not be verified: {release.tag}.")
        print(f"Published and verified: {final['html_url']}")
    print("All planned releases are published and verified.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check", action="store_true", help="Read-only authentication/release checks")
    modes.add_argument("--stage", action="store_true", help="Create/update drafts and upload missing assets")
    modes.add_argument("--publish", action="store_true", help="Explicitly publish fully verified drafts")
    parser.add_argument("--plan", type=Path, help="Reviewed release plan JSON")
    args = parser.parse_args()
    mode = "check" if args.check else "stage" if args.stage else "publish"
    if mode != "check" and args.plan is None:
        parser.error("--stage and --publish require --plan")
    api = None
    try:
        plan = load_plan(args.plan) if args.plan else None
        _, token = existing_credential()
        api = Github(token, allow_mutations=mode != "check")
        del token
        run(api, mode, plan)
        return 0
    except PublicationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except Exception:
        # Suppress raw exceptions/tracebacks because private authentication and
        # signed asset URLs may be present in local variables or library errors.
        print("ERROR: Publication failed while validating local or GitHub data.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled; any completed draft operations can be resumed with the same plan.", file=sys.stderr)
        return 130
    finally:
        if api is not None:
            api.close()


if __name__ == "__main__":
    raise SystemExit(main())
