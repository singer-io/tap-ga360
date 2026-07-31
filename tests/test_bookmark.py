"""Mock integration tests for tap-ga360 bookmark (incremental replication).

Patches the BigQuery client to supply controlled records. Verifies:
  - Bookmarks are written to state after a sync.
  - A second sync with a bookmark in state skips tables before the bookmark date.
  - INCREMENTAL streams advance the bookmark to the most recently seen table date.
"""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

try:
    from .base import Ga360BaseTest
except ImportError:
    from base import Ga360BaseTest

from tap_ga360.streams import GaSessions, GaSessionHits


class Ga360BookmarkTest(Ga360BaseTest, unittest.TestCase):
    """Verify bookmark behaviour for INCREMENTAL streams."""

    # ── Helpers ──────────────────────────────────────────────────────────

    def _make_session_row(self, date_str, visitor_id="visitor1", visit_id=1, visit_start=1000):
        """Build a mock BigQuery row dict for a ga_sessions record."""
        return {
            "fullVisitorId": visitor_id,
            "visitId": visit_id,
            "visitStartTime": visit_start,
            "date": date_str,
            "visitNumber": 1,
        }

    def _make_hits_row(self, date_str, visitor_id="visitor1", visit_id=1, visit_start=1000, hits=None):
        """Build a mock BigQuery row dict for a ga_session_hits parent session row."""
        return {
            "fullVisitorId": visitor_id,
            "visitId": visit_id,
            "visitStartTime": visit_start,
            "hits": hits or [{"hitNumber": 1, "type": "PAGE"}],
        }

    def _run_ga_sessions_sync(self, tables, rows, start_date=None, initial_state=None):
        """Run GaSessions.sync() with mocked client; return (state, written_records)."""
        start_date = start_date or self.default_start_date
        state = initial_state or {}

        client = MagicMock()
        table_mocks = [
            SimpleNamespace(
                table_id=t,
                full_table_id="test-project:test_dataset.{}".format(t),
            )
            for t in tables
        ]
        client.list_tables.return_value = table_mocks

        row_mocks = []
        for r in rows:
            rm = MagicMock()
            rm.items.return_value = list(r.items())
            row_mocks.append(rm)
        client.list_rows.return_value = row_mocks

        # filter_fields returns empty list (all fields treated as selected)
        client.get_table.return_value.schema = []

        instance = GaSessions(client, "test-project", "test_dataset", start_date)
        catalog = self._make_catalog()
        ga_sessions_entry = next(
            e for e in catalog.streams if e.tap_stream_id == "ga_sessions"
        )

        written = []
        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record",
                   side_effect=lambda s, r, **kw: written.append(r)):
            instance.sync(state, ga_sessions_entry.metadata)

        return state, written

    # ── ga_sessions bookmark tests ────────────────────────────────────────

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_bookmark_is_written_after_sync(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """After syncing ga_sessions, state must contain a 'date' bookmark."""
        state, _ = self._run_ga_sessions_sync(
            tables=["ga_sessions_20200102"],
            rows=[self._make_session_row("20200102")],
        )
        self.assertIn("bookmarks", state)
        self.assertIn("ga_sessions", state["bookmarks"])

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_bookmark_advances_to_most_recent_table(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """Bookmark must equal the date of the latest table synced."""
        state, _ = self._run_ga_sessions_sync(
            tables=["ga_sessions_20200102", "ga_sessions_20200103"],
            rows=[self._make_session_row("20200102")],
        )
        bookmark = state.get("bookmarks", {}).get("ga_sessions", {}).get("date", "")
        self.assertIn("20200103", bookmark,
                      msg="Bookmark must advance to the most recent table date")

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_second_sync_skips_tables_before_bookmark(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """A second sync with a bookmark must not re-sync already-seen tables."""
        # First sync: process table 20200101
        state, _ = self._run_ga_sessions_sync(
            tables=["ga_sessions_20200101"],
            rows=[self._make_session_row("20200101")],
        )
        # Second sync: only table 20200102 should be processed (not 20200101)
        client = MagicMock()
        all_tables = [
            SimpleNamespace(
                table_id="ga_sessions_20200101",
                full_table_id="test-project:test_dataset.ga_sessions_20200101",
            ),
            SimpleNamespace(
                table_id="ga_sessions_20200102",
                full_table_id="test-project:test_dataset.ga_sessions_20200102",
            ),
        ]
        client.list_tables.return_value = all_tables
        row_mock = MagicMock()
        row_mock.items.return_value = list(
            self._make_session_row("20200102").items()
        )
        client.list_rows.return_value = [row_mock]
        client.get_table.return_value.schema = []

        instance = GaSessions(client, "test-project", "test_dataset", self.default_start_date)
        catalog = self._make_catalog()
        ga_sessions_entry = next(
            e for e in catalog.streams if e.tap_stream_id == "ga_sessions"
        )
        written = []
        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record",
                   side_effect=lambda s, r, **kw: written.append(r)):
            instance.sync(state, ga_sessions_entry.metadata)

        # list_rows should be called exactly once (for the new table only)
        self.assertEqual(client.list_rows.call_count, 1)
        list_rows_table = client.list_rows.call_args[0][0]
        self.assertEqual(list_rows_table.table_id, "ga_sessions_20200102")

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_no_new_tables_does_not_update_bookmark(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """When no new tables exist, the bookmark must not be modified."""
        initial_state = {"bookmarks": {"ga_sessions": {"date": "20200103T000000Z"}}}
        state, _ = self._run_ga_sessions_sync(
            tables=["ga_sessions_20200101", "ga_sessions_20200102"],
            rows=[],
            initial_state=initial_state,
        )
        # Bookmark must remain unchanged (no newer tables were processed)
        bookmark = state.get("bookmarks", {}).get("ga_sessions", {}).get("date", "")
        self.assertIn("20200103", bookmark)

    # ── ga_session_hits bookmark tests ────────────────────────────────────

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_ga_session_hits_bookmark_written_after_sync(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """After syncing ga_session_hits, state must contain a 'date' bookmark."""
        client = MagicMock()
        table = SimpleNamespace(
            table_id="ga_sessions_20200102",
            full_table_id="test-project:test_dataset.ga_sessions_20200102",
        )
        client.list_tables.return_value = [table]
        row_mock = MagicMock()
        row_mock.items.return_value = list(
            self._make_hits_row("20200102").items()
        )
        client.query.return_value.result.return_value = [row_mock]

        state = {}
        instance = GaSessionHits(
            client, "test-project", "test_dataset", self.default_start_date
        )
        catalog = self._make_catalog()
        hits_entry = next(
            e for e in catalog.streams if e.tap_stream_id == "ga_session_hits"
        )
        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record"):
            instance.sync(state, hits_entry.metadata)

        self.assertIn("bookmarks", state)
        self.assertIn("ga_session_hits", state["bookmarks"])

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_ga_session_hits_bookmark_reflects_latest_table(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """ga_session_hits bookmark must reflect the most recent table date synced."""
        client = MagicMock()
        tables = [
            SimpleNamespace(
                table_id="ga_sessions_20200102",
                full_table_id="test-project:test_dataset.ga_sessions_20200102",
            ),
            SimpleNamespace(
                table_id="ga_sessions_20200103",
                full_table_id="test-project:test_dataset.ga_sessions_20200103",
            ),
        ]
        client.list_tables.return_value = tables
        row_mock = MagicMock()
        row_mock.items.return_value = list(self._make_hits_row("20200102").items())
        client.query.return_value.result.return_value = [row_mock]

        state = {}
        instance = GaSessionHits(
            client, "test-project", "test_dataset", self.default_start_date
        )
        catalog = self._make_catalog()
        hits_entry = next(
            e for e in catalog.streams if e.tap_stream_id == "ga_session_hits"
        )
        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record"):
            instance.sync(state, hits_entry.metadata)

        bookmark = state.get("bookmarks", {}).get("ga_session_hits", {}).get("date", "")
        self.assertIn("20200103", bookmark)
