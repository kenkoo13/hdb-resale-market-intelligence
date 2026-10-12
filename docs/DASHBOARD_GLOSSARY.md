# Dashboard Glossary and Wording Audit

The Power BI report is written for managers and business owners without a statistics background. This page is the **single reference for dashboard wording**. It maps every plain-language term to the technical term used in the analysis documents, so the report, README and technical documents stay consistent.

**Wording rule (DEC-030):** every label answers at least one of three questions: *What am I looking at? What does it mean? Why should I care?* Only displayed text changed. No calculation, measure, data or model logic was altered.

## 1. Glossary: plain term ↔ technical term

| Dashboard term | What it means (plain English) | Why it matters | Technical term (docs) |
|---|---|---|---|
| **Typical price (median)** | The middle price: half of the flats sold for more, half for less | More representative than an average, which a few very expensive flats can pull up | Median resale price |
| **Low end / High end** | Half of all sales fall between these two prices | Shows how widely prices vary, not just the middle | 25th / 75th percentile (P25 / P75) |
| **Price per sqm** | Price divided by floor area | Compares flats of different sizes; compare within the same flat type | Median price per square metre |
| **Flats sold** | Number of registered resale transactions | Shows how much evidence sits behind a price | Transactions, n |
| **Enough sales?** | "Too few (under 30)" warns that a figure rests on very few sales | Treat those figures with caution | Low-sample flag (n < 30) |
| **Last 12 months / previous 12 months** | The latest 12 complete months, and the 12 before them | The incomplete current month is left out so it doesn't distort trends | Latest / prior 12 full months |
| **Price change vs previous 12 months** | Change in the typical price between the two periods | Also moves when a different mix of flats is sold (see like-for-like) | Raw median YoY % |
| **Headline price trend** | Typical price of all flats sold each month | Easy to read, but affected by which flats happened to sell | Raw median index |
| **Like-for-like price trend** | Price change for the same kind of flat (same town, type, design, size, floor and lease) | The fairer measure of whether prices really rose | Mix-adjusted (hedonic time-dummy) index |
| **Similar flats / otherwise alike** | A comparison that holds other characteristics constant | Isolates the effect of one factor (for example, floor level) | Hedonic regression, controlling for other variables |
| **Extra paid for higher floors / more lease** | Price difference compared with the lowest floors or shortest lease, for similar flats | Shows how much buyers pay for each feature | Adjusted premium vs reference band |
| **Town price level vs Ang Mo Kio** | How much more or less a similar flat costs in each town, compared with Ang Mo Kio | Location is the biggest single price factor | Town fixed effect vs reference town |
| **Size of effect** | How big the price difference is | A finding can be certain but too small to matter; this shows the size | Effect size / point estimate |
| **Likely range** | The range the true effect very probably lies in | Narrow range = precise evidence | 95% confidence interval |
| **Evidence: Strong evidence** | The pattern is clear and large enough to matter, judged against a size threshold set before testing (for example, at least 2% of price) | Safe to rely on as a pattern in past sales | Hypothesis "Supported"; H5 "Material composition effect" |
| **Not necessarily causes** | The data shows patterns, not proof that one thing causes another | Unmeasured factors (exact location, condition, views) also affect price | Association, not causation |
| **Average prediction error (SGD)** | On average, how far estimates were from the actual price, in dollars | The expected size of a miss | Mean absolute error (MAE) |
| **Typical error (%)** | Half of all estimates were closer than this percentage | Easy to apply to any price: 3% of SGD 600,000 is about SGD 18,000 | Median absolute percentage error (MdAPE) |
| **Model not updated / updated monthly** | Model built once vs rebuilt every month with the newest sales | Monthly updates keep accuracy steady | Static vs monthly-refit evaluation |
| **Simple benchmark (recent typical price)** | Estimating a flat at the typical price of its town and flat type over the past year | The "rule of thumb" a model must beat to be useful | Baseline B2 |
| **Reduction in prediction error** | How much smaller the chosen model's error is than the simple benchmark's | Shows the value the model adds | 1 − MAE(model) / MAE(B2) |
| **Chosen model** | The approach selected for the most accurate estimates | — | Gradient boosting with street encoding (G-B) |
| **Simple formula model** | A straightforward pricing formula (adds up the value of each feature) | Easier to explain, but less accurate here | Ridge regression (L-A / L-B) |
| **Advanced model, no street detail** | The chosen approach without street-level location | Shows how much street detail helps | Gradient boosting, feature set A (G-A) |
| **Over/under (%)** | Whether estimates tend to be too high (+) or too low (−) for a group | Flags groups where estimates are systematically off | Median bias % |
| **Reliable?: Yes / Few sales** | Whether a group had at least 30 sales to test against | Small groups give shaky accuracy figures | Reliability label (n ≥ 30) |
| **Sales tested** | Number of past sales the model was checked against | More sales = more trustworthy accuracy figures | Test n |
| **Accuracy lost without it** | How much worse estimates get if the model can't use this factor | Shows which factors the model leans on, not what causes prices | Permutation importance (SGD) |
| **Price level: Cheapest 20% … Most expensive 20%** | Sales split into five equal groups by actual price | Shows whether cheap or expensive flats are harder to estimate | Price quintile |
| **Estimated price (profile)** | The model's estimate for a typical flat of that town and type | A guide to typical prices, not a valuation | Pre-computed profile prediction |
| **Recent typical price** | The actual median price of such flats sold in the last 12 months | Real-world check beside each estimate | Segment median, latest 12 months |
| **Reliability: Normal / Lower** | Lower = that flat type or floor level is rarely sold in that area | Estimates for rarely sold flats are less dependable | Profile reliability label |

