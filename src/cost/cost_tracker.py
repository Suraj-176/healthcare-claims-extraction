"""
cost_tracker.py

Tracks which path each page took through the pipeline (template-only, LLM-escalated,
discarded, or rejected) and rolls up a real blended cost-per-page from actual per-path unit
cost assumptions. These unit costs are estimates (see project spec, Section 8) and are stated
as such wherever this rollup is reported — never presented as measured facts.
"""

from __future__ import annotations

# Estimates only — see project spec Section 8. Update with real measured/quoted costs before
# finalizing the Cost Analysis deliverable.
UNIT_COST_ESTIMATES = {
    "template_only": 0.0015,
    "llm_escalated": 0.015,
    "human_review": 0.20,
    "discarded_or_rejected": 0.0,
}


class CostTracker:
    def __init__(self) -> None:
        self._page_paths: list[str] = []

    def record_page(self, path_taken: str) -> None:
        """path_taken should be one of the UNIT_COST_ESTIMATES keys."""
        if path_taken not in UNIT_COST_ESTIMATES:
            path_taken = "template_only"  # safe default, never crash on an unexpected label
        self._page_paths.append(path_taken)

    def summary(self) -> dict:
        total_pages = len(self._page_paths)
        if total_pages == 0:
            return {"total_pages": 0, "blended_cost_per_page": 0.0, "breakdown": {}}

        breakdown = {}
        total_cost = 0.0
        for path_type, unit_cost in UNIT_COST_ESTIMATES.items():
            count = self._page_paths.count(path_type)
            cost = count * unit_cost
            total_cost += cost
            breakdown[path_type] = {"count": count, "unit_cost_estimate": unit_cost, "subtotal": round(cost, 4)}

        return {
            "total_pages": total_pages,
            "blended_cost_per_page": round(total_cost / total_pages, 5),
            "breakdown": breakdown,
            "note": "unit costs are estimates from the project spec, not measured invoices",
        }
