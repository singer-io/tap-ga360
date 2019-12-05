#!/usr/bin/env python

from setuptools import setup

setup(
    name="tap-ga360",
    version="0.1.0",
    description="Singer.io tap for extracting data from Google Analytics 360 via BigQuery",
    author="Stitch",
    url="https://singer.io",
    classifiers=["Programming Language :: Python :: 3 :: Only"],
    py_modules=["tap_ga360"],
    install_requires=["google-cloud-bigquery==1.17.0", "singer-python==5.8"],
    entry_points="""
          [console_scripts]
          tap-ga360=tap_ga360:main
      """,
    packages=["tap_ga360"],
    package_data = {
        "schemas": ["tap_ga360/schemas/*.json"]
    },
    include_package_data=True,
)
