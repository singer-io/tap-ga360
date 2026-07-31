"""Mock integration tests for interrupted / resumed sync in tap-ga360.

Verifies that:
  - A resumed sync from a bookmark correctly skips already-processed tables.
  - The bookmark is advanced after a resumed sync completes.
  - Multiple tables are processed correctly even when sync resumes mid-run.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    from .base import Ga360BaseTest
except ImportError:
    from base import Ga360BaseTest

from tap_ga360.streams import GaSessions, GaSessionHits


class Ga360InterruptedSyncTest(Ga360BaseTest, unittest.TestCase):
    """Verify sync resumes correctly after an interruption."""

    # ── Helpers ──────────────────────────────────────────────────────────

    def _make_tables(self, table_ids):
        return [
            SimpleNamespace(
                table_id=t,
                full_table_id="test-project:test_dataset.{}".format(t),
            )
            for t in table_ids
        ]

    def _run_sessions_sync(self, table_ids, rows, initial_state):
        """Run GaSessions.sync() and return (final_state, written_records, list_rows_calls)."""
        client = MagicMock()
        client.list_tables.return_value = self._make_tables(table_ids)

        row_mocks = []
        for r in rows:
            rm = MagicMock()
            rm.items.return_value = list(r.items())
            row_mocks.append(rm)
        client.list_rows.return_value = row_mocks
        client.get_table.return_value.schema = []

        state = dict(initial_state)
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
            instance.sync(state, entry.metadata)

        return state, written, client.list_rows.call_args_list

    # ── Resumed sync tests ───────────────────────────────────────────────

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_resumed_sync_skips_pre_bookmark_tables(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """Resumed sync must not re-process tables already covered by the bookmark."""
        interrupted_state = {"bookmarks": {"ga_sessions": {"date": "20200102T000000Z"}}}

        state, _, list_rows_calls = self._run_sessions_sync(
            table_ids=[
                "ga_sessions_20200101",
                "ga_sessions_20200102",
                "ga_sessions_20200103",
            ],
            rows=[{"fullVisitorId": "v1", "visitId": 1, "visitStartTime": 1}],
            initial_state=interrupted_state,
        )
        synced_tables = [c[0][0].table_id for c in list_rows_calls]
        self.assertNotIn("ga_sessions_20200101", synced_tables)
        self.assertNotIn("ga_sessions_20200102", synced_tables)
        self.assertIn("ga_sessions_20200103", synced_tables)

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_bookmark_advanced_after_resumed_sync(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """After a resumed sync the bookmark must advance to the most recent table."""
        interrupted_state = {"bookmarks": {"ga_sessions": {"date": "20200102T000000Z"}}}

        state, _, _ = self._run_sessions_sync(
            table_ids=[
                "ga_sessions_20200101",
                "ga_sessions_20200102",
                "ga_sessions_20200103",
                "ga_sessions_20200104",
            ],
            rows=[{"fullVisitorId": "v1", "visitId": 1, "visitStartTime": 1}],
            initial_state=interrupted_state,
        )
        bookmark = state.get("bookmarks", {}).get("ga_sessions", {}).get("date", "")
        self.assertIn("20200104", bookmark,
                      msg="Bookmark must advance to the latest synced table after resume")

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_bookmark_not_changed_when_no_new_tables_on_resume(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """If no new tables exist after the bookmark, the bookmark must remain unchanged."""
        interrupted_state = {"bookmarks": {"ga_sessions": {"date": "20200103T000000Z"}}}

        state, _, list_rows_calls = self._run_sessions_sync(
            table_ids=["ga_sessions_20200101", "ga_sessions_20200102"],
            rows=[],
            initial_state=interrupted_state,
        )
        # No list_rows calls should have been made
        self.assertEqual(len(list_rows_calls), 0)
        bookmark = state.get("bookmarks", {}).get("ga_sessions", {}).get("date", "")
        self.assertIn("20200103", bookmark)

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_multiple_tables_processed_from_clean_state(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """From clean state, all tables after start_date are processed in order."""
        state, _, list_rows_calls = self._run_sessions_sync(
            table_ids=[
                "ga_sessions_20200102",
                "ga_sessions_20200103",
                "ga_sessions_20200104",
            ],
            rows=[{"fullVisitorId": "v1", "visitId": 1, "visitStartTime": 1}],
            initial_state={},
        )
        synced_tables = [c[0][0].table_id for c in list_rows_calls]
        self.assertEqual(
            synced_tables,
            ["ga_sessions_20200102", "ga_sessions_20200103", "ga_sessions_20200104"],
        )

    # ── ga_session_hits interrupted sync ─────────────────────────────────

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_ga_session_hits_resumed_sync_skips_old_tables(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """ga_session_hits resumed sync must not re-query tables before bookmark."""
        interrupted_state = {
            "bookmarks": {"ga_session_hits": {"date": "20200102T000000Z"}}
        }

        client = MagicMock()
        tables = self._make_tables(
            ["ga_sessions_20200101", "ga_sessions_20200102", "ga_sessions_20200103"]
        )
        client.list_tables.return_value = tables

        row_mock = MagicMock()
        row_mock.items.return_value = [
            ("fullVisitorId", "v1"),
            ("visitId", 1),
            ("visitStartTime", 1000),
            ("hits", [{"hitNumber": 1}]),
        ]
        client.query.return_value.result.return_value = [row_mock]

        state = dict(interrupted_state)
        instance = GaSessionHits(
            client, "test-project", "test_dataset", self.default_start_date
        )
        catalog = self._make_catalog()
        entry = next(e for e in catalog.streams if e.tap_stream_id == "ga_session_hits")

        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record"):
            instance.sync(state, entry.metadata)

        # Only ga_sessions_20200103 should be queried
        self.assertEqual(client.query.call_count, 1)
        query_sql = client.query.call_args[0][0]
        self.assertIn("ga_sessions_20200103", query_sql)
        self.assertNotIn("ga_sessions_20200101", query_sql)
        self.assertNotIn("ga_sessions_20200102", query_sql)

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.write_schema")
    def test_ga_session_hits_bookmark_advanced_after_resumed_sync(
        self, mock_write_schema, mock_write_record, mock_write_state
    ):
        """ga_session_hits bookmark must advance to the latest table after a resumed sync."""
        interrupted_state = {
            "bookmarks": {"ga_session_hits": {"date": "20200102T000000Z"}}
        }

        client = MagicMock()
        tables = self._make_tables(
            ["ga_sessions_20200103", "ga_sessions_20200104"]
        )
        client.list_tables.return_value = tables

        row_mock = MagicMock()
        row_mock.items.return_value = [
            ("fullVisitorId", "v1"),
            ("visitId", 1),
            ("visitStartTime", 1000),
            ("hits", [{"hitNumber": 1}]),
        ]
        client.query.return_value.result.return_value = [row_mock]

        state = dict(interrupted_state)
        instance = GaSessionHits(
            client, "test-project", "test_dataset", self.default_start_date
        )
        catalog = self._make_catalog()
        entry = next(e for e in catalog.streams if e.tap_stream_id == "ga_session_hits")

        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record"):
            instance.sync(state, entry.metadata)

        bookmark = state.get("bookmarks", {}).get("ga_session_hits", {}).get("date", "")
        self.assertIn("20200104", bookmark)
