"""Mock integration tests for tap-ga360 stream discovery.

Verifies that the catalog produced by discover() contains correct stream
metadata, primary keys, replication keys, and schema properties.
No real BigQuery connections are made.
"""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from singer import metadata

try:
    from .base import Ga360BaseTest
except ImportError:
    from base import Ga360BaseTest

import tap_ga360
from tap_ga360.streams import STREAMS


class Ga360DiscoveryTest(Ga360BaseTest, unittest.TestCase):
    """Verify discover() returns a correct Singer Catalog for all streams."""

    def _get_catalog_entries(self):
        """Run discover() with a mocked BigQuery client; return list of catalog entries."""
        client = self._make_mock_client(
            tables=["ga_sessions_20200101", "ga_sessions_20200102"]
        )
        catalog_entries = []
        # discover() prints JSON — capture by patching print and json.dumps
        printed = {}

        def capture_print(arg):
            printed["out"] = arg

        with patch("builtins.print", side_effect=capture_print):
            tap_ga360.discover(client, self.config)

        raw = json.loads(printed["out"])
        return raw["streams"]

    # ── Stream presence ──────────────────────────────────────────────────

    def test_discovery_returns_all_expected_streams(self):
        """discover() must return exactly the set of expected streams."""
        entries = self._get_catalog_entries()
        discovered = {e["tap_stream_id"] for e in entries}
        self.assertEqual(discovered, self.expected_stream_names())

    def test_discovery_stream_count_matches_expected(self):
        """Number of catalog entries must equal the number of expected streams."""
        entries = self._get_catalog_entries()
        self.assertEqual(len(entries), len(self.expected_metadata()))

    def test_discovery_tap_stream_id_equals_stream_name(self):
        """tap_stream_id must equal stream for every entry."""
        for entry in self._get_catalog_entries():
            with self.subTest(stream=entry["stream"]):
                self.assertEqual(entry["tap_stream_id"], entry["stream"])

    # ── Primary keys ─────────────────────────────────────────────────────

    def test_discovery_primary_keys_match_expected(self):
        """Primary keys must match expected_metadata() for every stream."""
        expected = self.expected_metadata()
        for entry in self._get_catalog_entries():
            stream = entry["tap_stream_id"]
            with self.subTest(stream=stream):
                mdata_map = metadata.to_map(entry["metadata"])
                actual_pks = set(
                    metadata.get(mdata_map, (), "table-key-properties") or []
                )
                self.assertEqual(actual_pks, expected[stream][self.PRIMARY_KEYS])

    def test_ga_sessions_has_correct_primary_keys(self):
        """ga_sessions must declare fullVisitorId, visitId, visitStartTime as PKs."""
        for entry in self._get_catalog_entries():
            if entry["tap_stream_id"] == "ga_sessions":
                mdata_map = metadata.to_map(entry["metadata"])
                pks = set(metadata.get(mdata_map, (), "table-key-properties") or [])
                self.assertEqual(
                    pks, {"fullVisitorId", "visitId", "visitStartTime"}
                )

    def test_ga_session_hits_has_correct_primary_keys(self):
        """ga_session_hits must include hitNumber in addition to session PKs."""
        for entry in self._get_catalog_entries():
            if entry["tap_stream_id"] == "ga_session_hits":
                mdata_map = metadata.to_map(entry["metadata"])
                pks = set(metadata.get(mdata_map, (), "table-key-properties") or [])
                self.assertIn("hitNumber", pks)

    # ── Schema integrity ─────────────────────────────────────────────────

    def test_discovery_schema_has_properties(self):
        """Every discovered stream must have a schema with at least one property."""
        for entry in self._get_catalog_entries():
            with self.subTest(stream=entry["tap_stream_id"]):
                props = entry["schema"].get("properties", {})
                self.assertGreater(len(props), 0)

    def test_discovery_schema_is_not_none(self):
        """Schema must not be None for any stream."""
        for entry in self._get_catalog_entries():
            with self.subTest(stream=entry["tap_stream_id"]):
                self.assertIsNotNone(entry.get("schema"))

    def test_ga_sessions_schema_has_date_property(self):
        """ga_sessions schema must contain the replication key 'date'."""
        for entry in self._get_catalog_entries():
            if entry["tap_stream_id"] == "ga_sessions":
                props = entry["schema"].get("properties", {})
                self.assertIn("date", props)

    def test_ga_sessions_schema_has_fullVisitorId(self):
        """ga_sessions schema must contain 'fullVisitorId'."""
        for entry in self._get_catalog_entries():
            if entry["tap_stream_id"] == "ga_sessions":
                props = entry["schema"].get("properties", {})
                self.assertIn("fullVisitorId", props)

    def test_ga_session_hits_schema_has_hitNumber(self):
        """ga_session_hits schema must contain 'hitNumber'."""
        for entry in self._get_catalog_entries():
            if entry["tap_stream_id"] == "ga_session_hits":
                props = entry["schema"].get("properties", {})
                self.assertIn("hitNumber", props)

    # ── Replication method ───────────────────────────────────────────────

    def test_all_streams_are_incremental(self):
        """All tap-ga360 streams must use INCREMENTAL replication."""
        for entry in self._get_catalog_entries():
            with self.subTest(stream=entry["tap_stream_id"]):
                mdata_map = metadata.to_map(entry["metadata"])
                rep_method = (
                    metadata.get(mdata_map, (), "forced-replication-method")
                    or metadata.get(mdata_map, (), "replication-method")
                )
                self.assertEqual(rep_method, self.INCREMENTAL)

    def test_incremental_streams_have_valid_replication_keys(self):
        """INCREMENTAL streams must declare valid-replication-keys in metadata."""
        for entry in self._get_catalog_entries():
            stream = entry["tap_stream_id"]
            if stream in self.incremental_streams():
                with self.subTest(stream=stream):
                    mdata_map = metadata.to_map(entry["metadata"])
                    keys = metadata.get(mdata_map, (), "valid-replication-keys")
                    self.assertIsNotNone(keys)
                    self.assertGreater(len(keys), 0)

    def test_replication_key_is_date_for_all_streams(self):
        """Both streams must declare 'date' as the valid replication key."""
        for entry in self._get_catalog_entries():
            with self.subTest(stream=entry["tap_stream_id"]):
                mdata_map = metadata.to_map(entry["metadata"])
                keys = metadata.get(mdata_map, (), "valid-replication-keys") or []
                self.assertIn("date", keys)

    # ── Metadata completeness ────────────────────────────────────────────

    def test_metadata_list_is_not_empty(self):
        """Every catalog entry must have at least one metadata dict."""
        for entry in self._get_catalog_entries():
            with self.subTest(stream=entry["tap_stream_id"]):
                self.assertGreater(len(entry["metadata"]), 0)

    def test_discover_only_runs_once_per_stream(self):
        """discover() must not produce duplicate entries for the same stream."""
        entries = self._get_catalog_entries()
        stream_ids = [e["tap_stream_id"] for e in entries]
        self.assertEqual(len(stream_ids), len(set(stream_ids)))

    def test_discover_ignores_tables_not_matching_ga_sessions(self):
        """discover() must ignore tables that don't contain 'ga_sessions'."""
        client = self._make_mock_client(tables=["other_table_20200101"])
        printed = {}

        def capture_print(arg):
            printed["out"] = arg

        with patch("builtins.print", side_effect=capture_print):
            tap_ga360.discover(client, self.config)

        result = json.loads(printed["out"])
        self.assertEqual(result["streams"], [])
