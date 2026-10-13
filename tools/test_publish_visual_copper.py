"""Offline regression checks for publication safeguards; never authenticates."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import publish_visual_copper as publisher


COMMIT = "1" * 40


class FakeGithub:
    def __init__(self, release=None, tag=None):
        self.release = release
        self.tag = tag
        self.calls = []

    def json(self, method, endpoint, payload=None):
        self.calls.append((method, endpoint, payload))
        if endpoint == "/user":
            return {"login": "TQNL"}
        if endpoint == f"/repos/{publisher.REPOSITORY}":
            return {"full_name": publisher.REPOSITORY, "private": True,
                    "default_branch": "main", "permissions": {"push": True}}
        if "/git/commits/" in endpoint:
            return {"sha": COMMIT}
        if "/git/ref/tags/" in endpoint:
            if self.tag is None:
                raise publisher.GithubHTTPError(404, method, endpoint)
            return {"object": {"type": "commit", "sha": self.tag}}
        if method == "GET" and "/releases?" in endpoint:
            return [] if self.release is None else [self.release.copy()]
        if method == "POST" and endpoint.endswith("/releases"):
            self.release = dict(payload, id=123, assets=[],
                                upload_url="https://uploads.github.com/repos/example/releases/123/assets{?name,label}",
                                html_url="https://github.com/example/releases/tag/" + payload["tag_name"])
            return self.release.copy()
        if method == "PATCH" and endpoint.endswith("/releases/123"):
            self.release.update(payload)
            if not self.release["draft"]:
                self.tag = COMMIT
            return self.release.copy()
        raise AssertionError((method, endpoint, payload))

    def asset_hash(self, asset):
        return asset["digest"].removeprefix("sha256:")

    def upload(self, url, data):
        self.calls.append(("POST", url, None))
        name = parse_qs(urlparse(url).query)["name"][0]
        asset = {"id": len(self.release["assets"]) + 1, "name": name,
                 "size": len(data), "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                 "state": "uploaded"}
        self.release["assets"].append(asset)
        return asset


class Safeguards(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        entries = []
        for edition in ("16x", "32x", "64x"):
            name = "VisualWaxedCopperItems-" + edition + "-mc-1.21.9.zip"
            data = (edition + " reviewed content").encode()
            (root / name).write_bytes(data)
            entries.append({"name": name, "path": name,
                            "sha256": hashlib.sha256(data).hexdigest()})
        self.raw_plan = {"repository": publisher.REPOSITORY, "target_commitish": COMMIT,
                         "releases": [{"target": "1.21.9",
                                       "tag": "VisualWaxedCopperItems-mc-1.21.9",
                                       "name": "VisualWaxedCopperItems V3 - Minecraft 1.21.9",
                                       "body": "Reviewed description", "assets": entries}]}
        self.path = root / "release-plan.json"
        self.save_plan()
        self.plan = publisher.load_plan(self.path)
        self.planned = self.plan.releases[0]

    def tearDown(self):
        self.directory.cleanup()

    def save_plan(self):
        self.path.write_text(json.dumps(self.raw_plan), encoding="utf-8")

    def complete_remote(self, draft=True):
        return {"id": 123, "tag_name": self.planned.tag, "target_commitish": COMMIT,
                "name": self.planned.name, "body": self.planned.body,
                "draft": draft, "prerelease": False,
                "html_url": "https://github.com/example/releases/tag/test",
                "assets": [{"id": index, "name": asset.name, "size": asset.size,
                            "state": "uploaded", "digest": "sha256:" + asset.sha256}
                           for index, asset in enumerate(self.planned.assets)]}

    def run_quietly(self, api, mode):
        with contextlib.redirect_stdout(io.StringIO()):
            publisher.run(api, mode, self.plan)

    def test_read_only_transport_refuses_mutation(self):
        api = publisher.Github("test-placeholder")
        try:
            with self.assertRaisesRegex(publisher.PublicationError, "Read-only"):
                api._request("POST", "/must-never-be-sent", b"{}")
        finally:
            api.close()

    def test_check_sends_only_gets(self):
        api = FakeGithub()
        self.run_quietly(api, "check")
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_plan_rejects_changed_local_content(self):
        self.plan.releases[0].assets[0].path.write_bytes(b"changed")
        with self.assertRaisesRegex(publisher.PublicationError, "SHA256 differs"):
            publisher.load_plan(self.path)
        with self.assertRaisesRegex(publisher.PublicationError, "changed after"):
            self.plan.releases[0].assets[0].bytes()

    def test_remote_hash_conflict_prevents_all_mutations(self):
        remote = self.complete_remote()
        remote["assets"][1]["digest"] = "sha256:" + "f" * 64
        api = FakeGithub(remote)
        with self.assertRaisesRegex(publisher.PublicationError, "refusing replacement"):
            self.run_quietly(api, "stage")
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_later_group_conflict_prevents_earlier_draft_creation(self):
        earlier = publisher.Release(
            "1.21.10", "VisualWaxedCopperItems-mc-1.21.10",
            "VisualWaxedCopperItems V3 - Minecraft 1.21.10",
            self.planned.body, self.planned.assets)
        self.plan = publisher.Plan(COMMIT, (earlier, self.planned))
        remote = self.complete_remote()
        remote["assets"][1]["digest"] = "sha256:" + "f" * 64
        api = FakeGithub(remote)
        with self.assertRaisesRegex(publisher.PublicationError, "refusing replacement"):
            self.run_quietly(api, "stage")
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_different_tag_commit_prevents_all_mutations(self):
        api = FakeGithub(self.complete_remote(), "2" * 40)
        with self.assertRaisesRegex(publisher.PublicationError, "another commit"):
            self.run_quietly(api, "publish")
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_stage_uploads_three_assets_and_is_idempotent(self):
        api = FakeGithub()
        self.run_quietly(api, "stage")
        self.assertTrue(api.release["draft"])
        self.assertEqual(len(api.release["assets"]), 3)
        first_mutations = [call for call in api.calls if call[0] != "GET"]
        self.assertEqual(len(first_mutations), 4)
        api.calls.clear()
        self.run_quietly(api, "stage")
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_publish_requires_all_assets(self):
        remote = self.complete_remote()
        remote["assets"].pop()
        api = FakeGithub(remote)
        with self.assertRaisesRegex(publisher.PublicationError, "missing planned assets"):
            self.run_quietly(api, "publish")
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_publish_explicitly_finishes_and_is_idempotent(self):
        api = FakeGithub(self.complete_remote())
        self.run_quietly(api, "publish")
        self.assertFalse(api.release["draft"])
        self.assertEqual(api.tag, COMMIT)
        self.assertEqual(len([call for call in api.calls if call[0] != "GET"]), 1)
        api.calls.clear()
        self.run_quietly(api, "publish")
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_published_metadata_is_immutable(self):
        remote = self.complete_remote(draft=False)
        remote["body"] = "Existing published description"
        api = FakeGithub(remote, COMMIT)
        with self.assertRaisesRegex(publisher.PublicationError, "Published release metadata differs"):
            self.run_quietly(api, "stage")
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_redirect_strips_authorization(self):
        request = Request("https://api.github.com/example", headers={"Authorization": "Bearer test-placeholder"})
        redirected = publisher.SafeRedirects().redirect_request(
            request, None, 302, "Found", {},
            "https://release-assets.githubusercontent.com/example?opaque=signed-value")
        self.assertIsNone(redirected.get_header("Authorization"))
        with self.assertRaises(publisher.PublicationError):
            publisher.SafeRedirects().redirect_request(request, None, 302, "Found", {}, "https://example.net/asset")


if __name__ == "__main__":
    unittest.main()
