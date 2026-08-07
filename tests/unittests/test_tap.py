import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import tap_ga360


CONFIG = {
    "project_id": "project",
    "dataset_id": "dataset",
    "start_date": "2020-01-01T00:00:00Z",
    "service_account_json": json.dumps({"project_id": "credentials-project"}),
}


class TestSync(unittest.TestCase):

    def test_sync_runs_each_selected_stream(self):
        instance = MagicMock()
        mock_class = MagicMock(return_value=instance)

        stream = SimpleNamespace(
            tap_stream_id="ga_sessions", metadata={"metadata": True}
        )
        catalog = MagicMock()
        catalog.get_selected_streams.return_value = [stream]

        with patch.dict(tap_ga360.STREAMS, {"ga_sessions": mock_class}, clear=True):
            tap_ga360.sync("client", catalog, {"state": True}, {**CONFIG, "page_size": 25})

        mock_class.assert_called_once_with(
            "client", "project", "dataset", "2020-01-01T00:00:00Z"
        )
        instance.write_schema.assert_called_once_with()
        instance.sync.assert_called_once_with({"state": True}, {"metadata": True}, 25)


class TestDiscover(unittest.TestCase):

    def test_discover_outputs_parent_and_substream_once(self):
        sessions_instance = MagicMock()
        sessions_instance.catalog_entry.return_value = {"stream": "ga_sessions"}
        hits_instance = MagicMock()
        hits_instance.catalog_entry.return_value = {"stream": "ga_session_hits"}

        sessions_class = MagicMock(return_value=sessions_instance)
        hits_class = MagicMock(return_value=hits_instance)

        client = MagicMock()
        client.list_tables.return_value = [
            SimpleNamespace(table_id="unrelated"),
            SimpleNamespace(table_id="ga_sessions_20200101"),
            SimpleNamespace(table_id="ga_sessions_20200102"),
        ]

        with patch.dict(
            tap_ga360.STREAMS,
            {"ga_sessions": sessions_class, "ga_session_hits": hits_class},
            clear=True,
        ), patch.dict(
            tap_ga360.SUB_STREAMS,
            {"ga_sessions": "ga_session_hits"},
            clear=True,
        ), patch("builtins.print") as mock_print:
            tap_ga360.discover(client, CONFIG)

        mock_print.assert_called_once()
        result = json.loads(mock_print.call_args[0][0])
        self.assertEqual(
            result,
            {"streams": [{"stream": "ga_sessions"}, {"stream": "ga_session_hits"}]},
        )
        client.list_tables.assert_called_once_with("project.dataset")
        self.assertEqual(sessions_class.call_count, 1)
        self.assertEqual(hits_class.call_count, 1)


class TestGetClient(unittest.TestCase):

    @patch("tap_ga360.bigquery.Client")
    @patch("tap_ga360.service_account.Credentials.from_service_account_info")
    def test_get_client_builds_credentials_and_bigquery_client(
        self, mock_from_info, mock_bq_client
    ):
        mock_from_info.return_value = "credentials"
        mock_bq_client.return_value = "client"

        result = tap_ga360.get_client(CONFIG)

        mock_from_info.assert_called_once_with({"project_id": "credentials-project"})
        mock_bq_client.assert_called_once_with("credentials-project", "credentials")
        self.assertEqual(result, "client")


class TestMain(unittest.TestCase):

    @patch("tap_ga360.discover")
    @patch("tap_ga360.get_client")
    @patch("tap_ga360.singer.utils.parse_args")
    def test_main_dispatches_to_discover(
        self, mock_parse_args, mock_get_client, mock_discover
    ):
        mock_parse_args.return_value = SimpleNamespace(
            config=CONFIG, discover=True, catalog=None, state={}
        )
        mock_get_client.return_value = "client"

        tap_ga360.main()

        mock_discover.assert_called_once_with("client", CONFIG)

    @patch("tap_ga360.sync")
    @patch("tap_ga360.get_client")
    @patch("tap_ga360.singer.utils.parse_args")
    def test_main_dispatches_to_sync(
        self, mock_parse_args, mock_get_client, mock_sync
    ):
        catalog = object()
        mock_parse_args.return_value = SimpleNamespace(
            config=CONFIG, discover=False, catalog=catalog, state={"x": 1}
        )
        mock_get_client.return_value = "client"

        tap_ga360.main()

        mock_sync.assert_called_once_with("client", catalog, {"x": 1}, CONFIG)

    @patch("tap_ga360.get_client")
    @patch("tap_ga360.singer.utils.parse_args")
    def test_main_does_nothing_when_no_discover_or_catalog(
        self, mock_parse_args, mock_get_client
    ):
        mock_parse_args.return_value = SimpleNamespace(
            config=CONFIG, discover=False, catalog=None, state={}
        )
        mock_get_client.return_value = "client"
        # Should complete without error
        tap_ga360.main()
