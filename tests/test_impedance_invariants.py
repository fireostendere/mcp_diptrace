from __future__ import annotations

from itertools import pairwise, product

import pytest

from diptrace_mcp.domain import ImpedanceInput, ImpedanceResult
from diptrace_mcp.impedance import calculate_impedance

ER_VALUES = (2.2, 3.5, 4.1, 4.4, 10.2)
HEIGHTS_MM = (0.1, 0.18, 0.5, 1.0)
WIDTH_RATIOS = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
IN_BAND_WIDTH_RATIOS = WIDTH_RATIOS[:-1]
GAP_RATIOS = (0.01, 0.1, 0.2, 0.5, 1.0, 2.0, 10.0)
COPPER_THICKNESSES_MM = (0.0, 0.035, 0.070)


def _coupled_result(
    *,
    er: float,
    height_mm: float,
    width_ratio: float,
    gap_ratio: float,
    thickness_mm: float,
) -> ImpedanceResult:
    return calculate_impedance(
        ImpedanceInput(
            structure="differential_microstrip",
            width_mm=width_ratio * height_mm,
            gap_mm=gap_ratio * height_mm,
            copper_thickness_mm=thickness_mm,
            dielectric_height_mm=height_mm,
            dielectric_constant=er,
        )
    )


def _zero_thickness_single_result(
    *,
    er: float,
    height_mm: float,
    width_ratio: float,
) -> ImpedanceResult:
    return calculate_impedance(
        ImpedanceInput(
            structure="microstrip",
            width_mm=width_ratio * height_mm,
            copper_thickness_mm=0.0,
            dielectric_height_mm=height_mm,
            dielectric_constant=er,
        )
    )


def test_coupled_published_bounds_are_cited_and_inclusive() -> None:
    result = _coupled_result(
        er=4.1,
        height_mm=0.18,
        width_ratio=0.1,
        gap_ratio=0.01,
        thickness_mm=0.0,
    )

    assert result.validity["inside_published_range"] is True
    published_range = result.validity["published_range"]
    citations = result.validity["published_range_citations"]
    assert published_range == {
        "min_width_over_height": 0.1,
        "max_width_over_height": 10.0,
        "min_gap_over_height": 0.01,
    }
    assert citations.keys() == published_range.keys()
    assert all(
        "https://qucs.sourceforge.net/tech/node77.html" in citation
        for citation in citations.values()
    )


def test_coupled_microstrip_swept_physical_invariants() -> None:
    evaluated = 0
    for er, height_mm, thickness_mm in product(
        ER_VALUES,
        HEIGHTS_MM,
        COPPER_THICKNESSES_MM,
    ):
        results_by_gap: dict[float, dict[float, ImpedanceResult]] = {}
        for gap_ratio in GAP_RATIOS:
            results_by_width: dict[float, ImpedanceResult] = {}
            for width_ratio in WIDTH_RATIOS:
                result = _coupled_result(
                    er=er,
                    height_mm=height_mm,
                    width_ratio=width_ratio,
                    gap_ratio=gap_ratio,
                    thickness_mm=thickness_mm,
                )
                results_by_width[width_ratio] = result
                evaluated += 1

                if width_ratio <= 10.0:
                    single = _zero_thickness_single_result(
                        er=er,
                        height_mm=height_mm,
                        width_ratio=width_ratio,
                    )
                    single_er = single.effective_dielectric_constant
                    assert single_er is not None
                    odd_er = float(
                        result.validity["odd_mode_effective_dielectric_constant"]
                    )
                    even_er = float(
                        result.validity["even_mode_effective_dielectric_constant"]
                    )
                    # The coupled branch is explicitly zero-thickness. Compare its
                    # modal permittivities with the zero-thickness single line even
                    # when the caller supplied finite copper thickness.
                    assert odd_er < single_er < even_er
                    assert 1.0 < odd_er < er
                    assert 1.0 < single_er < er
                    assert 1.0 < even_er < er
                    assert result.validity["inside_published_range"] is True
                else:
                    # Do not assert model physics outside the published W/h band.
                    assert result.validity["inside_published_range"] is False
                    assert result.confidence == "low"
                    assert any("outside" in warning.lower() for warning in result.warnings)

            in_band_by_width = [
                results_by_width[ratio].estimated_impedance_ohm
                for ratio in IN_BAND_WIDTH_RATIOS
            ]
            assert all(
                left > right
                for left, right in pairwise(in_band_by_width)
            )
            results_by_gap[gap_ratio] = results_by_width

        for width_ratio in IN_BAND_WIDTH_RATIOS:
            in_band_by_gap = [
                results_by_gap[ratio][width_ratio].estimated_impedance_ohm
                for ratio in GAP_RATIOS
            ]
            assert all(
                left < right
                for left, right in pairwise(in_band_by_gap)
            )

    assert evaluated == 3_360


def test_coupled_microstrip_impedance_increases_with_dielectric_height() -> None:
    for er, thickness_mm in product(ER_VALUES, COPPER_THICKNESSES_MM):
        impedances = [
            calculate_impedance(
                ImpedanceInput(
                    structure="differential_microstrip",
                    width_mm=0.2,
                    gap_mm=0.15,
                    copper_thickness_mm=thickness_mm,
                    dielectric_height_mm=height_mm,
                    dielectric_constant=er,
                )
            ).estimated_impedance_ohm
            for height_mm in HEIGHTS_MM
        ]
        assert all(
            left < right
            for left, right in pairwise(impedances)
        )


def test_coupled_microstrip_decoupling_asymptote() -> None:
    for er, height_mm, width_ratio, thickness_mm in product(
        ER_VALUES,
        HEIGHTS_MM,
        IN_BAND_WIDTH_RATIOS,
        COPPER_THICKNESSES_MM,
    ):
        coupled = _coupled_result(
            er=er,
            height_mm=height_mm,
            width_ratio=width_ratio,
            gap_ratio=1_000.0,
            thickness_mm=thickness_mm,
        )
        single = _zero_thickness_single_result(
            er=er,
            height_mm=height_mm,
            width_ratio=width_ratio,
        )
        single_er = single.effective_dielectric_constant
        assert single_er is not None
        odd_er = float(coupled.validity["odd_mode_effective_dielectric_constant"])
        even_er = float(coupled.validity["even_mode_effective_dielectric_constant"])

        assert odd_er == pytest.approx(single_er, rel=0.01)
        assert even_er == pytest.approx(single_er, rel=0.01)
        if thickness_mm == 0.0:
            assert coupled.estimated_impedance_ohm == pytest.approx(
                2.0 * single.estimated_impedance_ohm,
                rel=0.05,
            )
        else:
            # The coupled model does not implement the finite-thickness
            # correction, so comparing it with a thickness-corrected Z0 would
            # turn this physical asymptote into a known false assertion.
            assert coupled.confidence == "low"
            assert any(
                "Finite copper thickness" in warning for warning in coupled.warnings
            )
