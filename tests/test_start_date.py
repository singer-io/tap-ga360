"""Mock integration tests for tap-ga360 start_date filtering.

Verifies that the tap respects start_date: tables whose date is on or before
the start_date (or current bookmark) are skipped, and only newer tables are
replicated.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    from .base import Ga360BaseTest
except ImportError:
    from base import Ga360BaseTest

from tap_ga360.streams import GaSessions, GaSessionHits


class Ga360StartDateTest(Ga360BaseTest, unittest.TestCase):
    """Verify start_date and bookmark filtering for INCREMENTAL streams."""

    # ── Helpers ──────────────────────────────────────────────────────────

    def _make_tables(self, table_ids):
        return [
            SimpleNamespace(
                table_id=t,
                full_table_id="test-project:test_dataset.{}".format(t),
            )
            for t in table_ids
        ]

    def _run_sessions_sync(self, table_ids, start_date, initial_state=None):
        """Run GaSessions.sync(); return list of list_rows call table_ids."""
        client = MagicMock()
        client.list_tables.return_value = self._make_tables(table_ids)
        client.list_rows.return_value = []
        client.get_table.return_value.schema = []

        state = initial_state or {}
        instance = GaSessions(client, "test-project", "test_dataset", start_date)
        catalog = self._make_catalog()
        entry = next(e for e in catalog.streams if e.tap_stream_id == "ga_sessions")

        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record"):
            instance.sync(state, entry.metadata)

        return [c[0][0].table_id for c in client.list_rows.call_args_list]

    def _run_hits_sync(self, table_ids, start_date, initial_state=None):
        """Run GaSessionHits.sync(); return list of query call arguments."""
        client = MagicMock()
        client.list_tables.return_value = self._make_tables(table_ids)
        client.query.return_value.result.return_value = []

        state = initial_state or {}
        instance = GaSessionHits(client, "test-project", "test_dataset", start_date)
        catalog = self._make_catalog()
        entry = next(e for e in catalog.streams if e.tap_stream_id == "ga_session_hits")

        with patch("tap_ga360.streams.write_schema"), \
             patch("tap_ga360.streams.write_state"), \
             patch("tap_ga360.streams.write_record"):
            instance.sync(state, entry.metadata)

        return [c[0][0] for c in client.query.call_args_list]

    # ── ga_sessions start_date tests ─────────────────────────────────────

    def test_tables_on_or_before_start_date_are_skipped(self):
        """Tables with date <= start_date must not be synced."""
        synced = self._run_sessions_sync(
            table_ids=[
                "ga_sessions_20200101",  # == start_date → skip
                "ga_sessions_20191231",  # before start_date → skip
                "ga_sessions_20200102",  # after start_date → sync
            ],
            start_date="2020-01-01T00:00:00Z",
        )
        self.assertEqual(synced, ["ga_sessions_20200102"])

    def test_only_tables_after_start_date_are_synced(self):
        """Only tables with table_id > bookmark table_id are processed."""
        synced = self._run_sessions_sync(
            table_ids=[
                "ga_sessions_20200101",
                "ga_sessions_20200102",
                "ga_sessions_20200103",
            ],
            start_date="2020-01-01T00:00:00Z",
        )
        self.assertEqual(synced, ["ga_sessions_20200102", "ga_sessions_20200103"])

    def test_no_tables_synced_when_all_before_start_date(self):
        """When all tables predate start_date, nothing is synced."""
        synced = self._run_sessions_sync(
            table_ids=["ga_sessions_20191231", "ga_sessions_20191230"],
            start_date="2020-01-01T00:00:00Z",
        )
        self.assertEqual(synced, [])

    def test_all_tables_synced_when_far_before_start_date(self):
        """All available tables are synced when start_date is before all of them."""
        synced = self._run_sessions_sync(
            table_ids=["ga_sessions_20200101", "ga_sessions_20200102"],
            start_date="2019-01-01T00:00:00Z",
        )
        self.assertEqual(synced, ["ga_sessions_20200101", "ga_sessions_20200102"])

    def test_tables_are_synced_in_ascending_date_order(self):
        """Tables must be synced in chronological (ascending) order."""
        synced = self._run_sessions_sync(
            table_ids=[
                "ga_sessions_20200103",
                "ga_sessions_20200101",
                "ga_sessions_20200102",
            ],
            start_date="2019-01-01T00:00:00Z",
        )
        self.assertEqual(
            synced,
            ["ga_sessions_20200101", "ga_sessions_20200102", "ga_sessions_20200103"],
        )

    def test_intraday_tables_are_excluded(self):
        """Intraday tables (ga_sessions_intraday_*) must never be synced."""
        synced = self._run_sessions_sync(
            table_ids=[
                "ga_sessions_intraday_20200102",
                "ga_sessions_20200102",
            ],
            start_date="2020-01-01T00:00:00Z",
        )
        self.assertEqual(synced, ["ga_sessions_20200102"])

    def test_non_ga_tables_are_excluded(self):
        """Tables with unrelated names must not be synced."""
        synced = self._run_sessions_sync(
            table_ids=[
                "some_other_table_20200102",
                "ga_sessions_20200102",
            ],
            start_date="2020-01-01T00:00:00Z",
        )
        self.assertEqual(synced, ["ga_sessions_20200102"])

    def test_start_date_respected_when_bookmark_in_state(self):
        """When state has a bookmark, only tables after that bookmark are synced."""
        state = {"bookmarks": {"ga_sessions": {"date": "20200102T000000Z"}}}
        synced = self._run_sessions_sync(
            table_ids=[
                "ga_sessions_20200101",
                "ga_sessions_20200102",
                "ga_sessions_20200103",
                "ga_sessions_20200104",
            ],
            start_date="2020-01-01T00:00:00Z",
            initial_state=state,
        )
        # Bookmark is 20200102 so only 20200103 and 20200104 should be synced
        self.assertNotIn("ga_sessions_20200101", synced)
        self.assertNotIn("ga_sessions_20200102", synced)

    # ── ga_session_hits start_date tests ─────────────────────────────────

    def test_hits_tables_on_or_before_start_date_are_skipped(self):
        """GaSessionHits must skip tables on or before start_date."""
        queries = self._run_hits_sync(
            table_ids=[
                "ga_sessions_20200101",  # == start_date → skip
                "ga_sessions_20200102",  # after → sync
            ],
            start_date="2020-01-01T00:00:00Z",
        )
        self.assertEqual(len(queries), 1)
        self.assertIn("ga_sessions_20200102", queries[0])

    def test_hits_syncs_tables_in_ascending_order(self):
        """GaSessionHits tables must be queried in ascending date order."""
        queries = self._run_hits_sync(
            table_ids=[
                "ga_sessions_20200103",
                "ga_sessions_20200101",
                "ga_sessions_20200102",
            ],
            start_date="2019-01-01T00:00:00Z",
        )
        self.assertEqual(len(queries), 3)
        # Extract table name from each query string
        table_names = [q.split("`")[1].split(".")[-1] for q in queries]
        self.assertEqual(
            table_names,
            ["ga_sessions_20200101", "ga_sessions_20200102", "ga_sessions_20200103"],
        )
