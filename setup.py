#!/usr/bin/env python

from setuptools import setup

setup(
    name="tap-ga360",
    version="0.2.1",
    description="Singer.io tap for extracting data from Google Analytics 360 via BigQuery",
    author="Stitch",
    url="https://singer.io",
    classifiers=["Programming Language :: Python :: 3 :: Only"],
    py_modules=["tap_ga360"],
    install_requires=["google-cloud-bigquery==3.3.5", "singer-python==5.12.2", "numpy==1.26.4"],
    extras_require={
        'dev': [
            'pylint',
            'ipdb'
        ]
      },
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
