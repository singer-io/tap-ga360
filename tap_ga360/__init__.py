from google.cloud import bigquery

import singer
import pprint

client = bigquery.Client.from_service_account_json(
    "/home/cmerrick/myserviceaccount-687aaf85c101.json"
)

dataset_id = 'bigquery-public-data.google_analytics_sample'


def fiddling_around():
    tables = client.list_tables(dataset_id)
    data_set = client.get_dataset(dataset_id)
    
    print("Tables contained in '{}':".format(dataset_id))

    for table in tables:
        full_table_name = "{}.{}.{}".format(table.project, table.dataset_id, table.table_id)
        break

    full_table = client.get_table(full_table_name)
#    pprint.pprint(full_table.schema)
    
    query = (
        "SELECT * FROM `bigquery-public-data.google_analytics_sample.{}`".format(table.table_id)
    )

    query_job = client.query(
        query,
        location=data_set.location
    )
    
    for row in query_job:
        m = singer.RecordMessage(
            stream='ga_sessions',
            record=dict(row.items()),
            version=0, # TODO
            time_extracted=singer.utils.now()
        )
        
        singer.write_message(m)
        break

        
def main():
    fiddling_around()

