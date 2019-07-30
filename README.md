
## Notes
 - I ran into [this issue](https://github.com/googleapis/google-cloud-python/issues/2990) running `pip install -e .` on a vanilla pip/python 3.5.7, running `pip install --upgrade pip` and `pip install --upgrade setuptools` solved it.


## Requirements
 - If one or more tables matches the format `ga_sessions_YYYYMMDD`, discovery finds a single `ga_sessions` table, otherwise it finds nothing
 - The [documented GA360 schema](https://support.google.com/analytics/answer/3437719?hl=en&ref_topic=3416089) is hard-coded as the discovered schema for that table
 -- It should specify fullVisitorId and visitId as the primary key of the table, and those fields should be required to be selected during field selection
 -- See other taps for examples of the proper JSON schema for decimals, datetimes, and integers.
 - It supports field selection within the ga_sessions table
 - It takes the following config params:
  - start_date - the default value to use if no bookmark exists for an endpoint (rfc3339 date string)
  - project_id - GCP BigQuery project ID
  - dataset_id - Dataset ID that Google Analytics 360 will exporting
  - TODO: whatever is needed for auth
 - On each invocation of the tap, tables are replicated one-at-a-time in ascending order (sorted lexicographically by table name) starting with the one corresponding to the YYYYMMDD of the start_date parameter, until there are no tables left to replicate.
 -- Unless a bookmark is found in the state, in which case replication will begin with the table corresponding to the bookmark value
 -- The bookmark should be written to the state in the standard structure, as a `YYYYMMDD` string.
 -- If the tap replicates only a part of a table during a run, during the next run it should start at the beginning of that same table
   - If the tap finds no new tables to replicate, it should complete successfully 
  
## Milestones
 - M1: Replication without field selection or bookmarking
  - Emit correct schema and records, pipe into `target-stitch` using the dry run flag to confirm.
 - M2: Add bookmarking
 - M3: Add discovery and field selection
 - M4: tap-tester tests against https://bigquery.cloud.google.com/dataset/bigquery-public-data:google_analytics_sample?pli=1
  
## Questions
 - How can the service account JSON be passed in as params?
 - How to deal with table version? Activate table? Probably unnecessary
 - Are any fields required as part of field selection?
