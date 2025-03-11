# Changelog

## 0.2.2
  * Update google-cloud-bigquery version [#7](https://github.com/singer-io/tap-ga360/pull/7)

## 0.2.1
  * Pinnumpy version to avoid compatibility errors [#6](https://github.com/singer-io/tap-ga360/pull/6)

## 0.2.0
  * Update singer-python version and google-cloud-bigquery version [#3](https://github.com/singer-io/tap-ga360/pull/3)

## 0.1.1
  * Rework the `ga_session_hits` stream to query via query string in order to get all results

## 0.1.0
  * Make `ga_session_hits` its own streams to avoid `ga_sessions` records > 4 MB [#8](https://github.com/stitchdata/tap-ga360/pull/8)

## 0.0.8
  * FIX: Error when there are no new tables to extract. [#7](https://github.com/stitchdata/tap-ga360/pull/7)

## 0.0.7
  * FIX: Only consider tables from the BQ dataset conforming to the name pattern `ga_sessions_yyyymmdd`. [#6](https://github.com/stitchdata/tap-ga360/pull/6)

## 0.0.6
  * Update `filter_fields` to include fields with automatic inclusion [#5](https://github.com/stitchdata/tap-ga360/pull/5)
