import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, mock_open, patch

from tap_ga360 import streams


START_DATE = "2020-01-01T00:00:00Z"


def make_stream(stream_class=streams.GaSessions, client=None):
    with patch.object(stream_class, "load_schema", return_value={"type": "object"}):
        return stream_class(client or MagicMock(), "project", "dataset", START_DATE)


class TestGetAbsPath(unittest.TestCase):

    def test_get_abs_path_points_inside_package(self):
        self.assertTrue(
            streams.get_abs_path("schemas/example.json").endswith(
                "tap_ga360/schemas/example.json"
            )
        )


class TestStreamLoadSchemaAndCatalog(unittest.TestCase):

    @patch("tap_ga360.streams.get_standard_metadata")
    @patch("builtins.open", new_callable=mock_open)
    def test_stream_loads_schema_and_exposes_catalog(
        self, mock_file, mock_get_standard_metadata
    ):
        payload = {"type": "object", "properties": {}}
        mock_file.return_value.read.return_value = json.dumps(payload)
        mock_file.return_value.__enter__.return_value.read.return_value = json.dumps(payload)
        mock_get_standard_metadata.return_value = ["metadata"]

        instance = streams.GaSessions("client", "project", "dataset", START_DATE)
        self.assertEqual(instance.schema, payload)
        self.assertTrue(mock_file.call_args.args[0].endswith("schemas/ga_sessions.json"))

        result = instance.catalog_entry()
        self.assertEqual(
            result,
            {
                "stream": "ga_sessions",
                "tap_stream_id": "ga_sessions",
                "schema": payload,
                "metadata": ["metadata"],
            },
        )
        mock_get_standard_metadata.assert_called_once_with(
            schema=payload,
            key_properties=instance.key_properties,
            valid_replication_keys=["date"],
            replication_method="INCREMENTAL",
        )


class TestWriteSchema(unittest.TestCase):

    @patch("tap_ga360.streams.write_schema")
    def test_write_schema_delegates_to_singer(self, mock_write_schema):
        instance = make_stream()
        instance.write_schema()
        mock_write_schema.assert_called_once_with(
            "ga_sessions", instance.schema, instance.key_properties
        )


class TestGetBookmark(unittest.TestCase):

    @patch("tap_ga360.streams.utils.strptime_to_utc")
    @patch("tap_ga360.streams.get_bookmark")
    def test_get_bookmark_uses_state_value(self, mock_get_bookmark, mock_parse):
        instance = make_stream()
        expected = datetime(2020, 1, 2, tzinfo=timezone.utc)
        mock_get_bookmark.return_value = "2020-01-02T00:00:00Z"
        mock_parse.return_value = expected
        self.assertEqual(instance.get_bookmark({}), expected)
        mock_parse.assert_called_once_with("2020-01-02T00:00:00Z")

    @patch("tap_ga360.streams.utils.strptime_to_utc")
    @patch("tap_ga360.streams.get_bookmark")
    def test_get_bookmark_falls_back_to_start_date(self, mock_get_bookmark, mock_parse):
        instance = make_stream()
        expected = datetime(2020, 1, 1, tzinfo=timezone.utc)
        mock_get_bookmark.return_value = None
        mock_parse.return_value = expected
        instance.get_bookmark({})
        mock_parse.assert_called_once_with(START_DATE)


class TestUpdateBookmark(unittest.TestCase):

    @patch("tap_ga360.streams.write_bookmark")
    @patch("tap_ga360.streams.utils.strptime_to_utc")
    def test_update_bookmark_only_writes_newer_nonempty_values(
        self, mock_parse, mock_write_bookmark
    ):
        instance = make_stream()
        instance.get_bookmark = MagicMock(
            return_value=datetime(2020, 1, 2, tzinfo=timezone.utc)
        )
        state = {}

        # None value — should not write
        instance.update_bookmark(state, None)

        # Older value — should not write
        mock_parse.return_value = datetime(2020, 1, 1, tzinfo=timezone.utc)
        instance.update_bookmark(state, "20200101")

        # Newer value — should write
        mock_parse.return_value = datetime(2020, 1, 3, tzinfo=timezone.utc)
        instance.update_bookmark(state, "20200103")

        mock_write_bookmark.assert_called_once_with(
            state, "ga_sessions", "date", "20200103"
        )


class TestFilterFields(unittest.TestCase):

    def test_filter_fields_selects_explicit_and_automatic_fields(self):
        client = MagicMock()
        client.get_table.return_value.schema = [
            SimpleNamespace(name="selected"),
            SimpleNamespace(name="automatic"),
            SimpleNamespace(name="excluded"),
        ]
        instance = make_stream(client=client)
        metadata = {
            ("properties", "selected"): {"selected": True},
            ("properties", "automatic"): {"inclusion": "automatic"},
        }
        result = [f.name for f in instance.filter_fields(metadata, "table")]
        self.assertEqual(result, ["selected", "automatic"])


