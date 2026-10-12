# HDB Resale Market Intelligence & Price Prediction

> **Project status: in progress (Phases 0–2 of 6 complete: source verified, data-quality pipeline, exploratory analysis and pre-registered hypothesis tests).** Modelling (Phase 3) and Power BI (Phase 4) are not yet built. This README is rewritten as each phase completes.

An end-to-end data analytics capstone that turns Singapore HDB resale transaction records into explainable price intelligence. It covers market trends, fair comparisons between flats, the evidence on which characteristics are associated with price differences, and an honestly evaluated price-estimation model, all delivered through a reproducible Python/SQL pipeline and a Power BI report.

**Data source:** "Resale flat prices based on registration date from Jan-2017 onwards", Housing & Development Board, via [data.gov.sg](https://data.gov.sg/datasets/d_8b84c4ee58e3cfc0ece0d773c8ca6abc/view), under the [Singapore Open Data Licence v1.0](https://data.gov.sg/open-data-licence). This is an independent project, not endorsed by HDB or the Singapore Government. See [DATA_LICENSE.md](DATA_LICENSE.md).

See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) for scope and plan, and [docs/DECISION_LOG.md](docs/DECISION_LOG.md) for design decisions.

## Findings so far (Phase 2, snapshot of 12 Oct 2026)

All findings describe **associations in observational data**, not causes. Full evidence, methods and caveats are in [docs/HYPOTHESIS_REGISTER.md](docs/HYPOTHESIS_REGISTER.md). Hypotheses, methods and a 2% practical-significance threshold were [committed before testing](docs/HYPOTHESIS_REGISTER.md#0-pre-registration-statement).

| Question | Finding | Evidence |
|---|---|---|
| How have prices moved? | The median resale price rose from SGD 410,000 (2017) to SGD 630,000 (Oct 2025 – Sep 2026), **+53.7%**. | 241,557 analysis-ready transactions |
| Is that the true change for comparable flats? | No. Holding town, type, model, area, storey and lease fixed, prices rose **+57.4%**. The raw median *understates* growth by 3.7 points, which is consistent with the flats being sold getting older. That explanation is an interpretation, not a separate test. | Hedonic time-dummy index; the CIs of the two estimates do not overlap |
| Higher floors? | **+7.8%** per 10 floors for otherwise comparable flats (95% CI 7.5–8.0%). Raw medians exaggerate this because tall blocks cluster in pricier towns. | Supported, robust across 4 specifications |
| Remaining lease? | **+10.6%** per 10 extra years (CI 10.3–10.9%), steepest below about 60 years remaining. The figure mixes lease length with building age and condition. | Supported, robust |
| Floor area within a flat type? | **+9.3%** per extra 10 sqm (CI 8.9–9.7%) | Supported, robust |
| Does town matter for like-for-like flats? | Strongly. Median 4-ROOM prices range from SGD 537,500 (Jurong West) to SGD 1.2m (Central Area). After controls, town effects still span about 61 percentage points. | Kruskal–Wallis ε² = 0.42 (large) |

![Raw vs mix-adjusted price index](outputs/figures/03_raw_vs_mix_adjusted_index.png)
![Storey: raw vs adjusted](outputs/figures/07_storey_raw_vs_adjusted.png)

More figures are in [outputs/figures](outputs/figures). The data-quality results are in [docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).
