"""Tests for the BI layer: SQL star schema, SQL-vs-pandas cross-check, DAX expected values,
and consistency of the generated PBIP (every visual field must exist in the model).
SQL tests use SYNTHETIC data; PBIP tests read the generated project in powerbi/."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analytics.descriptive import add_bands
from src.analytics.hedonic import add_lease_band
from src.config import REPO_ROOT
from src.reporting import build_bi_tables as B
from src.reporting import build_pbip as P

PBIP_ROOT = REPO_ROOT / "powerbi"


def synthetic_clean(n_months: int = 30, per_month: int = 40, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.date_range("2023-01-01", periods=n_months, freq="MS")
    n = n_months * per_month
    df = pd.DataFrame({
        "source_row_number": np.arange(1, n + 1), "month_date": np.repeat(months, per_month),
        "town": rng.choice(["BEDOK", "YISHUN"], n), "flat_type": rng.choice(["3 ROOM", "4 ROOM"], n),
        "flat_model": "Model A", "storey_range": rng.choice(["01 TO 03", "10 TO 12"], n),
        "floor_area_sqm_num": rng.choice([49.9, 50.0, 69.99, 70.0, 149.9, 150.0, 92.0], n),
        "remaining_lease_years": rng.choice([44.99, 45.0, 70.25, 95.0], n),
        "lease_commence_year": 1990.0, "resale_price_sgd": rng.integers(300, 900, n) * 1000.0,
    })
    df["storey_lower"] = df["storey_range"].str[:2].astype(int)
    df["storey_mid"] = df["storey_lower"] + 1.0
    df["price_per_sqm_sgd"] = df["resale_price_sgd"] / df["floor_area_sqm_num"]
    df["is_partial_month"] = df["month_date"] == months[-1]
    df["month"] = df["month_date"].dt.strftime("%Y-%m")
    return df


@pytest.fixture(scope="module")
def sql_env():
    clean = synthetic_clean()
    con = B.build_sqlite(clean)
    yield clean, con
    con.close()


def test_fact_rows_and_bands_match_python(sql_env):
    clean, con = sql_env
    fact = pd.read_sql("SELECT * FROM fact_transactions ORDER BY txn_id", con)
    assert len(fact) == len(clean)
    py = add_lease_band(add_bands(clean)).sort_values("source_row_number")
    assert fact["floor_area_band"].tolist() == py["floor_area_band"].astype(str).tolist()
    assert fact["lease_band"].tolist() == py["lease_band"].tolist()


def test_dim_month_windows(sql_env):
    _, con = sql_env
    dm = pd.read_sql("SELECT * FROM dim_month ORDER BY month", con)
    assert dm["is_partial_month"].sum() == 1
    assert dm["is_latest_12m"].sum() == 12 and dm["is_prior_12m"].sum() == 12
    assert dm.loc[dm["is_latest_12m"] == 1, "is_partial_month"].sum() == 0
    latest = dm[dm["is_latest_12m"] == 1]["month"]
    prior = dm[dm["is_prior_12m"] == 1]["month"]
    assert prior.max() < latest.min()
    assert dm.loc[dm["months_before_last_full"] == 0, "is_partial_month"].iloc[0] == 0


def test_sql_cross_check_passes_and_detects_tampering(sql_env):
    clean, con = sql_env
    assert B.cross_check(con, clean)["result"] == "match"
    con.execute("UPDATE agg_monthly SET median_price = median_price + 1 WHERE rowid = 1")
    with pytest.raises(B.CrossCheckError):
        B.cross_check(con, clean)


def test_sql_median_handles_even_and_odd_groups():
    import sqlite3
    con = sqlite3.connect(":memory:")
    pd.DataFrame({"g": ["a"] * 4 + ["b"] * 3, "v": [1, 2, 10, 20, 5, 1, 9]}).to_sql("t", con, index=False)
    out = pd.read_sql("""WITH r AS (SELECT g, v, ROW_NUMBER() OVER (PARTITION BY g ORDER BY v) rn,
                         COUNT(*) OVER (PARTITION BY g) c FROM t)
                         SELECT g, AVG(v) m FROM r WHERE rn IN ((c+1)/2, (c+2)/2) GROUP BY g""", con)
    con.close()
    assert dict(zip(out["g"], out["m"])) == {"a": 6.0, "b": 5.0}


def test_dax_expected_values_hand_check(sql_env):
    _, con = sql_env
    fact = pd.read_sql("SELECT * FROM fact_transactions", con)
    dm = pd.read_sql("SELECT * FROM dim_month", con)
    exp = B.dax_expected(fact, dm).set_index(["measure", "filter_context"])["expected_value"]
    assert exp[("Transactions", "no filter")] == len(fact)
    assert exp[("Transactions (Full Months)", "no filter")] == len(fact) - 40
    l12 = fact[fact["month"].isin(dm.loc[dm["is_latest_12m"] == 1, "month"])]
    assert exp[("Median Price Latest 12M", "no filter")] == l12["resale_price"].median()


# ---------------- PBIP consistency (requires `python -m src.reporting.build_pbip` to have run) -------------
def _model_fields() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    defs = PBIP_ROOT / f"{P.PROJECT}.SemanticModel" / "definition" / "tables"
    cols, measures = {}, {}
    for f in defs.glob("*.tmdl"):
        text = f.read_text(encoding="utf-8")
        name = f.stem
        cols[name] = {m.strip("'") for m in re.findall(r"^\tcolumn ('[^']+'|\S+)", text, re.M)}
        measures[name] = {m.strip("'") for m in re.findall(r"^\tmeasure ('[^']+'|[^=\s]+)", text, re.M)}
    return cols, measures


pbip_missing = not (PBIP_ROOT / f"{P.PROJECT}.pbip").exists()


@pytest.mark.skipif(pbip_missing, reason="PBIP not generated")
def test_every_visual_field_exists_in_model():
    cols, measures = _model_fields()
    problems, n_fields = [], 0
    for vf in (PBIP_ROOT / f"{P.PROJECT}.Report" / "definition" / "pages").rglob("visual.json"):
        v = json.loads(vf.read_text(encoding="utf-8"))
        for role in v["visual"].get("query", {}).get("queryState", {}).values():
            for proj in role["projections"]:
                kind, body = next(iter(proj["field"].items()))
                ent, prop = body["Expression"]["SourceRef"]["Entity"], body["Property"]
                n_fields += 1
                pool = cols if kind == "Column" else measures
                if prop not in pool.get(ent, set()):
                    problems.append(f"{vf.parent.name}: {kind} {ent}.{prop}")
    assert n_fields > 50
    assert not problems, problems


@pytest.mark.skipif(pbip_missing, reason="PBIP not generated")
def test_visuals_fit_on_page_and_names_unique():
    names = []
    for vf in (PBIP_ROOT / f"{P.PROJECT}.Report" / "definition" / "pages").rglob("visual.json"):
        v = json.loads(vf.read_text(encoding="utf-8"))
        pos = v["position"]
        assert pos["x"] + pos["width"] <= P.PAGE_W and pos["y"] + pos["height"] <= P.PAGE_H, vf
        names.append(v["name"])
    assert len(names) == len(set(names))


def test_measure_names_unique_and_described():
    names = [m.name for m in P.MEASURES]
    assert len(names) == len(set(names))
    assert all(m.description and m.folder for m in P.MEASURES)


def test_relationship_endpoints_are_declared_tables():
    tables = {t for t, _, _ in P.TABLES}
    for a, b in P.RELATIONSHIPS:
        assert a.split(".")[0] in tables and b.split(".")[0] in tables
