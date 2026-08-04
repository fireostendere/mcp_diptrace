"""Read-only review execution and persisted finding views."""

from __future__ import annotations

import json
from typing import Any

from ..domain import ImpedanceInput
from ..errors import DocumentError
from ..impedance import analyze_stackup, synthesize_microstrip_width
from ..impedance import calculate_impedance as calculate_impedance_estimate
from ..lengths import analyze_differential_pair as analyze_pair_geometry
from ..lengths import measure_net_length, resolve_differential_pair, resolve_net
from ..return_path import analyze_plane_continuity as analyze_plane_geometry
from ..return_path import analyze_return_path as analyze_return_geometry
from ..review import run_checks
from .context import DocumentGateway, ServiceContext, read_success, validate_page


class ReviewService:
    """Implementation for registered review reports and read-only analysis."""

    def __init__(self, context: ServiceContext, gateway: DocumentGateway):
        self.context = context
        self.gateway = gateway

    def run_review(
        self,
        path: str | None = None,
        *,
        profile: str,
        categories: set[str] | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        findings, metrics, skipped, registered_check_count = run_checks(
            snapshot, categories=categories
        )
        unsupported_checks: list[dict[str, str]] = []
        assumptions = [
            "All coordinates are normalized to millimetres.",
            "Checks use exported XML geometry only and do not invoke DipTrace DRC/ERC.",
        ]
        if snapshot.board is not None:
            assumptions.append(
                "Component bboxes are estimated when footprint courtyard/body geometry is absent."
            )
            unsupported_checks.append(
                {
                    "check_id": "pcb.silk_to_pad",
                    "reason": "not_implemented",
                }
            )
        report = self.context.finding_store.create_report(
            document_id=snapshot.info.document_id,
            source_sha256=snapshot.info.sha256,
            profile=profile,
            findings=findings,
            metrics=metrics,
            assumptions=assumptions,
            skipped_checks=skipped,
            registered_check_count=registered_check_count,
        )
        if unsupported_checks:
            # Unsupported, unregistered checks are disclosures, not registry entries. Add them
            # after the registry-only completeness calculation, then persist the full disclosure.
            report.skipped_checks.extend(unsupported_checks)
            self.context.finding_store.store(report)
        resources = [
            f"diptrace://document/{snapshot.info.document_id}/review/{report.report_id}",
            f"diptrace://document/{snapshot.info.document_id}/findings",
        ]
        response = read_success(
            snapshot.info,
            {
                "summary": report.summary(),
                "findings": [finding.model_dump() for finding in report.findings],
                "metrics": report.metrics,
                "clearance_rule_status": report.metrics.get("clearance_rule_status"),
                "clearance_review_complete": report.metrics.get(
                    "clearance_review_complete", True
                ),
                "netclass_rules_ignored": report.metrics.get(
                    "netclass_rules_ignored", False
                ),
                "assumptions": report.assumptions,
                "skipped_checks": report.skipped_checks,
                "skipped_reasons": report.skipped_reasons,
            },
            resources=resources,
        )
        response["clearance_rule_status"] = report.metrics.get(
            "clearance_rule_status"
        )
        response["clearance_review_complete"] = report.metrics.get(
            "clearance_review_complete", True
        )
        response["netclass_rules_ignored"] = report.metrics.get(
            "netclass_rules_ignored", False
        )
        return response

    def get_stackup(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Stackup is only available for PCB documents")
        return read_success(
            snapshot.info,
            snapshot.board.stackup.model_dump(mode="json"),
            warnings=snapshot.board.stackup.warnings,
            limitations=(
                ["Physical LayerStackItems are absent from this XML export."]
                if snapshot.board.stackup.source == "missing"
                else []
            ),
            resources=[f"diptrace://document/{snapshot.info.document_id}/stackup"],
        )

    def measure_net_lengths(
        self,
        path: str | None = None,
        *,
        nets: list[str] | None = None,
        effective_dielectric_constant: float | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Net-length measurement requires a PCB document")
        references = nets or [net.stable_id for net in snapshot.board.nets]
        measurements = [
            measure_net_length(
                snapshot,
                reference,
                effective_dielectric_constant=effective_dielectric_constant,
            )
            for reference in references
        ]
        return read_success(
            snapshot.info,
            {
                "matched_count": len(measurements),
                "measurements": [item.model_dump(mode="json") for item in measurements],
                "units": {"length": "mm", "delay": "ps"},
            },
            limitations=[
                "Geometric length follows exported trace centerlines; package and pin delay "
                "are not included."
            ],
        )

    def analyze_length_group(
        self,
        nets: list[str],
        *,
        tolerance_mm: float | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        if len(nets) < 2:
            raise DocumentError("Length-group analysis requires at least two nets")
        if tolerance_mm is not None and tolerance_mm < 0:
            raise DocumentError("tolerance_mm cannot be negative")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        measurements = [measure_net_length(snapshot, net) for net in nets]
        lengths = [item.geometric_length_mm for item in measurements]
        minimum = min(lengths)
        maximum = max(lengths)
        delta = maximum - minimum
        return read_success(
            snapshot.info,
            {
                "measurements": [item.model_dump(mode="json") for item in measurements],
                "minimum_length_mm": minimum,
                "maximum_length_mm": maximum,
                "delta_mm": delta,
                "tolerance_mm": tolerance_mm,
                "within_tolerance": tolerance_mm is None or delta <= tolerance_mm,
            },
        )

    def list_differential_pairs(
        self,
        path: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        validate_page(offset, limit)
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Differential pairs require a PCB document")
        pairs = snapshot.board.differential_pairs
        return read_success(
            snapshot.info,
            {
                "matched_count": len(pairs),
                "offset": offset,
                "limit": limit,
                "items": [item.model_dump(mode="json") for item in pairs[offset : offset + limit]],
            },
        )

    def get_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        result = resolve_differential_pair(snapshot, pair)
        return read_success(snapshot.info, result.model_dump(mode="json"))

    def analyze_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        result = analyze_pair_geometry(snapshot, pair)
        return read_success(
            snapshot.info,
            result.model_dump(mode="json"),
            warnings=result.warnings,
            limitations=[
                "Coupling and gap are geometry heuristics; this is not a field-solver result."
            ],
        )

    def analyze_differential_pairs(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Differential pairs require a PCB document")
        analyses = [
            analyze_pair_geometry(snapshot, pair.stable_id)
            for pair in snapshot.board.differential_pairs
        ]
        return read_success(
            snapshot.info,
            {
                "matched_count": len(analyses),
                "items": [item.model_dump(mode="json") for item in analyses],
                "failed_check_count": sum(
                    1 for item in analyses for check in item.checks if not bool(check["passed"])
                ),
                "skipped_check_count": sum(
                    len(item.skipped_checks) for item in analyses
                ),
                "incomplete_pair_count": sum(
                    not item.fully_evaluated for item in analyses
                ),
            },
            limitations=[
                "Coupling and gap are geometry heuristics; this is not a field-solver result."
            ],
        )

    def validate_differential_pair(self, pair: str, path: str | None = None) -> dict[str, Any]:
        response = self.analyze_differential_pair(pair, path)
        checks = response["result"]["checks"]
        fully_evaluated = bool(response["result"]["fully_evaluated"])
        response["result"]["valid"] = fully_evaluated and all(
            bool(check["passed"]) for check in checks
        )
        response["result"]["evaluated_check_count"] = len(checks)
        response["result"]["status"] = (
            "valid"
            if response["result"]["valid"]
            else "incomplete"
            if not fully_evaluated
            else "invalid"
        )
        return response

    def calculate_impedance(
        self,
        *,
        structure: str,
        width_mm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        gap_mm: float | None = None,
        frequency_hz: float | None = None,
        target_ohm: float | None = None,
        tolerance_ohm: float | None = None,
    ) -> dict[str, Any]:
        values = ImpedanceInput.model_validate(
            {
                "structure": structure,
                "width_mm": width_mm,
                "copper_thickness_mm": copper_thickness_mm,
                "dielectric_height_mm": dielectric_height_mm,
                "dielectric_constant": dielectric_constant,
                "gap_mm": gap_mm,
                "frequency_hz": frequency_hz,
                "target_ohm": target_ohm,
                "tolerance_ohm": tolerance_ohm,
            }
        )
        result = calculate_impedance_estimate(values)
        return {
            "ok": True,
            "document": None,
            "result": result.model_dump(mode="json"),
            "warnings": result.warnings,
            "limitations": [
                "Analytical preliminary estimate only; not a full-wave or fabrication-coupon "
                "result."
            ],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def suggest_trace_geometry_for_impedance(
        self,
        *,
        target_ohm: float,
        copper_thickness_mm: float,
        dielectric_height_mm: float,
        dielectric_constant: float,
        minimum_width_mm: float,
        maximum_width_mm: float,
        tolerance_ohm: float = 0.01,
    ) -> dict[str, Any]:
        result = synthesize_microstrip_width(
            target_ohm=target_ohm,
            copper_thickness_mm=copper_thickness_mm,
            dielectric_height_mm=dielectric_height_mm,
            dielectric_constant=dielectric_constant,
            minimum_width_mm=minimum_width_mm,
            maximum_width_mm=maximum_width_mm,
            tolerance_ohm=tolerance_ohm,
        )
        return {
            "ok": True,
            "document": None,
            "result": result,
            "warnings": result["result"]["warnings"],
            "limitations": [
                "Width synthesis uses the same preliminary Hammerstad-Jensen microstrip model."
            ],
            "resources": [],
            "transaction": None,
            "job": None,
        }

    def analyze_stackup_for_impedance(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Stackup analysis requires a PCB document")
        result = analyze_stackup(snapshot.board.stackup)
        return read_success(
            snapshot.info,
            result,
            warnings=snapshot.board.stackup.warnings,
            limitations=result["limitations"],
        )

    def validate_impedance_constraints(
        self,
        constraints: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        if not constraints:
            raise DocumentError("At least one explicit impedance constraint is required")
        if len(constraints) > 1_000:
            raise DocumentError("At most 1000 impedance constraints are accepted")
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Impedance validation requires a PCB document")
        stackup_analysis = analyze_stackup(snapshot.board.stackup)
        candidates = stackup_analysis["microstrip_candidates"]
        layer_names = {
            str(layer.get("id", "")): str(layer.get("name", "")) for layer in snapshot.board.layers
        }
        results: list[dict[str, Any]] = []
        for index, raw_constraint in enumerate(constraints):
            net_ref = str(raw_constraint.get("net", "")).strip()
            layer_ref = str(raw_constraint.get("layer", "")).strip()
            if not net_ref or not layer_ref:
                raise DocumentError(
                    f"Constraint {index} requires net and layer",
                    details={"constraint_index": index},
                )
            net = resolve_net(snapshot, net_ref)
            target_ohm = float(raw_constraint.get("target_ohm", 0.0))
            tolerance_ohm = float(raw_constraint.get("tolerance_ohm", 0.0))
            if target_ohm <= 0 or tolerance_ohm < 0:
                raise DocumentError(
                    f"Constraint {index} has invalid target/tolerance",
                    details={"constraint_index": index},
                )
            canonical_layer = layer_names.get(layer_ref, layer_ref)
            stack_candidates = [
                item for item in candidates if item["signal_layer"] == canonical_layer
            ]
            if len(stack_candidates) != 1:
                results.append(
                    {
                        "net_id": net.stable_id,
                        "net": net.name,
                        "layer": layer_ref,
                        "status": "skipped",
                        "reason": "No unique complete microstrip geometry exists for this layer.",
                    }
                )
                continue
            widths = {
                float(width)
                for trace in snapshot.board.traces
                if trace.parent_id == net.stable_id
                for segment_index, width in enumerate(trace.attributes.get("segment_widths_mm", []))
                if width is not None
                and (
                    segment_index >= len(trace.attributes.get("segment_layers", []))
                    or str(trace.attributes["segment_layers"][segment_index]) == layer_ref
                    or layer_names.get(str(trace.attributes["segment_layers"][segment_index]), "")
                    == canonical_layer
                )
            }
            if raw_constraint.get("width_mm") is not None:
                widths = {float(raw_constraint["width_mm"])}
            if not widths:
                results.append(
                    {
                        "net_id": net.stable_id,
                        "net": net.name,
                        "layer": layer_ref,
                        "status": "skipped",
                        "reason": "No routed width exists on the requested layer.",
                    }
                )
                continue
            stack_candidate = stack_candidates[0]
            estimates = [
                calculate_impedance_estimate(
                    ImpedanceInput(
                        structure="microstrip",
                        width_mm=width,
                        copper_thickness_mm=float(
                            stack_candidate.get("copper_thickness_mm") or 0.0
                        ),
                        dielectric_height_mm=float(stack_candidate["dielectric_height_mm"]),
                        dielectric_constant=float(stack_candidate["dielectric_constant"]),
                        target_ohm=target_ohm,
                        tolerance_ohm=tolerance_ohm,
                        source=f"stackup:{snapshot.info.document_id}:{canonical_layer}",
                    )
                )
                for width in sorted(widths)
            ]
            results.append(
                {
                    "net_id": net.stable_id,
                    "net": net.name,
                    "layer": layer_ref,
                    "status": "evaluated",
                    "valid": all(item.within_tolerance is True for item in estimates),
                    "estimates": [item.model_dump(mode="json") for item in estimates],
                    "stackup_geometry": stack_candidate,
                }
            )
        evaluated = [item for item in results if item["status"] == "evaluated"]
        return read_success(
            snapshot.info,
            {
                "constraint_count": len(constraints),
                "evaluated_count": len(evaluated),
                "skipped_count": len(results) - len(evaluated),
                "valid": bool(evaluated)
                and len(evaluated) == len(results)
                and all(bool(item["valid"]) for item in evaluated),
                "items": results,
            },
            limitations=[
                "Only explicit single-ended outer-layer microstrip constraints are evaluated.",
                "Reference-plane net continuity and solder mask are not inferred by this tool.",
            ],
        )

    def analyze_controlled_impedance_nets(
        self,
        constraints: list[dict[str, Any]],
        *,
        path: str | None = None,
    ) -> dict[str, Any]:
        return self.validate_impedance_constraints(constraints, path=path)

    def list_copper_pours(
        self,
        path: str | None = None,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        validate_page(offset, limit)
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        if snapshot.board is None:
            raise DocumentError("Copper pours require a PCB document")
        items = snapshot.board.copper_pours
        return read_success(
            snapshot.info,
            {
                "matched_count": len(items),
                "offset": offset,
                "limit": limit,
                "items": [item.model_dump(mode="json") for item in items[offset : offset + limit]],
            },
            limitations=[
                "Exported polygons are pour boundaries, not authoritative refilled copper."
            ],
        )

    def analyze_plane_continuity(self, path: str | None = None) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        result = analyze_plane_geometry(snapshot)
        return read_success(
            snapshot.info,
            result,
            limitations=result["limitations"],
        )

    def analyze_return_path(
        self,
        path: str | None = None,
        *,
        stitching_radius_mm: float,
        nets: list[str] | None = None,
        reference_nets: list[str] | None = None,
    ) -> dict[str, Any]:
        document, target = self.gateway.load(path)
        snapshot = self.context.model_cache.get(document, live_session=target.is_live)
        result = analyze_return_geometry(
            snapshot,
            nets=nets,
            reference_nets=reference_nets,
            stitching_radius_mm=stitching_radius_mm,
        )
        return read_success(
            snapshot.info,
            result.model_dump(mode="json"),
            limitations=[
                "Geometry-based heuristic only; exported pour boundaries are not final refill."
            ],
        )

    def get_findings(self, report_id: str) -> dict[str, Any]:
        report = self.context.finding_store.read(report_id)
        return {
            "ok": True,
            "report": report.summary(),
            "findings": [finding.model_dump() for finding in report.findings],
        }

    def get_finding(self, finding_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "finding": self.context.finding_store.get_finding(finding_id).model_dump(),
        }

    def review_resource(self, report_id: str) -> str:
        report = self.context.finding_store.read(report_id)
        return json.dumps(report.model_dump(), ensure_ascii=False, indent=2)

    def findings_resource(self, document_id: str) -> str:
        reports = []
        for report in reversed(self.context.finding_store.list_reports()):
            if report.document_id == document_id:
                reports.append(report.model_dump())
        return json.dumps({"document_id": document_id, "reports": reports}, indent=2)
