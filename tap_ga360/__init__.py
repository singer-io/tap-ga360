import json

import singer
from google.cloud import bigquery
from google.oauth2 import service_account
from tap_ga360.streams import STREAMS, SUB_STREAMS

LOGGER = singer.get_logger()

REQUIRED_CONFIG_KEYS = {
    "start_date",
    "project_id",
    "dataset_id",
    "service_account_json",
}


def sync(client, catalog, state, config):
    for stream in catalog.get_selected_streams(state):
        LOGGER.info("Syncing stream:" + stream.tap_stream_id)
        instance = STREAMS[stream.tap_stream_id](
            client, config["project_id"], config["dataset_id"], config["start_date"]
        )
        instance.write_schema()
        instance.sync(state, stream.metadata, config.get("page_size"))


def discover(client, config):
    found = {stream: False for stream in STREAMS}
    streams = []
    tables = client.list_tables(
        "{}.{}".format(config["project_id"], config["dataset_id"])
    )

    for table in tables:
        for stream, stream_class in STREAMS.items():
            if not found[stream] and stream in table.table_id:
                instance = stream_class(
                    client,
                    config["project_id"],
                    config["dataset_id"],
                    config["start_date"],
                )
                streams.append(instance.catalog_entry())
                if SUB_STREAMS.get(stream):
                    sub_stream = SUB_STREAMS[stream]
                    sub_stream_class = STREAMS[sub_stream]
                    sub_stream_instance = sub_stream_class(
                        client,
                        config["project_id"],
                        config["dataset_id"],
                        config["start_date"],
                    )
                    streams.append(sub_stream_instance.catalog_entry())
                found[stream] = True

    print(json.dumps({"streams": streams}, indent=2))


def get_client(config):
    credentials_info = json.loads(config["service_account_json"])

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info
    )

    return bigquery.Client(credentials_info.get("project_id"), credentials)


@singer.utils.handle_top_exception(LOGGER)
def main():
    parsed_args = singer.utils.parse_args(REQUIRED_CONFIG_KEYS)

    client = get_client(parsed_args.config)

    if parsed_args.discover:
        discover(client, parsed_args.config)
    elif parsed_args.catalog:
        sync(client, parsed_args.catalog, parsed_args.state, parsed_args.config)


if __name__ == "__main__":
    main()
