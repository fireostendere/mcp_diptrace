from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, cast

DipTraceEditor = Literal["pcb", "schematic"]
MouseButton = Literal["left", "right", "middle"]


@dataclass(frozen=True, slots=True)
class DesignPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("design coordinates must be finite")


@dataclass(frozen=True, slots=True)
class ClientPoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("client coordinates must be finite")
        if not 0.0 <= self.x <= 1.0 or not 0.0 <= self.y <= 1.0:
            raise ValueError("client coordinates must be normalized to 0..1")


@dataclass(frozen=True, slots=True)
class CalibrationAnchor:
    design: DesignPoint
    client: ClientPoint


def _solve_three(
    matrix: Sequence[Sequence[float]],
    values: Sequence[float],
) -> tuple[float, float, float]:
    if len(matrix) != 3 or len(values) != 3 or any(len(row) != 3 for row in matrix):
        raise ValueError("3x3 linear system required")
    augmented = [
        [float(matrix[row][column]) for column in range(3)] + [float(values[row])]
        for row in range(3)
    ]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("calibration anchors are degenerate")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        for item in range(column, 4):
            augmented[column][item] /= divisor
        for row in range(3):
            if row == column:
                continue
            factor = augmented[row][column]
            for item in range(column, 4):
                augmented[row][item] -= factor * augmented[column][item]
    return augmented[0][3], augmented[1][3], augmented[2][3]


def _least_squares_plane(
    points: Sequence[DesignPoint],
    values: Sequence[float],
) -> tuple[float, float, float]:
    if len(points) != len(values) or len(points) < 3:
        raise ValueError("at least three matching calibration samples are required")
    sx = sum(point.x for point in points)
    sy = sum(point.y for point in points)
    sxx = sum(point.x * point.x for point in points)
    syy = sum(point.y * point.y for point in points)
    sxy = sum(point.x * point.y for point in points)
    sv = sum(values)
    sxv = sum(point.x * value for point, value in zip(points, values, strict=True))
    syv = sum(point.y * value for point, value in zip(points, values, strict=True))
    matrix = (
        (sxx, sxy, sx),
        (sxy, syy, sy),
        (sx, sy, float(len(points))),
    )
    return _solve_three(matrix, (sxv, syv, sv))


@dataclass(frozen=True, slots=True)
class DesignToClientTransform:
    """Affine DipTrace design-coordinate to normalized client transform."""

    xx: float
    xy: float
    x0: float
    yx: float
    yy: float
    y0: float

    def __post_init__(self) -> None:
        coefficients = (self.xx, self.xy, self.x0, self.yx, self.yy, self.y0)
        if not all(math.isfinite(value) for value in coefficients):
            raise ValueError("transform coefficients must be finite")
        if abs(self.xx * self.yy - self.xy * self.yx) < 1e-12:
            raise ValueError("design-to-client transform must be invertible")

    def _map_raw(self, point: DesignPoint) -> tuple[float, float]:
        return (
            self.xx * point.x + self.xy * point.y + self.x0,
            self.yx * point.x + self.yy * point.y + self.y0,
        )

    def map(self, point: DesignPoint) -> ClientPoint:
        x, y = self._map_raw(point)
        return ClientPoint(x, y)

    def inverse(self, point: ClientPoint) -> DesignPoint:
        determinant = self.xx * self.yy - self.xy * self.yx
        dx = point.x - self.x0
        dy = point.y - self.y0
        x = (self.yy * dx - self.xy * dy) / determinant
        y = (-self.yx * dx + self.xx * dy) / determinant
        return DesignPoint(x, y)

    def error(self, anchors: Sequence[CalibrationAnchor]) -> tuple[float, float]:
        if not anchors:
            raise ValueError("at least one calibration anchor is required")
        errors: list[float] = []
        for anchor in anchors:
            x, y = self._map_raw(anchor.design)
            errors.append(math.hypot(x - anchor.client.x, y - anchor.client.y))
        rms = math.sqrt(sum(value * value for value in errors) / len(errors))
        return rms, max(errors)

    @classmethod
    def calibrate(
        cls,
        anchors: Sequence[CalibrationAnchor],
        *,
        max_rms_error: float = 0.01,
        max_point_error: float = 0.025,
    ) -> DesignToClientTransform:
        if len(anchors) < 3:
            raise ValueError("at least three calibration anchors are required")
        if max_rms_error <= 0 or max_point_error <= 0:
            raise ValueError("calibration error thresholds must be > 0")
        design = [anchor.design for anchor in anchors]
        xx, xy, x0 = _least_squares_plane(design, [a.client.x for a in anchors])
        yx, yy, y0 = _least_squares_plane(design, [a.client.y for a in anchors])
        transform = cls(xx=xx, xy=xy, x0=x0, yx=yx, yy=yy, y0=y0)
        rms, maximum = transform.error(anchors)
        if rms > max_rms_error or maximum > max_point_error:
            raise ValueError(
                "calibration residual is too large: "
                f"rms={rms:.6f}, max={maximum:.6f}"
            )
        return transform


