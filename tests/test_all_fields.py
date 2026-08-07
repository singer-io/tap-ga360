"""Mock integration tests — all schema fields are replicated for tap-ga360 streams.

Uses _generate_stream_record() to produce schema-valid mock records and verifies
that every top-level property in the stream's JSON schema appears in the emitted
records.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    from .base import Ga360BaseTest
except ImportError:
    from base import Ga360BaseTest

from tap_ga360.streams import GaSessions, GaSessionHits


# ---------------------------------------------------------------------------
# Known missing fields
# Fields present in the schema but not emitted in mock records by default.
# ---------------------------------------------------------------------------
KNOWN_MISSING_FIELDS = {
    # BigQuery RECORD / array sub-fields are returned as nested objects and are
    # not individually enumerated at the top level by the Transformer.
}


class Ga360AllFieldsTest(Ga360BaseTest, unittest.TestCase):
    """Ensure syncing with all fields selected replicates every top-level schema field."""

    # ── Helpers ──────────────────────────────────────────────────────────

    def _run_sessions_sync(self, record):
        """Run GaSessions.sync() with one mock record; return list of written records."""
        client = MagicMock()
        table = SimpleNamespace(
            table_id="ga_sessions_20200102",
            full_table_id="test-project:test_dataset.ga_sessions_20200102",
        )
        client.list_tables.return_value = [table]

        row_mock = MagicMock()
        row_mock.items.return_value = list(record.items())
        client.list_rows.return_value = [row_mock]
        client.get_table.return_value.schema = []

        instance = GaSessions(
            client, "test-project", "test_dataset", self.default_start_date
        )
        catalog = self._make_catalog()
        entry = next(e for e in catalog.streams if e.tap_stream_id == "ga_sessions")

        written = []
        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record",
                   side_effect=lambda s, r, **kw: written.append(r)):
            instance.sync({}, entry.metadata)

        return written

    def _run_hits_sync(self, hits_row):
        """Run GaSessionHits.sync() with one session row; return written records."""
        client = MagicMock()
        table = SimpleNamespace(
            table_id="ga_sessions_20200102",
            full_table_id="test-project:test_dataset.ga_sessions_20200102",
        )
        client.list_tables.return_value = [table]

        row_mock = MagicMock()
        row_mock.items.return_value = list(hits_row.items())
        client.query.return_value.result.return_value = [row_mock]

        instance = GaSessionHits(
            client, "test-project", "test_dataset", self.default_start_date
        )
        catalog = self._make_catalog()
        entry = next(e for e in catalog.streams if e.tap_stream_id == "ga_session_hits")

        written = []
        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record",
                   side_effect=lambda s, r, **kw: written.append(r)):
            instance.sync({}, entry.metadata)

        return written

    def _assert_all_fields_present(self, stream_name, written_records):
        """Assert every top-level schema property appears in at least one written record."""
        schema = self._load_schema(stream_name)
        top_level_fields = set(schema.get("properties", {}).keys())
        known_missing = KNOWN_MISSING_FIELDS.get(stream_name, set())

        if not written_records:
            self.fail("No records were written for stream '{}'".format(stream_name))

        all_written_keys = set()
        for record in written_records:
            all_written_keys.update(record.keys())

        missing = (top_level_fields - known_missing) - all_written_keys
        self.assertEqual(
            missing,
            set(),
            msg=(
                "Stream '{}': the following top-level schema fields were not found "
                "in any written record: {}".format(stream_name, missing)
            ),
        )

    # ── ga_sessions all-fields test ───────────────────────────────────────

    def test_ga_sessions_all_top_level_fields_present(self):
        """All top-level ga_sessions schema fields must appear in written records."""
        record = self._generate_stream_record("ga_sessions")
        written = self._run_sessions_sync(record)
        self._assert_all_fields_present("ga_sessions", written)

    # ── ga_session_hits all-fields test ──────────────────────────────────

    def test_ga_session_hits_all_top_level_fields_present(self):
        """All top-level ga_session_hits schema fields must appear in written records."""
        hit_record = self._generate_stream_record("ga_session_hits")
        # ga_session_hits queries sessions and flattens the hits array
        hits_row = {
            "fullVisitorId": hit_record.get("fullVisitorId", "visitor1"),
            "visitId": hit_record.get("visitId", 1),
            "visitStartTime": hit_record.get("visitStartTime", 1000),
            "hits": [hit_record],
        }
        written = self._run_hits_sync(hits_row)
        self._assert_all_fields_present("ga_session_hits", written)

    # ── Record count sanity ───────────────────────────────────────────────

    def test_ga_sessions_writes_one_record_per_row(self):
        """GaSessions must write exactly one record per BigQuery row."""
        record = self._generate_stream_record("ga_sessions")
        written = self._run_sessions_sync(record)
        self.assertEqual(len(written), 1)

    def test_ga_session_hits_writes_one_record_per_hit(self):
        """GaSessionHits must emit one record per hit entry in the hits array."""
        hits_row = {
            "fullVisitorId": "visitor1",
            "visitId": 1,
            "visitStartTime": 1000,
            "hits": [{"hitNumber": 1}, {"hitNumber": 2}, {"hitNumber": 3}],
        }
        written = self._run_hits_sync(hits_row)
        self.assertEqual(len(written), 3)

    def test_ga_session_hits_empty_hits_writes_no_records(self):
        """GaSessionHits must not emit records for sessions with empty hits array."""
        hits_row = {
            "fullVisitorId": "visitor1",
            "visitId": 1,
            "visitStartTime": 1000,
            "hits": [],
        }
        written = self._run_hits_sync(hits_row)
        self.assertEqual(len(written), 0)

    def test_ga_session_hits_null_hits_writes_no_records(self):
        """GaSessionHits must not emit records for sessions with None hits."""
        hits_row = {
            "fullVisitorId": "visitor1",
            "visitId": 1,
            "visitStartTime": 1000,
            "hits": None,
        }
        written = self._run_hits_sync(hits_row)
        self.assertEqual(len(written), 0)

    # ── Key properties embedded in hits ──────────────────────────────────

    def test_ga_session_hits_injects_session_key_props_into_each_hit(self):
        """Each hit record must contain fullVisitorId, visitId, visitStartTime from the parent session."""
        hits_row = {
            "fullVisitorId": "visitor-abc",
            "visitId": 42,
            "visitStartTime": 9999,
            "hits": [{"hitNumber": 1}, {"hitNumber": 2}],
        }
        written = self._run_hits_sync(hits_row)
        for record in written:
            with self.subTest(record=record):
                self.assertEqual(record["fullVisitorId"], "visitor-abc")
                self.assertEqual(record["visitId"], 42)
                self.assertEqual(record["visitStartTime"], 9999)
