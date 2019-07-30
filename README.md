
## Notes
 - I ran into [this issue](https://github.com/googleapis/google-cloud-python/issues/2990) running `pip install -e .` on a vanilla pip/python 3.5.7, running `pip install --upgrade pip` and `pip install --upgrade setuptools` solved it.
 - Development can be done against the [public GA360 example BQ dataset](https://bigquery.cloud.google.com/dataset/bigquery-public-data:google_analytics_sample?pli=1)
 
## Requirements
**Config**
 - It takes the following config params:
   - start_date - the default value to use if no bookmark exists for an endpoint (rfc3339 date string)
   - project_id - GCP BigQuery project ID
   - dataset_id - Dataset ID that Google Analytics 360 will exporting
   - TODO: whatever is needed for auth
 
**Replication**
 - On each invocation of the tap, all tables with name matching the format `ga_sessions_YYYYMMDD` are replicated one-at-a-time in ascending order (sorted lexicographically by table name) starting with the one corresponding to the YYYYMMDD of the start_date parameter, until there are no tables left to replicate.
 -- Unless a bookmark is found in the state, in which case replication will begin with the table corresponding to the bookmark value
 - The bookmark should be written to the state in the standard structure, as a `YYYYMMDD` string.
 - If the tap replicates only a part of a table during a run, during the next run it should start at the beginning of that same table
 - If the tap finds no new tables to replicate, it should complete successfully 
 
**Discovery and Field Selection**
 - If one or more tables matches the format `ga_sessions_YYYYMMDD`, discovery finds a single `ga_sessions` table, otherwise it finds nothing
 - The [documented GA360 schema](https://support.google.com/analytics/answer/3437719?hl=en&ref_topic=3416089) is hard-coded into the tap as the discovered schema for that table
   - It should specify fullVisitorId and visitId as the primary key of the table, and those fields should be required to be selected during field selection
   - See other taps for examples of the proper JSON schema for decimals, datetimes, and integers.
 - It supports field selection within the ga_sessions table
  
## Milestones
 - M1: Accepts proper config, runs replication without field selection or bookmarking
   - Emit correct schema and records, pipe into `target-stitch` using the dry run flag to confirm.
   - Accepts params from config file except ones related to auth
 - M2: Performance test replication against real data sets (to be completed by Stitch team)
 - M3: Add bookmarking
 - M4: Add discovery and field selection
 - M5: tap-tester tests against https://bigquery.cloud.google.com/dataset/bigquery-public-data:google_analytics_sample?pli=1
   - Do a sync, generate a state file w/ a bookmark, run a second sync with the state file and confirm the bookmark was correctly applied
  
## Questions
 - How can the service account JSON be passed in as params?
 - What metrics should be emitted?
