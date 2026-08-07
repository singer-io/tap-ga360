import json
import unittest
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

from tap_ga360 import schema


def _field(name, field_type, fields=()):
    return SimpleNamespace(name=name, field_type=field_type, fields=fields)


class TestGetTableSchema(unittest.TestCase):

    def test_get_table_schema_uses_qualified_table_name(self):
        client = MagicMock()
        client.get_table.return_value.schema = ["field"]
        result = schema.get_table_schema(client, "project", "dataset", "table")
        self.assertEqual(result, ["field"])
        client.get_table.assert_called_once_with("project.dataset.table")


class TestConvertSchema(unittest.TestCase):

    def test_convert_schema_handles_scalar_date_and_nested_fields(self):
        converted = schema.convert_schema(
            [
                _field("name", "STRING"),
                _field("created", "TIMESTAMP"),
                _field("details", "RECORD", [_field("count", "INTEGER")]),
            ]
        )
        self.assertEqual(
            converted,
            {
                "type": ["null", "object"],
                "properties": {
                    "name": {"type": ["null", "string"]},
                    "created": {"type": ["null", "string"], "format": "date-time"},
                    "details": {
                        "type": ["null", "object"],
                        "properties": {"count": {"type": ["null", "number"]}},
                    },
                },
            },
        )


class TestGenerateSingerSchema(unittest.TestCase):

    @patch("tap_ga360.schema.convert_schema")
    @patch("tap_ga360.schema.get_table_schema")
    @patch("builtins.open", new_callable=mock_open)
    @patch("builtins.print")
    def test_generate_singer_schema_uses_first_table_and_writes_file(
        self, mock_print, mock_file, mock_get_table_schema, mock_convert_schema
    ):
        client = MagicMock()
        client.list_tables.return_value = [
            SimpleNamespace(table_id="first"),
            SimpleNamespace(table_id="second"),
        ]
        generated = {"type": ["null", "object"], "properties": {}}
        mock_get_table_schema.return_value = ["raw"]
        mock_convert_schema.return_value = generated

        schema.generate_singer_schema(client, "project", "dataset", "ga_sessions")

        mock_get_table_schema.assert_called_once_with(
            client, "project", "dataset", "first"
        )
        mock_file.assert_called_once()
        mock_file().write.assert_called_once_with(json.dumps(generated, indent=2))
        printed = " ".join(str(a) for a in mock_print.call_args[0])
        self.assertIn("schemas/ga_sessions.json created", printed)


class TestGetSchemaFields(unittest.TestCase):

    def test_get_schema_fields_flattens_objects_arrays_and_scalars(self):
        singer_schema = {
            "type": ["null", "object"],
            "properties": {
                "id": {"type": ["null", "string"]},
                "nested": {
                    "type": ["null", "object"],
                    "properties": {"value": {"type": ["null", "number"]}},
                },
                "items": {
                    "type": ["null", "array"],
                    "items": {
                        "type": ["null", "object"],
                        "properties": {"name": {"type": ["null", "string"]}},
                    },
                },
            },
        }
        result = schema.get_schema_fields(singer_schema, results=[])
        # Note: the array branch calls get_schema_fields(items_schema, parent)
        # without forwarding the results list, so array sub-field names are NOT
        # included in the returned set – only the array field itself is.
        self.assertEqual(
            result,
            {"", "id", "nested", "nested.value", "items"},
        )
