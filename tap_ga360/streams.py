import json
import os

from singer import (
    Transformer,
    get_bookmark,
    utils,
    write_bookmark,
    write_record,
    write_schema,
    write_state,
)
from singer.metadata import get_standard_metadata, to_map


def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)


class Stream:
    name = None
    replication_method = None
    replication_key = None
    key_properties = []

    def __init__(self, client=None, project_id=None, dataset_id=None, start_date=None):
        self.client = client
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.start_date = start_date
        self.schema = self.load_schema()

    def get_bookmark(self, state):
        bookmark = (
            get_bookmark(state, self.name, self.replication_key) or self.start_date
        )
        return utils.strptime_to_utc(bookmark)

    def update_bookmark(self, state, value):
        current_bookmark = self.get_bookmark(state)

        if value and utils.strptime_to_utc(value) > current_bookmark:
            write_bookmark(state, self.name, self.replication_key, value)

    def load_schema(self):
        schema_file = "schemas/{}.json".format(self.name)
        with open(get_abs_path(schema_file)) as f:
            schema = json.load(f)
        return schema

    def load_metadata(self):
        return get_standard_metadata(
            schema=self.schema,
            key_properties=self.key_properties,
            valid_replication_keys=[self.replication_key],
            replication_method=self.replication_method,
        )

    def catalog_entry(self):
        return {
            "stream": self.name,
            "tap_stream_id": self.name,
            "schema": self.schema,
            "metadata": self.load_metadata(),
        }

    def sync(self, state, metadata, page_size=None):
        bookmark = self.get_bookmark(state)

        tables = self.client.list_tables(
            "{}.{}".format(self.project_id, self.dataset_id)
        )

        new_table_id = "{}_{}".format(self.name, bookmark.strftime("%Y%m%d"))

        with Transformer() as transformer:
            for table in tables:
                if table.table_id <= new_table_id:
                    continue

                selected_fields = self.filter_fields(to_map(metadata), table)

                for row in self.client.list_rows(
                    table, page_size=page_size, selected_fields=selected_fields
                ):
                    record = transformer.transform(
                        dict(row.items()), self.schema, to_map(metadata)
                    )
                    write_record("ga_sessions", record, time_extracted=utils.now())

                date = table.table_id.replace("ga_sessions_", "")
                self.update_bookmark(state, date)
                write_state(state)

    def write_schema(self):
        write_schema(self.name, self.schema, self.key_properties)

    def filter_fields(self, metadata, table):
        """Return only the selected fields from the table schema."""
        schema = self.client.get_table(table).schema

        return [
            field
            for field in schema
            if metadata.get(("properties", field.name), {}).get("selected")
        ]


class GaSessions(Stream):
    name = "ga_sessions"
    replication_method = "INCREMENTAL"
    replication_key = "date"
    key_properties = ["fullVisitorId", "visitId", "visitStartTime"]


STREAMS = {"ga_sessions": GaSessions}