@dataclass(frozen=True, slots=True)
class UIActionStep:
    move_to: ClientPoint | None = None
    path: tuple[ClientPoint, ...] = ()
    click: MouseButton | None = None
    click_count: int = 1
    hotkey: tuple[str, ...] = ()
    text: str | None = None
    pause_ms: int = 0

    def __post_init__(self) -> None:
        if self.click not in {None, "left", "right", "middle"}:
            raise ValueError("unsupported mouse button")
        if not 1 <= self.click_count <= 3:
            raise ValueError("click_count must be between 1 and 3")
        if not 0 <= self.pause_ms <= 10_000:
            raise ValueError("pause_ms must be between 0 and 10000")
        if self.move_to is not None and self.path:
            raise ValueError("UI action step cannot use move_to and path together")
        if self.path and len(self.path) < 2:
            raise ValueError("UI action path requires at least two points")
        if any(not key.strip() for key in self.hotkey):
            raise ValueError("hotkey names must not be empty")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.move_to is not None:
            result["move_to"] = [self.move_to.x, self.move_to.y]
        if self.path:
            result["path"] = [[point.x, point.y] for point in self.path]
        if self.click is not None:
            result["click"] = self.click
            result["click_count"] = self.click_count
        if self.hotkey:
            result["hotkey"] = list(self.hotkey)
        if self.text is not None:
            result["text"] = self.text
        if self.pause_ms:
            result["pause_ms"] = self.pause_ms
        return result

    def render(self, context: Mapping[str, str] | None = None) -> dict[str, Any]:
        result = self.to_dict()
        if self.text is None:
            return result
        try:
            result["text"] = self.text.format_map(dict(context or {}))
        except KeyError as exc:
            raise ValueError(
                f"missing UI action template value: {exc.args[0]}"
            ) from exc
        return result


_REQUIRED_ACTIONS: dict[DipTraceEditor, tuple[str, ...]] = {
    "pcb": ("place_component", "route_trace"),
    "schematic": ("place_component", "wire"),
}


def _point_from_json(value: Any, *, field_name: str) -> ClientPoint:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError(f"{field_name} must contain [x, y]")
    return ClientPoint(float(value[0]), float(value[1]))


def _step_from_json(raw: Any, *, field_name: str) -> UIActionStep:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{field_name} must be an object")
    move_to = (
        _point_from_json(raw["move_to"], field_name=f"{field_name}.move_to")
        if raw.get("move_to") is not None
        else None
    )
    path: tuple[ClientPoint, ...] = ()
    path_raw = raw.get("path")
    if path_raw is not None:
        if not isinstance(path_raw, Sequence) or isinstance(path_raw, (str, bytes)):
            raise ValueError(f"{field_name}.path must be an array")
        path = tuple(
            _point_from_json(point, field_name=f"{field_name}.path[{index}]")
            for index, point in enumerate(path_raw)
        )
    hotkey: tuple[str, ...] = ()
    hotkey_raw = raw.get("hotkey")
    if hotkey_raw is not None:
        if (
            not isinstance(hotkey_raw, Sequence)
            or isinstance(hotkey_raw, (str, bytes))
            or not all(isinstance(key, str) for key in hotkey_raw)
        ):
            raise ValueError(f"{field_name}.hotkey must be an array of strings")
        hotkey = tuple(str(key) for key in hotkey_raw)
    click_raw = raw.get("click")
    click: MouseButton | None = None
    if click_raw is not None:
        if click_raw not in {"left", "right", "middle"}:
            raise ValueError(f"{field_name}.click is invalid")
        click = cast(MouseButton, click_raw)
    text_raw = raw.get("text")
    if text_raw is not None and not isinstance(text_raw, str):
        raise ValueError(f"{field_name}.text must be a string")
    return UIActionStep(
        move_to=move_to,
        path=path,
        click=click,
        click_count=int(raw.get("click_count", 1)),
        hotkey=hotkey,
        text=text_raw,
        pause_ms=int(raw.get("pause_ms", 0)),
    )