## 2. Wording audit: before → after (by page)

### Page names
| Before | After |
|---|---|
| 1 Market overview / 2 Town & property / 3 Price drivers & evidence / 4 Model performance / 5 Indicative estimates | 1 Market overview / 2 Compare towns & flats / 3 What drives prices / 4 Estimate accuracy / 5 Estimated prices |

### Page 1: Market overview
| Element | Before | After | Issue fixed |
|---|---|---|---|
| Page header | Executive market overview: HDB resale prices and volumes (indicative, not official valuations) | Market overview: how are HDB resale prices and sales changing? | Framed as the business question |
| KPI | Median price, latest 12 months | Typical price (median), last 12 months | "Median" explained |
| KPI | Change vs prior 12 months (raw) | Price change vs previous 12 months | "raw" was jargon; the caveat moved to the table title |
| KPI | Transactions, latest 12 months | Flats sold, last 12 months | Business word |
| KPI | Median SGD per sqm, latest 12m | Typical price per sqm, last 12 months | Abbreviation removed |
| Chart | Median resale price by month (full months only) | Typical resale price each month | Simpler; the coverage line explains complete months |
| Chart | Transactions per month (partial month excluded) | Flats sold each month | Same |
| Chart | Median price by flat type, latest 12 months (hover for n) | Typical price by flat type, last 12 months (hover for number sold) | "n" explained |
| Table title | Latest vs prior 12 months (raw medians include mix changes) | This year vs last year (changes also reflect which flats were sold) | Explains "mix" plainly |
| Table headers | Sales (12m) / Median (12m) / YoY % (raw) | Flats sold / Typical price / Change vs last year | Abbreviations removed |
| Coverage line | Data: 2017-01 to 2026-09 (full months). Partial month excluded from trends: 2026-10. Retrieved … | Data covers Jan 2017 to Sep 2026 (complete months). Oct 2026 is still being recorded and is left out of trends. Data downloaded 12 Oct 2026, 09:00 SGT. | Readable dates; explains *why* |

### Page 2: Compare towns & flats
| Element | Before | After |
|---|---|---|
| Page header | Town and property comparison: compare like with like, and always check the sample size | Compare towns and flats: what do similar flats sell for? |
| Filter | Floor area band (sqm) | Flat size (sqm) |
| Table title | By town, latest 12 full months (P25 to P75 = middle half of prices) | Prices by town, last 12 months (half of all sales fall between Low end and High end) |
| Table headers | Sales (12m) / Median / P25 / P75 / Median $/sqm / Sample (values OK / Low sample (n<30)) | Flats sold / Typical price / Low end / High end / Price per sqm / Enough sales? (values Yes / Too few (under 30)) |
| Chart | Median price by storey (raw; mixes towns); axis "01 TO 03" | Typical price by floor level (all towns combined); axis "Floors 1-3" |
| Chart | Median price by remaining lease (raw) | Typical price by years of lease left |

### Page 3: What drives prices
| Element | Before | After |
|---|---|---|
| Page header | Price drivers and statistical evidence: associations in observational data, not causes | What drives price differences? Comparing otherwise similar flats |
| Table title | Pre-registered hypotheses: % price difference for the stated contrast (H5: raw minus mix-adjusted change) | Key findings: price differences between flats that are otherwise alike |
| Table headers | ID / Question / Estimate (%; H5 pp) / 95% CI low / 95% CI high / Effect size (H4 ε²) / Result | Question / What the data shows / Size of effect / Likely range / Evidence |
| Table values | H1 … H5; 7.8; 7.5; 8.0; 0.42; "Supported" | "Do higher floors sell for more?" · "10 floors higher: about 7.8% more" · "+7.8%" · "7.5% to 8.0%" · "Strong evidence". These are generated from the same numbers. |
| Chart | Raw vs mix-adjusted index (2017 = 100); legend Raw median / Mix-adjusted | Headline vs like-for-like price trend (2017 = 100); legend Headline (all sales) / Like-for-like flats |
| Chart | Adjusted storey premium vs floors 01-03 (axis "04 TO 06"...) | Extra paid for higher floors (vs floors 1-3) (axis: floor number) |
| Chart | Adjusted lease premium vs 35-39 years | Extra paid for more lease left (vs 35-39 years) |
| Chart | Adjusted town effect vs Ang Mo Kio | Town price level vs Ang Mo Kio (similar flats) |
| Note | Adjusted = hedonic regression … Unobserved factors … can confound every estimate | How to read: each result compares flats that are alike … patterns in past sales, not proof of cause … |

