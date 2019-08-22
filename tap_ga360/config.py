import json
from argparse import ArgumentParser
from pathlib import Path


def get_args():
    args = ArgumentParser()
    args.add_argument("--config", help="Path to configuration json file to modify")
    args.add_argument(
        "--creds", help="Path to Google service account credentials json file"
    )

    return args.parse_args()


def write_config(config_path, creds_path):
    """Take google json and convert it to a string in the credentials key in
    config.json."""
    with Path(creds_path).expanduser().open() as creds_file:
        creds = json.load(creds_file)

    with Path(config_path).expanduser().open("r+") as config_file:
        config = json.load(config_file)
        config["credentials"] = json.dumps(creds)
        config_file.seek(0)
        json.dump(config, config_file, indent=2)


if __name__ == "__main__":
    args = get_args()
    write_config(args.config, args.creds)
