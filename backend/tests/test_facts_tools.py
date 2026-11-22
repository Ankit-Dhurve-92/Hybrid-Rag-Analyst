"""WP-BE3: the four facts tools over v_fact_current (contract 14 sections 6 and 8)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from ingestion.fin_store import FIN_SCHEMA

from app.tools.registry import ToolRegistry

CRORE, MILLION = 10_000_000, 1_000_000


def _seed(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(FIN_SCHEMA)                  # Myank's schema and v_fact_current, as extraction writes them
    conn.executemany("INSERT INTO report VALUES (?, ?, 'ANNUAL', ?, ?, NULL)", [
        ("R-A-24", "Infosys Limited", "FY2023-24", "2024-06-01"),
        ("R-A-25", "Infosys Limited", "FY2024-25", "2025-06-01"),
        ("R-B-25", "Company B", "FY2024-25", "2025-07-01"),
    ])
    conn.executemany("INSERT INTO fin_table (table_id, report_id, pages, statement, basis, scale, unit_printed, "
                     "status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                         ("T24", "R-A-24", "[48]", "PL", "CONSOLIDATED", CRORE, "₹ crore", "APPROVED"),
                         ("T25", "R-A-25", "[52]", "PL", "CONSOLIDATED", CRORE, "₹ crore", "APPROVED"),
                         ("T25S", "R-A-25", "[60]", "PL", "STANDALONE", CRORE, "₹ crore", "APPROVED"),
                         ("T25SEG", "R-A-25", "[71]", "SEGMENT", "CONSOLIDATED", CRORE, "₹ crore", "APPROVED"),
                         ("T25R", "R-A-25", "[80]", "OTHER", "CONSOLIDATED", CRORE, "₹ crore", "NEEDS_REVIEW"),
                         ("TB25", "R-B-25", "[33]", "PL", "CONSOLIDATED", MILLION, "₹ million", "APPROVED"),
                     ])
    facts = [
        # (fact, table, report, company, period, basis, metric, segment, label, value_num, printed, page, row)
        ("f1", "T24", "R-A-24", "Infosys Limited", "FY2023-24", "CONSOLIDATED", "revenue", "", "Revenue from operations",
         153_670 * CRORE, "153,670", 48, 3),
        ("f2", "T25", "R-A-25", "Infosys Limited", "FY2023-24", "CONSOLIDATED", "revenue", "", "Revenue from operations",
         153_670 * CRORE, "153,670", 52, 3),
        ("f3", "T25", "R-A-25", "Infosys Limited", "FY2024-25", "CONSOLIDATED", "revenue", "", "Revenue from operations",
         162_990 * CRORE, "162,990", 52, 3),
        ("f4", "T25S", "R-A-25", "Infosys Limited", "FY2024-25", "STANDALONE", "revenue", "", "Revenue from operations",
         129_305 * CRORE, "129,305", 60, 3),
        ("f5", "T25", "R-A-25", "Infosys Limited", "FY2024-25", "CONSOLIDATED", "", "", "Income from new ventures",
         5 * CRORE, "5", 52, 9),
        ("f6", "T24", "R-A-24", "Infosys Limited", "FY2022-23", "CONSOLIDATED", "pat", "", "Profit for the year",
         24_095 * CRORE, "24,095", 48, 14),
        ("f7", "T24", "R-A-24", "Infosys Limited", "FY2023-24", "CONSOLIDATED", "pat", "", "Profit for the year",
         26_233 * CRORE, "26,233", 48, 14),
        ("f8", "T25", "R-A-25", "Infosys Limited", "FY2023-24", "CONSOLIDATED", "pat", "", "Profit for the year",
         26_233 * CRORE, "26,233", 52, 14),
        ("f9", "T25", "R-A-25", "Infosys Limited", "FY2024-25", "CONSOLIDATED", "pat", "", "Profit for the year",
         26_713 * CRORE, "26,713", 52, 14),
        ("f10", "T25SEG", "R-A-25", "Infosys Limited", "FY2024-25", "CONSOLIDATED", "segment_revenue", "Financial Services", "Financial Services",
         40_746 * CRORE, "40,746", 71, 2),
        ("f11", "T25SEG", "R-A-25", "Infosys Limited", "FY2024-25", "CONSOLIDATED", "segment_revenue", "Manufacturing",
         "Manufacturing", 26_730 * CRORE, "26,730", 71, 3),
        ("f12", "T25SEG", "R-A-25", "Infosys Limited", "FY2024-25", "CONSOLIDATED", "segment_revenue", "Retail",
         "Retail", 23_449 * CRORE, "23,449", 71, 4),
        ("f13", "T25R", "R-A-25", "Infosys Limited", "FY2024-25", "CONSOLIDATED", "ebitda", "", "EBITDA",
         2_000 * CRORE, "2,000", 80, 1),
        ("f14", "TB25", "R-B-25", "Company B", "FY2024-25", "CONSOLIDATED", "revenue", "", "Revenue from operations",
         95_000 * MILLION, "95,000", 33, 2),
    ]
    conn.executemany("INSERT INTO fin_fact (fact_id, table_id, report_id, company, period, basis, metric, segment, "
                     "line_label, value_kind, value_num, value_printed, page, row_no, col_no) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'AMOUNT', ?, ?, ?, ?, 1)", facts)
    conn.commit()
    conn.close()


@pytest.fixture
def tools(tmp_path) -> ToolRegistry:
    knowledge = tmp_path / "knowledge.db"
    _seed(knowledge)
    return ToolRegistry(tmp_path / "business.db", knowledge)


def test_metric_value_current(tools):
    r = tools.run_tool("metric_value", {"company": "Infosys Limited", "metric": "revenue", "period": "FY2023-24"})
    assert r.status == "OK" and r.rows[0]["value"] == "₹153,670 crore" and r.rows[0]["restated"] == 0
    assert "Infosys Limited FY2024-25 annual report, p.52, PL row 3" in r.summary


def test_growth_in_sql(tools):
    r = tools.run_tool("metric_compare", {"metric": "revenue", "company": "Infosys Limited",
                                          "periods": ["FY2023-24", "FY2024-25"]})
    assert [row["value"] for row in r.rows] == ["₹153,670 crore", "₹162,990 crore"]
    assert r.rows[1]["growth_pct"] == 6.1 and r.rows[1]["change"] == "₹9,320 crore"


def test_standalone_not_in_consolidated(tools):
    r = tools.run_tool("metric_value", {"company": "Infosys Limited", "metric": "revenue", "period": "FY2024-25"})
    assert r.rows[0]["value"] == "₹162,990 crore" and r.rows[0]["basis"] == "CONSOLIDATED"
    s = tools.run_tool("metric_value", {"company": "Infosys Limited", "metric": "revenue", "period": "FY2024-25",
                                        "basis": "STANDALONE"})
    assert s.rows[0]["value"] == "₹129,305 crore"


def test_crore_and_million_compare_in_base_units(tools):
    r = tools.run_tool("metric_compare", {"metric": "revenue", "companies": ["Infosys Limited", "Company B"],
                                          "period": "FY2024-25"})
    assert [row["value"] for row in r.rows] == ["₹162,990 crore", "₹9,500 crore"]
    assert r.rows[1]["growth_pct"] == -94.2


def test_unmapped_label_not_used(tools):
    r = tools.run_tool("metric_value", {"company": "Infosys Limited", "metric": "", "period": "FY2024-25"})
    assert r.status == "ARGS_INVALID"


def test_table_waiting_for_review_not_used(tools):
    r = tools.run_tool("metric_value", {"company": "Infosys Limited", "metric": "ebitda", "period": "FY2024-25"})
    assert r.status == "EMPTY"


def test_missing_period_not_found(tools):
    r = tools.run_tool("metric_value", {"company": "Infosys Limited", "metric": "revenue", "period": "FY2019-20"})
    assert (r.status, r.summary) == ("EMPTY", "Not found in the reports.")
    c = tools.run_tool("metric_compare", {"metric": "revenue", "company": "Infosys Limited",
                                          "periods": ["FY2019-20", "FY2024-25"]})
    assert c.status == "EMPTY"                  # one side missing: no comparison


def test_metric_trend_growth(tools):
    r = tools.run_tool("metric_trend", {"company": "Infosys Limited", "metric": "pat", "from_period": "FY2020-21",
                                        "to_period": "FY2024-25"})
    assert [(row["period"], row["growth_pct"]) for row in r.rows] == [
        ("FY2022-23", None), ("FY2023-24", 8.9), ("FY2024-25", 1.8)]


def test_segment_shares_in_sql(tools):
    r = tools.run_tool("segment_breakdown", {"company": "Infosys Limited", "period": "FY2024-25"})
    assert [(row["segment"], row["share_pct"]) for row in r.rows] == [
        ("Financial Services", 44.9), ("Manufacturing", 29.4), ("Retail", 25.8)]


def test_compare_needs_exactly_one_mode(tools):
    r = tools.run_tool("metric_compare", {"metric": "revenue", "company": "Infosys Limited", "period": "FY2024-25"})
    assert r.status == "ARGS_INVALID"


def test_unknown_company_args_invalid(tools):
    r = tools.run_tool("metric_value", {"company": "Company Z", "metric": "revenue", "period": "FY2024-25"})
    assert r.status == "ARGS_INVALID" and "Company Z" in r.message


def test_no_knowledge_db_is_a_controlled_error(tmp_path):
    r = ToolRegistry(tmp_path / "business.db", tmp_path / "missing.db").run_tool(
        "metric_value", {"company": "Infosys Limited", "metric": "revenue", "period": "FY2024-25"})
    assert r.status == "DB_ERROR"
