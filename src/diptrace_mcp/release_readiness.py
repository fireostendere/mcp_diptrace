"""Deterministic DFM/DFA/DFT release-readiness supplement.

These checks are intentionally bounded to facts available in exported XML. They
supplement the registered review engine without pretending to replace DipTrace
DRC/ERC, fabrication review, assembly sign-off, or physical test-fixture review.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .adapters import DocumentSnapshot

_DNP_TRUE = {"1", "true", "yes", "y"}
_MPN_KEYS = ("mpn", "manufacturer part number", "manufacturer_part_number")


def _fields(item: Any) -> dict[str, str]:
    raw = item.attributes.get("additional_fields", {})
    return {str(key).casefold(): str(value).strip() for key, value in raw.items()}


def _is_dnp(item: Any) -> bool:
    return _fields(item).get("dnp", "").casefold() in _DNP_TRUE


def _finding(
    check_id: str,
    severity: str,
    message: str,
    *,
    object_ids: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "severity": severity,
        "message": message,
        "object_ids": object_ids or [],
        "details": details or {},
    }


def run_release_readiness(snapshot: DocumentSnapshot) -> dict[str, Any]:
    """Run automatable release checks and disclose every non-automatable boundary."""

    findings: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    if snapshot.board is None:
        return {
            "status": "not_applicable",
            "findings": [],
            "metrics": {},
            "manual_gates": ["PCB DFM/DFA/DFT supplement requires a PCB document."],
        }

    components = list(snapshot.board.components)
    populated = [item for item in components if not _is_dnp(item)]
    metrics["components"] = len(components)
    metrics["populated_components"] = len(populated)

    refdes_counts = Counter((item.refdes or "").casefold() for item in components if item.refdes)
    duplicate_refdes = {value for value, count in refdes_counts.items() if count > 1}
    for refdes in sorted(duplicate_refdes):
        objects = [
            item.stable_id
            for item in components
            if (item.refdes or "").casefold() == refdes
        ]
        findings.append(
            _finding(
                "release.duplicate_refdes",
                "error",
                f"Reference designator {refdes.upper()} occurs more than once.",
                object_ids=objects,
            )
        )
    metrics["duplicate_refdes_count"] = len(duplicate_refdes)

    missing_pattern = [
        item
        for item in populated
        if not str(item.attributes.get("pattern_style", "")).strip()
    ]
    for item in missing_pattern:
        findings.append(
            _finding(
                "release.pattern_assignment",
                "error",
                f"{item.refdes or item.label} has no explicit pattern assignment.",
                object_ids=[item.stable_id],
            )
        )
    metrics["missing_pattern_assignment_count"] = len(missing_pattern)

    missing_value = [item for item in populated if not (item.value or "").strip()]
    for item in missing_value:
        findings.append(
            _finding(
                "release.component_value",
                "warning",
                f"{item.refdes or item.label} has no explicit value.",
                object_ids=[item.stable_id],
            )
        )
    metrics["missing_value_count"] = len(missing_value)

    missing_procurement_identity = []
    for item in populated:
        fields = _fields(item)
        mpn = next((fields[key] for key in _MPN_KEYS if fields.get(key)), "")
        manufacturer = fields.get("manufacturer") or str(
            item.attributes.get("manufacturer", "")
        ).strip()
        if not mpn or not manufacturer:
            missing_procurement_identity.append(item)
            findings.append(
                _finding(
                    "release.procurement_identity",
                    "warning",
                    f"{item.refdes or item.label} lacks manufacturer and/or MPN metadata.",
                    object_ids=[item.stable_id],
                    details={
                        "manufacturer_present": bool(manufacturer),
                        "mpn_present": bool(mpn),
                    },
                )
            )
    metrics["missing_procurement_identity_count"] = len(missing_procurement_identity)

    patterns = {item.style: item for item in snapshot.board.patterns if item.style}
    missing_embedded_pattern = []
    missing_3d_model = []
    for item in populated:
        style = str(item.attributes.get("pattern_style", "")).strip()
        if not style:
            continue
        pattern = patterns.get(style)
        if pattern is None:
            missing_embedded_pattern.append(item)
            continue
        model = pattern.model_3d
        filename = str((model or {}).get("filename", "")).strip()
        if not filename:
            missing_3d_model.append(item)
    for item in missing_embedded_pattern:
        findings.append(
            _finding(
                "release.embedded_pattern_geometry",
                "warning",
                f"{item.refdes or item.label} pattern geometry is not embedded in the PCB cache.",
                object_ids=[item.stable_id],
            )
        )
    for item in missing_3d_model:
        findings.append(
            _finding(
                "release.assembly_3d_model",
                "info",
                f"{item.refdes or item.label} has no embedded 3D-model filename.",
                object_ids=[item.stable_id],
            )
        )
    metrics["missing_embedded_pattern_count"] = len(missing_embedded_pattern)
    metrics["missing_3d_model_count"] = len(missing_3d_model)

    eligible_nets = [
        net for net in snapshot.board.nets if int(net.attributes.get("endpoint_count", 0)) >= 2
    ]
    covered_net_ids = {
        item.net_id for item in snapshot.board.testpoints if item.net_id is not None
    }
    uncovered = [net for net in eligible_nets if net.xml_id not in covered_net_ids]
    metrics["dft_eligible_nets"] = len(eligible_nets)
    metrics["dft_explicitly_covered_nets"] = len(eligible_nets) - len(uncovered)
    metrics["dft_explicit_testpoint_coverage"] = (
        (len(eligible_nets) - len(uncovered)) / len(eligible_nets)
        if eligible_nets
        else 1.0
    )

    severity_rank = {"error": 3, "warning": 2, "info": 1}
    highest = max((severity_rank[item["severity"]] for item in findings), default=0)
    status = "blocked" if highest >= 3 else "review" if highest >= 2 else "informational"
    return {
        "status": status,
        "findings": findings,
        "metrics": metrics,
        "manual_gates": [
            "Run real DipTrace DRC/ERC and inspect every unresolved/skipped category.",
            "Obtain fabrication/assembly sign-off for process-specific limits and outputs.",
            "Validate physical test access and fixture strategy; XML testpoint presence is not fixture proof.",
            "Validate thermal performance with real stackup, power, enclosure and airflow assumptions.",
        ],
        "limitations": [
            "The supplement uses exported XML and deterministic heuristics only.",
            "3D-model presence checks a filename reference, not model correctness or mechanical fit.",
            "Explicit testpoint coverage does not prove probe accessibility or fixture manufacturability.",
        ],
    }