### Page 4: Estimate accuracy
| Element | Before | After |
|---|---|---|
| Page header | Model performance and reliability: test year evaluated once; estimates are indicative | How accurate are the price estimates, and where are they less reliable? |
| KPI | Selected model MAE (trained once) | Average prediction error (SGD) |
| KPI | Typical % error (median) | Typical error (%) |
| KPI | MAE if retrained monthly | Average error with monthly updates |
| KPI | Baseline MAE (town x type, 12m) | Error using a simple benchmark |
| KPI | Error removed vs baseline | Reduction in prediction error |
| Chart | Test-year MAE by model (SGD; lower is better); bars "Selected: gradient boosting (trained once)", "Ridge regression + street"… | Prediction accuracy by approach (lower error is better); bars "Chosen model (not updated)", "Simple formula model + street"… |
| Chart | Does accuracy fade? Test MAE by month; legend Trained once / Retrained monthly / Baseline B2 | Does prediction accuracy worsen over time? (average error by month); legend Model not updated / Model updated monthly / Simple benchmark |
| Filter | Error breakdown by (values flat_model, price_quintile…) | Break down by (values Flat model, Price level…) |
| Table title | Errors by segment (choose a segment on the left) | Where are predictions less accurate? (choose a grouping on the left) |
| Table headers / values | Segment / Level / Test sales / MAE (SGD) / Typical % error / Bias % (+ = over) / Reliability; "Q1 (lowest)", "01 TO 03", "ok" | Group / Sales tested / Average error / Typical error (%) / Over/under (%) (the title explains that + means estimates too high) / Reliable?; "Cheapest 20%", "Floors 1-3", "Yes" / "Few sales" |
| Chart | What the model relies on (not causes); "MAE increase" | Which factors influence predictions (not necessarily causes); "Accuracy lost without it" |
| Note | Test year = last 12 full months, never used for model choices. 80% prediction intervals failed their coverage check (65% actual) … | How we tested: the model estimated the latest 12 months of sales without seeing them. Average error = … Typical error (%) = … Price ranges are not shown: in testing they captured only 65% of actual prices instead of the intended 80%. |

### Page 5: Estimated prices
| Element | Before | After |
|---|---|---|
| Page header | Indicative price estimates for typical flat profiles: pre-computed, not a valuation | Estimated prices for typical flats (for guidance only, not a valuation) |
| Table title | Typical profile per town and flat type (median area and lease, most common model and street), three storey levels | Estimated price of a typical flat in each town and flat type, at three floor levels |
| Table headers | Type / Storey / Model / Area (sqm) / Lease left (yrs) / Estimate (SGD) / Typical error % / ± SGD / Segment median (12m) | Flat type / Floor level / Flat model / Size (sqm) / Lease left (years) / Estimated price / Typical error (%) / Typical error (SGD) / Recent typical price |
| Values | "High (13 TO 15)"; reliability "Typical" / "Less reliable: storey band rarely sold in this segment" | "High floor (13-15)"; reliability "Normal" / "Lower: this floor level is rarely sold here" |
| Note | How to read … computed in Python in advance; changing a slicer filters the table … | How to read: each row describes a typical flat … Estimates were calculated in advance: filters only narrow the list, they do not recalculate prices … |

## 3. Terminology decision: "average" vs "typical" error

The dashboard reports two accuracy figures:
- **Average prediction error (SGD)** is a *mean* of the dollar gaps (MAE).
- **Typical error (%)** is a *median* of the percentage gaps (MdAPE).

The review brief suggested "Typical prediction error (SGD)" for the first figure. It was worded **"average"** instead, so that:
- (a) the label describes the calculation accurately;
- (b) the two KPIs are not mistaken for the same number in different units.

Each is defined in one sentence on page 4.

## 4. Unchanged by design

- **Proper names and HDB categories:** town names, flat types (4 ROOM, EXECUTIVE) and flat model names (Model A, DBSS) are HDB's own terms. Business users searching for a flat will recognise them.
- **SGD and sqm:** standard units, kept.
- **Model and DAX measure names in the field list** (for example `Median Price Latest 12M`) are technical identifiers for report builders. Visuals show the plain-language display names above. The calculations and measure names are unchanged, so the DAX validation (BI_BUILD_GUIDE §4) still applies.
