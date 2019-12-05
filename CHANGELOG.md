# Changelog

## 0.1.0
  * Make `ga_session_hits` its own streams to avoid `ga_sessions` records > 4 MB [#8](https://github.com/stitchdata/tap-ga360/pull/8)

## 0.0.8
  * FIX: Error when there are no new tables to extract. [#7](https://github.com/stitchdata/tap-ga360/pull/7)

## 0.0.7
  * FIX: Only consider tables from the BQ dataset conforming to the name pattern `ga_sessions_yyyymmdd`. [#6](https://github.com/stitchdata/tap-ga360/pull/6)

## 0.0.6
  * Update `filter_fields` to include fields with automatic inclusion [#5](https://github.com/stitchdata/tap-ga360/pull/5)