@dataclass(frozen=True, slots=True)
class DipTraceUIProfile:
    profile_id: str
    editor: DipTraceEditor
    diptrace_version: str
    window_title_contains: str = "DipTrace"
    actions: dict[str, tuple[UIActionStep, ...]] = field(default_factory=dict)
    transform: DesignToClientTransform | None = None

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id must not be empty")
        if self.editor not in {"pcb", "schematic"}:
            raise ValueError("unsupported DipTrace editor")
        if not self.diptrace_version.strip():
            raise ValueError("diptrace_version must not be empty")
        if not self.window_title_contains.strip():
            raise ValueError("window_title_contains must not be empty")
        if any(not name.strip() for name in self.actions):
            raise ValueError("UI action names must not be empty")

    @property
    def required_actions(self) -> tuple[str, ...]:
        return _REQUIRED_ACTIONS[self.editor]

    @property
    def is_calibrated(self) -> bool:
        return self.transform is not None

    @property
    def missing_actions(self) -> tuple[str, ...]:
        return tuple(name for name in self.required_actions if name not in self.actions)

    @property
    def is_ready(self) -> bool:
        return self.is_calibrated and not self.missing_actions

    def require_ready(self) -> None:
        if self.transform is None:
            raise ValueError("DipTrace UI profile is not calibrated")
        if self.missing_actions:
            missing = ", ".join(self.missing_actions)
            raise ValueError(f"DipTrace UI profile is missing required actions: {missing}")

    def with_transform(self, transform: DesignToClientTransform) -> DipTraceUIProfile:
        return replace(self, transform=transform)

    def with_action(self, name: str, steps: Sequence[UIActionStep]) -> DipTraceUIProfile:
        if not name.strip():
            raise ValueError("UI action name must not be empty")
        if not steps:
            raise ValueError("UI action must contain at least one step")
        actions = dict(self.actions)
        actions[name] = tuple(steps)
        return replace(self, actions=actions)

    def render_action(
        self,
        name: str,
        *,
        context: Mapping[str, str] | None = None,
        optional: bool = False,
    ) -> list[dict[str, Any]]:
        steps = self.actions.get(name)
        if steps is None:
            if optional:
                return []
            raise ValueError(f"DipTrace UI action is not configured: {name}")
        return [step.render(context) for step in steps]

    def map_design(self, x: float, y: float) -> ClientPoint:
        if self.transform is None:
            raise ValueError("DipTrace UI profile is not calibrated")
        return self.transform.map(DesignPoint(x, y))

    def to_dict(self) -> dict[str, Any]:
        actions = {
            name: [step.to_dict() for step in steps]
            for name, steps in sorted(self.actions.items())
        }
        return {
            "schema": "diptrace-ui-profile/v1",
            "profile_id": self.profile_id,
            "editor": self.editor,
            "diptrace_version": self.diptrace_version,
            "window_title_contains": self.window_title_contains,
            "actions": actions,
            "transform": asdict(self.transform) if self.transform is not None else None,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> DipTraceUIProfile:
        if raw.get("schema") != "diptrace-ui-profile/v1":
            raise ValueError("unsupported DipTrace UI profile schema")
        editor_raw = raw.get("editor")
        if editor_raw not in {"pcb", "schematic"}:
            raise ValueError("DipTrace UI profile editor is invalid")
        actions_raw = raw.get("actions", {})
        if not isinstance(actions_raw, Mapping):
            raise ValueError("DipTrace UI profile actions must be an object")
        actions: dict[str, tuple[UIActionStep, ...]] = {}
        for action_name, action_steps in actions_raw.items():
            if not isinstance(action_name, str) or not action_name.strip():
                raise ValueError("DipTrace UI action name is invalid")
            if (
                not isinstance(action_steps, Sequence)
                or isinstance(action_steps, (str, bytes))
                or not action_steps
            ):
                raise ValueError(f"DipTrace UI action {action_name!r} must contain steps")
            actions[action_name] = tuple(
                _step_from_json(step, field_name=f"actions.{action_name}[{index}]")
                for index, step in enumerate(action_steps)
            )
        transform: DesignToClientTransform | None = None
        transform_raw = raw.get("transform")
        if transform_raw is not None:
            if not isinstance(transform_raw, Mapping):
                raise ValueError("DipTrace UI profile transform must be an object")
            transform = DesignToClientTransform(
                xx=float(transform_raw["xx"]),
                xy=float(transform_raw["xy"]),
                x0=float(transform_raw["x0"]),
                yx=float(transform_raw["yx"]),
                yy=float(transform_raw["yy"]),
                y0=float(transform_raw["y0"]),
            )
        return cls(
            profile_id=str(raw.get("profile_id") or ""),
            editor=cast(DipTraceEditor, editor_raw),
            diptrace_version=str(raw.get("diptrace_version") or ""),
            window_title_contains=str(raw.get("window_title_contains") or "DipTrace"),
            actions=actions,
            transform=transform,
        )

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, path: str | Path) -> DipTraceUIProfile:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("DipTrace UI profile root must be an object")
        return cls.from_dict(raw)


