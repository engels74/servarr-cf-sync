"""Offline behavior checks; all state is temporary and external HTTP is forbidden."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import Mock, patch

import requests
import semver
import sync_script as sync

ROOT = Path(__file__).resolve().parents[1]
FORMAT = {
    "name": "Fixture",
    "cfSync_version": "1.2.3",
    "cfSync_score": 5,
    "cfSync_radarr": True,
    "cfSync_sonarr": False,
    "includeCustomFormatWhenRenaming": False,
    "specifications": [
        {
            "name": "Title",
            "implementation": "ReleaseTitleSpecification",
            "negate": False,
            "required": False,
            "fields": {"value": "fixture"},
        }
    ],
}


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        previous = os.getcwd()
        os.chdir(self.temporary.name)
        self.addCleanup(os.chdir, previous)
        self.allowed = None
        original = requests.Session.request

        def isolated(session, method, url, **kwargs):
            if self.allowed is None or not url.startswith(self.allowed + "/"):
                raise AssertionError("Unexpected external HTTP in unit fixture")
            return original(session, method, url, timeout=5, **kwargs)

        guard = patch.object(requests.Session, "request", isolated)
        guard.start()
        self.addCleanup(guard.stop)
        Path("custom_formats").mkdir()
        self.syncer = sync.CustomFormatSyncer("custom_formats")

    def test_explicit_instances_override_app_flags(self):
        data = {**FORMAT, "cfSync_instances": ["003", "Radarr_002"]}
        for name in ["Radarr_003", "Sonarr_003", "Radarr_002"]:
            self.assertTrue(self.syncer.should_sync_to_instance(data, name))
        for name in ["Radarr_001", "Sonarr_002"]:
            self.assertFalse(self.syncer.should_sync_to_instance(data, name))
        self.assertTrue(self.syncer.should_sync_to_instance(FORMAT, "Radarr_001"))
        self.assertFalse(self.syncer.should_sync_to_instance(FORMAT, "Sonarr_001"))

    def test_wire_payload_strips_sync_metadata_and_normalizes_fields(self):
        client = Mock(spec=sync.APIClient)
        client.update_custom_format.return_value = {"id": 7, "name": "Fixture"}
        payload = self.syncer.prepare_format_for_sync(deepcopy(FORMAT))
        self.syncer.sync_format(client, [], payload)
        sent = client.update_custom_format.call_args.args[0]
        self.assertEqual(set(sent), {"name", "includeCustomFormatWhenRenaming", "specifications"})
        self.assertEqual(
            sent["specifications"][0]["fields"], [{"name": "value", "value": "fixture"}]
        )

    def test_existing_identical_format_does_not_write(self):
        client = Mock(spec=sync.APIClient)
        payload = {"name": "Fixture", "includeCustomFormatWhenRenaming": False}
        existing = {**payload, "id": 7}
        self.assertEqual(self.syncer.sync_format(client, [existing], payload), existing)
        client.update_custom_format.assert_not_called()

    def test_score_updates_matching_entries_only(self):
        client = Mock(spec=sync.APIClient)
        client.get_quality_profiles.return_value = [
            {
                "id": 1,
                "name": "First",
                "formatItems": [{"format": 7, "score": 0}, {"format": 8, "score": 2}],
            },
            {"id": 2, "name": "Second", "formatItems": []},
        ]
        client.update_quality_profile.side_effect = lambda value: value
        self.syncer.sync_format_score(client, {"id": 7, "name": "Fixture"}, 5)
        client.update_quality_profile.assert_called_once()
        self.assertEqual(
            client.update_quality_profile.call_args.args[0]["formatItems"],
            [{"format": 7, "score": 5}, {"format": 8, "score": 2}],
        )

    def test_version_round_trip_and_cleanup(self):
        version = semver.VersionInfo.parse("1.2.3")
        self.syncer.version_manager.update_version("fixture.json", version)
        manager = sync.VersionManager()
        self.assertEqual(manager.versions, {"fixture.json": version})
        manager.cleanup_versions([])
        self.assertEqual(json.loads(Path("version.json").read_text()), {})

    def test_template_never_calls_an_instance(self):
        Path("custom_formats/_template.json").write_text(json.dumps(FORMAT))
        with patch.object(sync, "APIClient") as client:
            self.syncer.sync_custom_formats([("Radarr_001", "https://example.invalid", "fixture")])
        client.assert_not_called()
        self.assertEqual(self.syncer.version_manager.versions, {})

    def test_instance_discovery_stops_at_the_first_missing_pair(self):
        with patch.dict(
            os.environ,
            {
                "RADARR_001_URL": "https://one.invalid",
                "RADARR_001_API_KEY": "fixture",
                "RADARR_003_URL": "https://three.invalid",
                "RADARR_003_API_KEY": "fixture",
            },
            clear=True,
        ):
            with patch.object(sync.CustomFormatSyncer, "sync_custom_formats") as run:
                sync.main()
        run.assert_called_once_with([("Radarr_001", "https://one.invalid", "fixture")])

    def test_requests_transport_paths_auth_and_json(self):
        recorded = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def respond(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                body = json.loads(raw) if raw else None
                recorded.append((self.command, self.path, self.headers.get("X-Api-Key"), body))
                result = (
                    [{"id": 7, "name": "Fixture"}] if self.command == "GET" else {"id": 7, **body}
                )
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())

            do_GET = respond
            do_POST = respond
            do_PUT = respond

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            self.allowed = f"http://127.0.0.1:{server.server_port}"
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = sync.APIClient(self.allowed, "public-fixture-key")
                self.assertEqual(client.get_custom_formats()[0]["id"], 7)
                client.get_quality_profiles()
                client.update_custom_format(sync.FormatDict(name="Fixture"))
                client.update_custom_format(sync.FormatDict(id=7, name="Fixture"))
                client.update_quality_profile({"id": 3, "name": "Quality", "formatItems": []})
                client.session.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
        self.assertEqual(
            [(r[0], r[1]) for r in recorded],
            [
                ("GET", "/api/v3/customformat"),
                ("GET", "/api/v3/qualityprofile"),
                ("POST", "/api/v3/customformat"),
                ("PUT", "/api/v3/customformat/7"),
                ("PUT", "/api/v3/qualityprofile/3"),
            ],
        )
        self.assertTrue(all(r[2] == "public-fixture-key" for r in recorded))
        self.assertEqual(recorded[2][3], {"name": "Fixture"})

    def test_repository_formats_and_generated_versions_are_valid(self):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                self.assertNotIn(key, result, f"Duplicate JSON key: {key}")
                result[key] = value
            return result

        files = list((ROOT / "custom_formats").glob("*.json"))
        self.assertTrue(files)
        names = set()
        for file in files:
            data = json.loads(file.read_text(), object_pairs_hook=unique)
            self.assertTrue(data["name"])
            self.assertNotIn(data["name"], names)
            names.add(data["name"])
            semver.VersionInfo.parse(data["cfSync_version"])
            self.assertIs(type(data["cfSync_score"]), int)
            for spec in data["specifications"]:
                self.assertTrue(spec["name"] and spec["implementation"])
                self.assertIs(type(spec["negate"]), bool)
                self.assertIs(type(spec["required"]), bool)
                self.assertIsInstance(spec["fields"], dict)
                self.assertIsInstance(spec["fields"]["value"], str)
        for version in json.loads(
            (ROOT / "version.json").read_text(), object_pairs_hook=unique
        ).values():
            semver.VersionInfo.parse(version)


if __name__ == "__main__":
    unittest.main()