class TestGetTablesToExtract(unittest.TestCase):

    def test_filters_sorts_and_excludes_intraday(self):
        client = MagicMock()
        client.list_tables.return_value = [
            SimpleNamespace(table_id="ga_sessions_intraday_20200104"),
            SimpleNamespace(table_id="ga_sessions_20200103"),
            SimpleNamespace(table_id="other_20200105"),
            SimpleNamespace(table_id="ga_sessions_20200102"),
            SimpleNamespace(table_id="ga_sessions_20191231"),
        ]
        instance = make_stream(client=client)
        bookmark = datetime(2020, 1, 1, tzinfo=timezone.utc)
        result = [t.table_id for t in instance.get_tables_to_extract("ga_sessions", bookmark)]
        self.assertEqual(result, ["ga_sessions_20200102", "ga_sessions_20200103"])

    def test_returns_empty_when_no_new_tables(self):
        client = MagicMock()
        client.list_tables.return_value = []
        instance = make_stream(client=client)
        bookmark = datetime(2020, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(list(instance.get_tables_to_extract("ga_sessions", bookmark)), [])


class TestGaSessionsSync(unittest.TestCase):

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.utils.now")
    @patch("tap_ga360.streams.to_map")
    @patch("tap_ga360.streams.Transformer")
    def test_sync_writes_records_bookmark_and_state(
        self, mock_transformer_cls, mock_to_map, mock_now, mock_write_record, mock_write_state
    ):
        client = MagicMock()
        table = SimpleNamespace(table_id="ga_sessions_20200102")
        client.list_rows.return_value = [MagicMock(items=lambda: [("id", 1)])]

        instance = make_stream(client=client)
        instance.get_bookmark = MagicMock(return_value="bookmark")
        instance.get_tables_to_extract = MagicMock(return_value=[table])
        instance.filter_fields = MagicMock(return_value=["selected-field"])
        instance.update_bookmark = MagicMock()

        transformer = MagicMock()
        transformer.transform.return_value = {"id": 1}
        mock_transformer_cls.return_value.__enter__.return_value = transformer
        mock_to_map.return_value = {"mapped": True}
        mock_now.return_value = "now"

        instance.sync({"state": True}, ["metadata"], page_size=10)

        client.list_rows.assert_called_once_with(
            table, page_size=10, selected_fields=["selected-field"]
        )
        transformer.transform.assert_called_once_with(
            {"id": 1}, instance.schema, {"mapped": True}
        )
        mock_write_record.assert_called_once_with(
            "ga_sessions", {"id": 1}, time_extracted="now"
        )
        instance.update_bookmark.assert_called_once_with({"state": True}, "20200102")
        mock_write_state.assert_called_once_with({"state": True})


class TestGaSessionHitsSync(unittest.TestCase):

    @patch("tap_ga360.streams.write_state")
    @patch("tap_ga360.streams.write_record")
    @patch("tap_ga360.streams.utils.now")
    @patch("tap_ga360.streams.to_map")
    @patch("tap_ga360.streams.Transformer")
    def test_sync_flattens_hits_and_skips_empty_hits(
        self, mock_transformer_cls, mock_to_map, mock_now, mock_write_record, mock_write_state
    ):
        client = MagicMock()
        table = SimpleNamespace(
            table_id="ga_sessions_20200102",
            full_table_id="project:dataset.ga_sessions_20200102",
        )
        client.query.return_value.result.return_value = [
            MagicMock(
                items=lambda: [
                    ("fullVisitorId", "visitor"),
                    ("visitId", 2),
                    ("visitStartTime", 3),
                    ("hits", [{"hitNumber": 1}, {"hitNumber": 2}]),
                ]
            ),
            MagicMock(
                items=lambda: [
                    ("fullVisitorId", "visitor"),
                    ("visitId", 2),
                    ("visitStartTime", 3),
                    ("hits", []),
                ]
            ),
        ]
        instance = make_stream(streams.GaSessionHits, client)
        instance.get_bookmark = MagicMock(return_value="bookmark")
        instance.get_tables_to_extract = MagicMock(return_value=[table])
        instance.update_bookmark = MagicMock()

        transformer = MagicMock()
        transformer.transform.side_effect = lambda record, *_: record
        mock_transformer_cls.return_value.__enter__.return_value = transformer
        mock_to_map.return_value = {"mapped": True}
        mock_now.return_value = "now"

        instance.sync({"state": True}, ["metadata"], page_size=10)

        client.query.assert_called_once_with(
            "SELECT hits, fullVisitorId, visitId, visitStartTime"
            " FROM `project.dataset.ga_sessions_20200102`"
        )
        self.assertEqual(transformer.transform.call_count, 2)
        self.assertEqual(mock_write_record.call_count, 2)
        self.assertEqual(
            mock_write_record.call_args_list[0],
            call(
                "ga_session_hits",
                {
                    "hitNumber": 1,
                    "fullVisitorId": "visitor",
                    "visitId": 2,
                    "visitStartTime": 3,
                },
                time_extracted="now",
            ),
        )
        instance.update_bookmark.assert_called_once_with({"state": True}, "20200102")
        mock_write_state.assert_called_once_with({"state": True})
