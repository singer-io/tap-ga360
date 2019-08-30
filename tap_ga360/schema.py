import json
import os

TYPE_MAP = {
    "STRING": "string",
    "BYTES": "string",
    "INTEGER": "number",
    "INT64": "number",
    "FLOAT": "number",
    "FLOAT64": "number",
    "BOOLEAN": "boolean",
    "BOOL": "boolean",
    "TIMESTAMP": "string",
    "DATE": "string",
    "TIME": "string",
    "DATETIME": "string",
    "RECORD": "object",
    "STRUCT": "object",
}

NESTED_TYPES = ["RECORD", "STRUCT"]
DATE_TYPES = ["DATE", "DATETIME", "TIMESTAMP"]


def get_table_schema(client, project_id, dataset_id, table_id):
    return client.get_table(".".join([project_id, dataset_id, table_id])).schema


def convert_schema(schema):
    converted_schema = {"properties": {}, "type": ["null", "object"]}
    for field in schema:
        if field.field_type in NESTED_TYPES:
            converted_schema["properties"][field.name] = convert_schema(field.fields)
        else:
            schema = {"type": ["null", TYPE_MAP[field.field_type]]}
            if field.field_type in DATE_TYPES:
                schema["format"] = "date-time"
            converted_schema["properties"][field.name] = schema

    return converted_schema


def generate_singer_schema(client, project_id, dataset_id, stream):
    for table in client.list_tables("{}.{}".format(project_id, dataset_id)):
        # just fetch first table to get the schema
        break

    schema = get_table_schema(client, project_id, dataset_id, table.table_id)
    singer_schema = convert_schema(schema)
    parent_dir = os.path.dirname(__file__)
    fname = "schemas/{}.json".format(stream)
    with open(os.path.join(parent_dir, fname), "w") as f:
        f.write(json.dumps(singer_schema, indent=2))
    print(
        "{} created\n".format(fname),
        "You will likely want to review the schema to ensure it's correct. Keep ",
        "an eye out for `object` types that might need to be `array` instead.",
    )


def get_schema_fields(schema, parent="", results=[]):
    """get set of flattened schema fields."""
    if "object" in schema["type"]:
        for key, val in schema["properties"].items():
            get_schema_fields(val, parent + "." + key, results)
    elif "array" in schema["type"]:
        get_schema_fields(schema["items"], parent)

    results.append(parent.strip("."))

    return set(results)