def make_diptrace_profile(
    editor: DipTraceEditor,
    *,
    version: str = "5.3",
    window_title_contains: str = "DipTrace",
) -> DipTraceUIProfile:
    """Create an explicit uncalibrated profile without guessed shortcuts or pixels."""

    if editor not in {"pcb", "schematic"}:
        raise ValueError("unsupported DipTrace editor")
    return DipTraceUIProfile(
        profile_id=f"diptrace-{version}-{editor}",
        editor=editor,
        diptrace_version=version,
        window_title_contains=window_title_contains,
    )


class DipTraceCinematicAdapter:
    """Translate planned DipTrace design geometry into executable desktop steps."""

    def __init__(self, profile: DipTraceUIProfile) -> None:
        self.profile = profile

    @staticmethod
    def _target_step(point: ClientPoint) -> dict[str, Any]:
        return {"move_to": [point.x, point.y], "click": "left", "click_count": 1}

    @staticmethod
    def _path_step(points: Sequence[ClientPoint]) -> dict[str, Any]:
        if len(points) < 2:
            raise ValueError("a wire or trace requires at least two points")
        return {
            "path": [[point.x, point.y] for point in points],
            "click": "left",
            "click_count": 1,
        }

    def _payload(self, steps: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        if not steps:
            raise ValueError("desktop playback requires at least one step")
        return {
            "desktop": {
                "window_title_contains": self.profile.window_title_contains,
                "steps": [dict(step) for step in steps],
            }
        }

    def place_component(
        self,
        component: str,
        x: float,
        y: float,
        *,
        context: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if not component.strip():
            raise ValueError("component identifier must not be empty")
        values = dict(context or {})
        values.setdefault("component", component)
        steps = self.profile.render_action("place_component", context=values)
        steps.append(self._target_step(self.profile.map_design(x, y)))
        steps.extend(
            self.profile.render_action("finish_place", context=values, optional=True)
        )
        return self._payload(steps)

    def route_trace(self, points: Sequence[DesignPoint], *, net: str = "") -> dict[str, Any]:
        if self.profile.editor != "pcb":
            raise ValueError("route_trace requires a PCB UI profile")
        context = {"net": net}
        steps = self.profile.render_action("route_trace", context=context)
        mapped = [self.profile.map_design(point.x, point.y) for point in points]
        steps.append(self._path_step(mapped))
        steps.extend(
            self.profile.render_action("finish_route", context=context, optional=True)
        )
        return self._payload(steps)

    def wire(self, points: Sequence[DesignPoint], *, net: str = "") -> dict[str, Any]:
        if self.profile.editor != "schematic":
            raise ValueError("wire requires a schematic UI profile")
        context = {"net": net}
        steps = self.profile.render_action("wire", context=context)
        mapped = [self.profile.map_design(point.x, point.y) for point in points]
        steps.append(self._path_step(mapped))
        steps.extend(
            self.profile.render_action("finish_wire", context=context, optional=True)
        )
        return self._payload(steps)

    def cancel(self) -> dict[str, Any]:
        return self._payload(self.profile.render_action("cancel"))
