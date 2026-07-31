"""Base test class for tap-ga360 mock-integration tests.

Not a TestCase itself — mix with unittest.TestCase in each test class to provide common fixtures, helpers, and mock factories.
"""
import json
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import singer
from singer import metadata
from singer.catalog import Catalog, CatalogEntry, Schema


class Ga360BaseTest:
    """Base mixin for tap-ga360 mock integration tests.

    Subclass alongside unittest.TestCase:

        class MyTest(Ga360BaseTest, unittest.TestCase):
            ...
    """

    # ── Metadata constants ───────────────────────────────────────────────
    PRIMARY_KEYS = "primary_keys"
    REPLICATION_METHOD = "replication_method"
    REPLICATION_KEYS = "replication_keys"
    OBEYS_START_DATE = "obeys_start_date"

    INCREMENTAL = "INCREMENTAL"
    FULL_TABLE = "FULL_TABLE"

    default_start_date = "2020-01-01T00:00:00Z"

    # ── Stream metadata ──────────────────────────────────────────────────

    @classmethod
    def expected_metadata(cls):
        """The expected streams and their metadata."""
        return {
            "ga_sessions": {
                cls.PRIMARY_KEYS: {"fullVisitorId", "visitId", "visitStartTime"},
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"date"},
                cls.OBEYS_START_DATE: True,
            },
            "ga_session_hits": {
                cls.PRIMARY_KEYS: {
                    "fullVisitorId",
                    "visitId",
                    "visitStartTime",
                    "hitNumber",
                },
                cls.REPLICATION_METHOD: cls.INCREMENTAL,
                cls.REPLICATION_KEYS: {"date"},
                cls.OBEYS_START_DATE: True,
            },
        }

    @classmethod
    def expected_stream_names(cls):
        """Return the set of all expected stream names."""
        return set(cls.expected_metadata().keys())

    @classmethod
    def incremental_streams(cls):
        """Return all streams that use INCREMENTAL replication."""
        return {
            name
            for name, meta in cls.expected_metadata().items()
            if meta[cls.REPLICATION_METHOD] == cls.INCREMENTAL
        }

    @classmethod
    def full_table_streams(cls):
        """Return all streams that use FULL_TABLE replication."""
        return {
            name
            for name, meta in cls.expected_metadata().items()
            if meta[cls.REPLICATION_METHOD] == cls.FULL_TABLE
        }

    # ── Test setup / teardown ────────────────────────────────────────────

    def setUp(self):
        """Set up test fixtures with dummy config and empty state."""
        self.config = self.get_mock_config()
        self.state = self.get_mock_state()

    def tearDown(self):
        """Clean up after tests."""
        self.state = {}

    # ── Config helpers ───────────────────────────────────────────────────

    @staticmethod
    def get_mock_config():
        """Return mock configuration with dummy values — no real credentials."""
        return {
            "start_date": "2020-01-01T00:00:00Z",
            "project_id": "test-project",
            "dataset_id": "test_dataset",
            "service_account_json": json.dumps({"project_id": "test-project"}),
        }

    @staticmethod
    def get_mock_state():
        """Return initial empty mock state."""
        return {}

    # ── Schema helpers ───────────────────────────────────────────────────

    @staticmethod
    def _schema_path(stream_name):
        """Resolve the absolute path of a stream's JSON schema file."""
        tap_dir = os.path.join(os.path.dirname(__file__), "..", "tap_ga360")
        return os.path.join(tap_dir, "schemas", "{}.json".format(stream_name))

    @classmethod
    def _load_schema(cls, stream_name):
        """Load and return the JSON schema dict for a stream."""
        with open(cls._schema_path(stream_name)) as f:
            return json.load(f)

    @staticmethod
    def _resolve_type(schema):
        """Return the concrete type, resolving null unions."""
        t = schema.get("type", "string")
        if isinstance(t, list):
            non_null = [x for x in t if x != "null"]
            return non_null[0] if non_null else "string"
        return t

    @classmethod
    def _generate_value(cls, schema, date_value="2024-01-01T00:00:00Z"):
        """Recursively generate one valid mock value for a JSON Schema fragment."""
        t = cls._resolve_type(schema)
        if t == "object":
            return {
                key: cls._generate_value(val, date_value)
                for key, val in schema.get("properties", {}).items()
            }
        if t == "array":
            item_schema = schema.get("items", {"type": "string"})
            return [cls._generate_value(item_schema, date_value)]
        if t == "string":
            return date_value if schema.get("format") == "date-time" else "mock_value"
        if t in ("number", "integer"):
            return 1
        if t == "boolean":
            return True
        return None

    @classmethod
    def _generate_stream_record(cls, stream_name, date_value="2024-01-01T00:00:00Z"):
        """Generate one schema-valid mock record for the given stream."""
        schema = cls._load_schema(stream_name)
        record = cls._generate_value(schema, date_value)
        # Ensure primary key and replication key fields are always present
        meta = cls.expected_metadata().get(stream_name, {})
        for key in meta.get(cls.PRIMARY_KEYS, set()):
            if key not in record:
                record[key] = "mock_pk"
        for key in meta.get(cls.REPLICATION_KEYS, set()):
            if key not in record:
                record[key] = date_value
        return record

    # ── BigQuery client mock factory ─────────────────────────────────────

    @staticmethod
    def _make_table(table_id, full_table_id=None):
        """Build a lightweight mock BigQuery table reference."""
        t = SimpleNamespace(
            table_id=table_id,
            full_table_id=full_table_id or "test-project:test_dataset.{}".format(table_id),
        )
        return t

    @classmethod
    def _make_mock_client(cls, tables=None, rows=None, hits_rows=None):
        """Build a mock BigQuery client.

        Args:
            tables: list of table_id strings to expose via list_tables().
            rows: list of dicts/row-mocks to return from list_rows().
            hits_rows: list of dicts/row-mocks to return from query().result().
        """
        if tables is None:
            tables = ["ga_sessions_20200101", "ga_sessions_20200102"]

        client = MagicMock()
        client.list_tables.return_value = [cls._make_table(t) for t in tables]

        if rows is not None:
            mock_rows = []
            for r in rows:
                row_mock = MagicMock()
                row_mock.items.return_value = list(r.items())
                mock_rows.append(row_mock)
            client.list_rows.return_value = mock_rows

        if hits_rows is not None:
            mock_hit_rows = []
            for r in hits_rows:
                row_mock = MagicMock()
                row_mock.items.return_value = list(r.items())
                mock_hit_rows.append(row_mock)
            client.query.return_value.result.return_value = mock_hit_rows

        # Default schema on get_table (all stream fields selected automatically)
        client.get_table.return_value.schema = []
        return client

    @classmethod
    def _make_catalog(cls):
        """Return a Singer Catalog with both streams fully selected."""
        from tap_ga360.streams import STREAMS

        entries = []
        for stream_name, stream_class in STREAMS.items():
            instance = stream_class(
                MagicMock(), "test-project", "test_dataset", cls.default_start_date
            )
            schema = instance.schema
            meta = metadata.get_standard_metadata(
                schema=schema,
                key_properties=instance.key_properties,
                valid_replication_keys=[instance.replication_key],
                replication_method=instance.replication_method,
            )
            mdata_map = metadata.to_map(meta)
            mdata_map[()]["selected"] = True
            for breadcrumb in mdata_map:
                if breadcrumb != ():
                    mdata_map[breadcrumb]["selected"] = True
            entries.append(
                CatalogEntry(
                    stream=stream_name,
                    tap_stream_id=stream_name,
                    schema=Schema.from_dict(schema),
                    key_properties=instance.key_properties,
                    metadata=metadata.to_list(mdata_map),
                )
            )
        return Catalog(entries)
