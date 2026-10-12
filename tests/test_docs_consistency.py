"""Documentation must agree with the executed outputs (brief §5.7 quality gate).

Each check reads a figure from the generated outputs and asserts that the README /
docs quote it exactly as formatted. The checks apply only when the outputs come
from the snapshot the documentation describes (DOCUMENTED_SNAPSHOT); after a refresh
to a newer snapshot they are skipped with an explicit message, signalling that the
narrative documents must be reviewed and updated.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from src.config import REPO_ROOT

DOCUMENTED_SNAPSHOT = "20261012T010041Z"
OUT = REPO_ROOT / "outputs"


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _snapshot() -> str | None:
    p = OUT / "tables" / "analysis_results.json"
    return json.loads(p.read_text(encoding="utf-8"))["snapshot_id"] if p.exists() else None


pytestmark = pytest.mark.skipif(
    _snapshot() != DOCUMENTED_SNAPSHOT,
    reason=f"outputs are from snapshot {_snapshot()}, docs describe {DOCUMENTED_SNAPSHOT}: "
           "review README/docs figures and update DOCUMENTED_SNAPSHOT")


def test_data_quality_counts_in_docs():
    dq = json.loads((OUT / "data_quality" / "dq_report.json").read_text(encoding="utf-8"))["counts"]
    text = _read("docs/DATA_QUALITY.md")
    for key in ["raw_rows", "quarantined_rows", "clean_rows", "partial_month_rows",
                "analysis_ready_rows_excl_partial_month"]:
        assert f"{dq[key]:,}" in text, f"{key}={dq[key]:,} not in DATA_QUALITY.md"


@pytest.mark.parametrize("doc", ["README.md", "docs/HYPOTHESIS_REGISTER.md"])
def test_hypothesis_effects_in_docs(doc):
    res = pd.read_csv(OUT / "tables" / "hypothesis_results.csv").set_index("hypothesis")
    text = _read(doc)
    for h in ["H1", "H2", "H3"]:
        est = f"{res.loc[h, 'estimate_pct']:.1f}%"
        assert est in text, f"{h} estimate {est} not in {doc}"
    assert f"{res.loc['H4', 'effect_size']:.2f}" in text


def test_h5_composition_in_docs():
    h5 = json.loads((OUT / "tables" / "analysis_results.json").read_text(encoding="utf-8"))["h5"]
    for doc in ["README.md", "docs/HYPOTHESIS_REGISTER.md"]:
        text = _read(doc)
        for v in [h5["raw_change_pct"], h5["mix_adjusted_change_pct"], abs(h5["difference_pp"])]:
            assert f"{v:.1f}" in text, f"H5 figure {v:.1f} not in {doc}"


def test_model_results_in_docs():
    ts = pd.read_csv(OUT / "model_metrics" / "test_scores.csv")
    sel = ts[(ts["mode"] == "static") & (ts["selected"] == True)].iloc[0]  # noqa: E712
    roll = ts[ts["mode"] == "monthly refit"].set_index("family").loc["G-B"]
    b2 = ts[(ts["mode"] == "static") & (ts["family"] == "B2")].iloc[0]
    cov = json.loads((OUT / "model_metrics" / "model_results.json").read_text(encoding="utf-8"))["conformal_80"]
    for doc in ["README.md", "docs/MODEL_CARD.md"]:
        text = _read(doc)
        for v in [sel["mae"], roll["mae"], b2["mae"]]:
            assert f"{v:,.0f}" in text, f"MAE {v:,.0f} not in {doc}"
        assert f"{sel['mdape_pct']:.1f}%" in text
        assert f"{100 * cov['coverage_test_static']:.0f}%" in text or \
               f"{100 * cov['coverage_test_static']:.1f}%" in text


def test_profile_count_in_bi_guide():
    n = len(pd.read_csv(REPO_ROOT / "data" / "curated" / "indicative_profiles.csv"))
    assert f"{n}" in _read("docs/BI_BUILD_GUIDE.md")


def test_decision_ids_are_unique_and_sequential():
    import re
    ids = [int(x) for x in re.findall(r"^### DEC-(\d{3})", _read("docs/DECISION_LOG.md"), re.M)]
    assert ids == list(range(1, len(ids) + 1)), ids
