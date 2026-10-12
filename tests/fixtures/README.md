# Test fixtures — SYNTHETIC DATA

Every file in this folder is **synthetic test data written by hand for unit tests**.
None of it is real HDB transaction data. Never mix it with `data/` outputs.

`synthetic_resale_sample.csv` mimics the source schema (11 columns, all text) and
deliberately contains edge cases, one per row where possible:

| Rows | Purpose |
|------|---------|
| 1-6 | Valid rows in the three observed `remaining_lease` formats |
| 7-8 | Genuine-looking exact duplicate (2019, price 500,000) - must be kept |
| 9-10 | 2017 exact duplicate at 470,000 - second copy must go to the exception report (Q07) |
| 11 | Blank resale_price -> quarantine Q01 |
| 12 | Non-numeric floor area "ninety" -> quarantine Q05 |
| 13 | Invalid month "2019-13" -> quarantine Q02 |
| 14 | Month before coverage (2016-12) -> quarantine Q03 |
| 15 | Unparseable remaining lease -> kept, flagged |
| 16 | Untrimmed whitespace and lower-case town -> normalised |
| 17 | Floor area 15 sqm -> kept, flagged implausible |
| 18 | Remaining lease inconsistent with lease start year -> kept, flagged |
| 19 | Partial month (2026-10, same as the fixture retrieval month) -> kept, flagged |
| 20 | flat_model lower-case variant "model a" -> unified to "Model A" |
