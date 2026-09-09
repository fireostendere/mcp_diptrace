"""Version-bounded native CAD round-trips on a private Win32 desktop.

Only copies are opened. GUI messages target owned HWNDs; there is no physical
mouse/keyboard fallback. Native evidence is not a fabrication approval.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import Field

from .domain import StrictModel
from .headless_gui import (
    HeadlessGuiError,
    HiddenDesktop,
    _main_window,
    _post_menu_item,
    _post_window_message,
    _pywinauto_application,
    _save_dialog_as_xml,
    _save_dialog_controls,
    _wait_for_export,
    _Win32Api,
    input_desktop_name,
    thread_desktop_name,
)
from .windows_configurator import detect_diptrace_installations, validate_diptrace_directory
from .windows_job import KillOnCloseJob
from .xml_document import DipTraceDocument, sha256_bytes

PROFILE = "diptrace-5.3.0.3-en"
EXTENSIONS = {
    "pcb": ("Pcb.exe", ".dipxml", ".dip"),
    "schematic": ("Schematic.exe", ".dchxml", ".dch"),
    "component_library": ("CompEdit.exe", ".elixml", ".eli"),
    "pattern_library": ("PattEdit.exe", ".libxml", ".lib"),
}


class NativeCadRequest(StrictModel):
    source: Path
    output_dir: Path
    diptrace_root: Path
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    timeout_seconds: float = Field(default=120.0, gt=0, le=300, allow_inf_nan=False)
    export_manufacturing: bool = False


def installation_root() -> Path:
    """Installation choice is server-owned configuration, never an MCP executable argument."""
    configured = os.environ.get("DIPTRACE_MCP_DIPTRACE_ROOT")
    if configured:
        return validate_diptrace_directory(Path(configured)).root
    installations = detect_diptrace_installations()
    if not installations:
        raise HeadlessGuiError("A configured DipTrace 5.3.0.3 installation is required")
    return installations[0].root


def _dump(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding="utf-8")


def _visible(app: Any, *classes: str) -> list[Any]:
    found: list[Any] = []
    # Delphi destroys splash/dialog HWNDs while pywinauto enumerates them.
    with suppress(Exception):
        for window in app.windows(visible_only=True):
            with suppress(Exception):
                if window.class_name() in classes:
                    found.append(window)
    return found


def _dialog(app: Any, timeout: float, *classes: str) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = _visible(app, *classes)
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise HeadlessGuiError("Ambiguous native dialog identity")
        time.sleep(0.1)
    raise HeadlessGuiError(f"Expected native dialog did not appear: {classes}")


def _children(hwnd: int) -> list[int]:
    """Enumerate owned HWND children without filtering by the input desktop."""
    from ctypes import wintypes

    api = _Win32Api()
    handles: list[int] = []
    callback_type = ctypes.__dict__["WINFUNCTYPE"](wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def collect(child: int, _data: int) -> bool:
        if len(handles) >= 512:
            return False
        handles.append(int(child))
        return True

    api.user32.EnumChildWindows(hwnd, callback_type(collect), 0)
    return handles


def _control_info(hwnd: int) -> dict[str, Any]:
    import win32gui  # type: ignore[import-untyped]

    return {
        "handle": hwnd,
        "title": win32gui.GetWindowText(hwnd),
        "class": win32gui.GetClassName(hwnd),
        "id": win32gui.GetDlgCtrlID(hwnd),
        "rect": list(win32gui.GetWindowRect(hwnd)),
        "visible": bool(win32gui.IsWindowVisible(hwnd)),
        "enabled": bool(win32gui.IsWindowEnabled(hwnd)),
    }


def _controls(window: Any) -> list[dict[str, Any]]:
    return [_control_info(hwnd) for hwnd in _children(int(window.handle))]


def _capture(window: Any, path: Path) -> Any:
    """PrintWindow renders only the owned window, even on a hidden desktop."""
    from ctypes import wintypes

    import win32gui
    import win32ui  # type: ignore[import-untyped]
    from PIL import Image  # type: ignore[import-not-found]

    left, top, right, bottom = win32gui.GetWindowRect(window.handle)
    width, height = right - left, bottom - top
    if not 0 < width * height <= 16_000_000:
        raise HeadlessGuiError("Native capture dimensions exceed the bound")
    window_dc = win32gui.GetWindowDC(window.handle)
    source_dc = win32ui.CreateDCFromHandle(window_dc)
    memory_dc = source_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source_dc, width, height)
        memory_dc.SelectObject(bitmap)
        windll = ctypes.__dict__["windll"]
        render = windll.user32.PrintWindow
        render.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
        render.restype = wintypes.BOOL
        rendered = render(window.handle, memory_dc.GetSafeHdc(), 0)
        if not rendered:
            raise HeadlessGuiError("Native window refused off-screen rendering")
        image = Image.frombuffer(
            "RGB", (width, height), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1
        )
        image.save(path)
        return image
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory_dc.DeleteDC()
        source_dc.DeleteDC()
        win32gui.ReleaseDC(window.handle, window_dc)


def _texts(window: Any, app: Any) -> list[str]:
    texts = [str(window.window_text())]
    texts.extend(str(control.window_text()) for control in window.descendants()[:256])
    # UIA may expose labels which have no HWND in a Delphi dialog.
    with suppress(Exception):
        uia = _pywinauto_application()(backend="uia").connect(process=app.process)
        texts.extend(
            str(control.window_text())
            for control in uia.window(handle=window.handle).descendants()[:256]
        )
    return list(dict.fromkeys(text.strip() for text in texts if text.strip()))


def _click_caption(window: Any, caption: str) -> None:
    matches = [
        control
        for control in _controls(window)
        if str(control["title"]).replace("&", "").strip().casefold() == caption.casefold()
        and control["visible"]
        and control["enabled"]
    ]
    if len(matches) != 1:
        raise HeadlessGuiError(f"Native control not uniquely resolved: {caption}")
    _post_window_message(int(matches[0]["handle"]), 0x00F5)  # BM_CLICK, no input desktop


def _set_checked(window: Any, caption: str, checked: bool) -> None:
    matches = [
        item
        for item in _controls(window)
        if str(item["title"]).replace("&", "").strip() == caption
        and item["visible"]
        and item["enabled"]
    ]
    if len(matches) != 1:
        raise HeadlessGuiError(f"Native checkbox is not unique: {caption}")
    hwnd = int(matches[0]["handle"])
    api = _Win32Api()
    if int(api.user32.SendMessageW(hwnd, 0x00F0, 0, 0)) != int(checked):
        _post_window_message(hwnd, 0x00F5)
    deadline = time.monotonic() + 3
    while int(api.user32.SendMessageW(hwnd, 0x00F0, 0, 0)) != int(checked):
        if time.monotonic() >= deadline:
            raise HeadlessGuiError(f"Native checkbox state did not change: {caption}")
        time.sleep(0.05)


def _drc_bitmap_status(image: Any, dialog_class: str) -> str:
    # Exact message-glyph fingerprint, observed in two independent runs of
    # DipTrace 5.3.0.3 EN / Win32 96-DPI. This is not OCR or a class-name heuristic.
    # Different DPI/font/text must stay unknown. Full-window evidence is retained.
    if dialog_class != "TFMyMessage" or image.size != (306, 117):
        return "visual_review_required"
    body = image.crop((8, 30, image.width - 8, image.height - 42)).convert("L")
    pixels = body.point(lambda value: 255 if value < 128 else 0)
    box = pixels.getbbox()
    if box is None:
        return "visual_review_required"
    glyphs = pixels.crop(box)
    if glyphs.size == (84, 10) and hashlib.sha256(glyphs.tobytes()).hexdigest() == (
        "8c8fc31460a31b05a3a51824dd3d11b03a2847c21095eddbe317b65eef2ee5f1"
    ):
        return "pass"
    return "visual_review_required"


def _acknowledge_startup(app: Any, output: Path) -> None:
    # A private desktop may start with a graphics-backend warning. Record it;
    # acknowledging on a disposable copy cannot certify a successfully loaded design.
    time.sleep(1.0)
    for index, dialog in enumerate(_visible(app, "TFMyMessage")):
        _capture(dialog, output / f"startup-{index}.png")
        _dump(
            output / f"startup-{index}.json",
            {"texts": _texts(dialog, app), "controls": _controls(dialog)},
        )
        _click_caption(dialog, "OK")
    time.sleep(0.2)


def _save_as(app: Any, window: Any, target: Path, timeout: float, *, xml: bool) -> None:
    if target.exists():
        raise HeadlessGuiError("Native output must not overwrite an existing file")
    _post_menu_item(window, window.menu_item("#0->#4"))
    dialog = _dialog(app, timeout, "#32770")
    deadline = time.monotonic() + min(timeout, 10)
    while True:
        try:
            _save_dialog_controls(int(dialog.handle))
            break
        except HeadlessGuiError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)
    if xml:
        _save_dialog_as_xml(int(dialog.handle), target)
    else:
        _save_filename(dialog, target, native_extension=target.suffix)
    _wait_for_export(app, target, timeout)


def _save_filename(dialog: Any, target: Path, *, native_extension: str | None = None) -> None:
    api = _Win32Api()
    edit, combo = _save_dialog_controls(int(dialog.handle))
    if native_extension is not None:
        count = int(api.user32.SendMessageW(combo, 0x0146, 0, 0))  # CB_GETCOUNT
        matching: list[int] = []
        choices: list[str] = []
        for index in range(max(0, min(count, 100))):
            text = ctypes.create_unicode_buffer(1024)
            api.user32.SendMessageW(combo, 0x0148, index, ctypes.addressof(text))
            choices.append(text.value)
            if (
                "xml" not in text.value.casefold()
                and f"*{native_extension}" in text.value.casefold()
            ):
                matching.append(index)
        if len(matching) != 1:
            raise HeadlessGuiError(f"Native file format not unique: {choices}")
        api.user32.SendMessageW(combo, 0x014E, matching[0], 0)  # CB_SETCURSEL
        for notification in (9, 1, 8):  # CBN_SELENDOK, SELCHANGE, CLOSEUP
            _post_window_message(int(dialog.handle), 0x0111, 1136 | (notification << 16), combo)
        time.sleep(0.2)
    text = ctypes.create_unicode_buffer(str(target))
    api.user32.SendMessageW(edit, 0x000C, 0, ctypes.addressof(text))
    _post_window_message(int(dialog.handle), 0x0111, 1, 0)


def _menu_item_rect(hwnd: int, menu: int, item: int) -> tuple[int, int, int, int]:
    """Read a menu rectangle without pywin32's version-dependent tuple wrapper."""
    from ctypes import wintypes

    rect = wintypes.RECT()
    get_rect = _Win32Api().user32.GetMenuItemRect
    get_rect.argtypes = [
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.UINT,
        ctypes.POINTER(wintypes.RECT),
    ]
    get_rect.restype = wintypes.BOOL
    if not get_rect(hwnd, menu, item, ctypes.byref(rect)):
        raise HeadlessGuiError("Native export menu item has no rectangle")
    return rect.left, rect.top, rect.right, rect.bottom


def _window_thread_process(hwnd: int) -> tuple[int, int]:
    from ctypes import wintypes

    process_id = wintypes.DWORD()
    get_process_id = _Win32Api().user32.GetWindowThreadProcessId
    get_process_id.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    get_process_id.restype = wintypes.DWORD
    thread_id = int(get_process_id(hwnd, ctypes.byref(process_id)))
    if not thread_id:
        raise HeadlessGuiError("Native export window has no owning thread")
    return thread_id, int(process_id.value)


def _menu_owner(thread_id: int) -> int:
    from ctypes import wintypes

    class GuiThreadInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND),
            ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND),
            ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND),
            ("hwndCaret", wintypes.HWND),
            ("rcCaret", wintypes.RECT),
        ]

    info = GuiThreadInfo(cbSize=ctypes.sizeof(GuiThreadInfo))
    get_info = _Win32Api().user32.GetGUIThreadInfo
    get_info.argtypes = [wintypes.DWORD, ctypes.POINTER(GuiThreadInfo)]
    get_info.restype = wintypes.BOOL
    if not get_info(thread_id, ctypes.byref(info)) or not info.hwndMenuOwner:
        raise HeadlessGuiError("Native export menu has no owner")
    return int(info.hwndMenuOwner)


def _native_export(app: Any, window: Any, output: Path, timeout: float) -> dict[str, Any]:
    import win32gui

    _post_menu_item(window, window.menu_item("#0->#9->#5"))
    drill = _dialog(app, min(timeout, 20), "TDrillForm")
    time.sleep(0.2)
    _dump(output / "drill-controls.json", {"controls": _controls(drill)})
    _set_checked(drill, "Metric", True)
    _set_checked(drill, "Use Design Origin", True)
    _set_checked(drill, "Mirror", False)
    _capture(drill, output / "drill-settings.png")
    _click_caption(drill, "Close")
    time.sleep(0.2)
    _post_menu_item(window, window.menu_item("#0->#9->#4"))  # observed 5.3.0.3 Export/Gerber X2
    dialog = _dialog(app, timeout, "TExpForm")
    _dump(output / "gerber-controls.json", {"controls": _controls(dialog)})
    _capture(dialog, output / "gerber-dialog.png")
    _set_checked(dialog, "Metric", True)
    _set_checked(dialog, "Use Design Origin", True)
    _set_checked(dialog, "Mirror", False)
    _capture(dialog, output / "gerber-settings.png")
    _click_caption(dialog, "Export All...")
    popup = _dialog(app, timeout, "#32768")
    menu = win32gui.SendMessage(popup.handle, 0x01E1, 0, 0)  # MN_GETHMENU
    if not menu or win32gui.GetMenuItemCount(menu) != 3:
        raise HeadlessGuiError("Unexpected native Export All popup")
    # Delphi's popup has no GW_OWNER. GUITHREADINFO exposes the actual menu owner.
    left, top, right, bottom = _menu_item_rect(int(popup.handle), int(menu), 1)
    command = int(win32gui.GetMenuItemID(menu, 1))
    thread_id, popup_pid = _window_thread_process(int(popup.handle))
    owner = _menu_owner(thread_id)
    _, owner_pid = _window_thread_process(owner)
    _dump(
        output / "gerber-popup.json",
        {
            "menu": int(menu),
            "rect": [left, top, right, bottom],
            "popup_pid": popup_pid,
            "owner": owner,
            "owner_pid": owner_pid,
            "process": int(app.process),
            "command": command,
        },
    )
    if popup_pid != int(app.process) or owner_pid != int(app.process):
        raise HeadlessGuiError("Native export popup ownership is invalid")
    if not 1 <= command <= 0xFFFF:
        raise HeadlessGuiError("Native export popup command is invalid")
    _capture(popup, output / "gerber-popup.png")
    _post_window_message(owner, 0x001F)  # WM_CANCELMODE
    _post_window_message(owner, 0x0111, command)  # WM_COMMAND
    save = _dialog(app, min(timeout, 20), "#32770")
    _save_filename(save, output / "native-fabrication.zip")
    _wait_for_export(app, output / "native-fabrication.zip", timeout)
    _post_window_message(dialog.handle, 0x0010)
    time.sleep(0.2)
    _native_placement(app, window, output, timeout)
    return {
        "assembly_exporter": "DipTrace Pick and Place",
        "exporter": "DipTrace Gerber X2 + NC Drill ZIP",
        "ui_profile": PROFILE,
        "units_requested": "mm",
        "origin": "design_origin",
        "mirror": False,
    }


def _combo_items(hwnd: int) -> list[str]:
    api = _Win32Api()
    count = int(api.user32.SendMessageW(hwnd, 0x0146, 0, 0))
    if not 0 < count <= 64:
        raise HeadlessGuiError("Unexpected native combo size")
    result = []
    for index in range(count):
        length = int(api.user32.SendMessageW(hwnd, 0x0149, index, 0))
        if not 0 <= length < 1024:
            raise HeadlessGuiError("Native combo text exceeds the bound")
        text = ctypes.create_unicode_buffer(length + 1)
        api.user32.SendMessageW(hwnd, 0x0148, index, ctypes.addressof(text))
        result.append(text.value)
    return result


def _choose_combo(hwnd: int, index: int) -> None:
    import win32gui

    api = _Win32Api()
    api.user32.SendMessageW(hwnd, 0x014E, index, 0)
    parent, control_id = win32gui.GetParent(hwnd), win32gui.GetDlgCtrlID(hwnd)
    for notification in (9, 1, 8):
        _post_window_message(parent, 0x0111, (control_id & 0xFFFF) | (notification << 16), hwnd)
    if int(api.user32.SendMessageW(hwnd, 0x0147, 0, 0)) != index:
        raise HeadlessGuiError("Native combo selection did not persist")


def _native_placement(app: Any, window: Any, output: Path, timeout: float) -> None:
    _post_menu_item(window, window.menu_item("#0->#9->#12"))
    dialog = _dialog(app, min(timeout, 20), "TForm54")
    time.sleep(0.2)
    _dump(output / "placement-controls.json", {"controls": _controls(dialog)})
    _capture(dialog, output / "placement-before.png")
    _set_checked(dialog, "Use Design Origin", True)
    _set_checked(dialog, "Mirror", False)
    selected_units = False
    for control in _controls(dialog):
        if control["class"] not in {"TComboBox", "ComboBox"}:
            continue
        hwnd = int(control["handle"])
        options = _combo_items(hwnd)
        lowered = [name.casefold() for name in options]
        if "millimeters" in lowered:
            _choose_combo(hwnd, lowered.index("millimeters"))
            selected_units = True
        elif set(lowered) == {"all", "top", "bottom"}:
            _choose_combo(hwnd, lowered.index("all"))
        elif set(options) == {".", ","}:
            _choose_combo(hwnd, options.index("."))
    if not selected_units:
        raise HeadlessGuiError("Native placement metric units were not resolved")
    _capture(dialog, output / "placement-settings.png")
    _click_caption(dialog, "Export to File")
    save = _dialog(app, min(timeout, 20), "#32770")
    time.sleep(0.2)
    _save_filename(save, output / "native-placement.csv", native_extension=".csv")
    csv_settings = _dialog(app, min(timeout, 20), "TForm_CSVSettings")
    _dump(output / "placement-csv-controls.json", {"controls": _controls(csv_settings)})
    _capture(csv_settings, output / "placement-csv-settings.png")
    _click_caption(csv_settings, "OK")
    _wait_for_export(app, output / "native-placement.csv", timeout)
    _post_window_message(int(dialog.handle), 0x0010)


def _worker(request: NativeCadRequest, desktop: str) -> dict[str, Any]:
    if thread_desktop_name() != desktop:
        raise HeadlessGuiError("Worker desktop does not match its isolated launch")
    source = DipTraceDocument.load(request.source, 64 * 1024 * 1024)
    if source.sha256 != request.expected_sha256:
        raise HeadlessGuiError("Native source hash is stale")
    if source.kind not in EXTENSIONS:
        raise HeadlessGuiError("Unsupported native editor")
    executable_name, xml_extension, binary_extension = EXTENSIONS[source.kind]
    executable = request.diptrace_root / executable_name
    import win32api  # type: ignore[import-untyped]

    version_info = win32api.GetFileVersionInfo(str(executable), "\\")
    ms, ls = version_info["FileVersionMS"], version_info["FileVersionLS"]
    version = ".".join(str(value) for value in (ms >> 16, ms & 65535, ls >> 16, ls & 65535))
    if version != "5.3.0.3":
        raise HeadlessGuiError(f"Unsupported native UI build {version}; expected 5.3.0.3")
    output = request.output_dir
    working = output / ("input" + xml_extension)
    working.write_bytes(source.raw_bytes)
    binary = output / ("saved" + binary_extension)
    reexport = output / ("reexport" + xml_extension)
    report: dict[str, Any] = {
        "schema_version": 1,
        "source_sha256": source.sha256,
        "source_type": source.source_type,
        "ui_profile": PROFILE,
        "version": version,
        "executable_sha256": sha256_bytes(executable.read_bytes()),
        "desktop": desktop,
        "steps": [],
        "drc_status": "not_applicable" if source.kind != "pcb" else "not_run",
        "completed": False,
        "fabrication_approved": False,
    }
    app: Any = None
    try:
        for phase, opened in (("open_save_close", working), ("reopen_reexport", binary)):
            app = _pywinauto_application()(backend="win32").start(
                subprocess.list2cmdline([str(executable), str(opened)]),
                timeout=request.timeout_seconds,
            )
            deadline = time.monotonic() + request.timeout_seconds
            while True:
                try:
                    _acknowledge_startup(app, output)
                    window = _main_window(app, opened, min(2.0, request.timeout_seconds))
                    break
                except Exception:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            report["steps"].append({"step": phase, "pid": int(app.process)})
            if phase == "open_save_close":
                _save_as(app, window, binary, request.timeout_seconds, xml=False)
            else:
                if source.kind == "pcb":
                    _post_menu_item(window, window.menu_item("#3->#14"))
                    _post_menu_item(window, window.menu_item("#7->#0"))
                    dialog = _dialog(app, request.timeout_seconds, "TFMyMessage", "TForm60")
                    report["drc_texts"] = _texts(dialog, app)
                    report["drc_dialog_class"] = dialog.class_name()
                    image = _capture(dialog, output / "drc.png")
                    report["drc_status"] = (
                        "pass"
                        if any(
                            text.casefold() in {"no errors", "no errors found"}
                            for text in report["drc_texts"]
                        )
                        else "fail"
                        if dialog.class_name() == "TForm60"
                        else _drc_bitmap_status(image, dialog.class_name())
                    )
                    report["drc_recognition"] = "text_or_version_bound_message_bitmap"
                    _post_window_message(dialog.handle, 0x0010)
                _save_as(app, window, reexport, request.timeout_seconds, xml=True)
                if request.export_manufacturing:
                    if source.kind != "pcb":
                        raise HeadlessGuiError("Manufacturing export requires PCB")
                    report["manufacturing"] = _native_export(
                        app, window, output, request.timeout_seconds
                    )
            _post_window_message(int(window.handle), 0x0010)
            app.wait_for_process_exit(timeout=15)
            app = None
        report["reexport_sha256"] = sha256_bytes(reexport.read_bytes())
        report["binary_sha256"] = sha256_bytes(binary.read_bytes())
        report["completed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        if app is not None:
            report["windows"] = []
            for window in app.windows(visible_only=True):
                if window.class_name() != "TApplication":
                    with suppress(Exception):
                        report["windows"].append(
                            {
                                "title": window.window_text(),
                                "class": window.class_name(),
                                "controls": _controls(window),
                            }
                        )
                        _capture(
                            window,
                            output / ("failed-" + window.class_name().replace("#", "") + ".png"),
                        )
    finally:
        if app is not None:
            with suppress(Exception):
                app.kill(soft=False)
        _dump(output / "native-result.json", report)
    return report


def run_native_cad(request: NativeCadRequest) -> dict[str, Any]:
    if os.name != "nt":
        raise HeadlessGuiError("Native CAD adapter currently requires Windows")
    request = request.model_copy(
        update={
            "source": request.source.resolve(),
            "output_dir": request.output_dir.resolve(),
            "diptrace_root": request.diptrace_root.resolve(),
        }
    )
    if request.output_dir.exists():
        raise HeadlessGuiError("Native output directory must be new")
    source_sha = DipTraceDocument.load(request.source, 64 * 1024 * 1024).sha256
    if source_sha != request.expected_sha256:
        raise HeadlessGuiError("Native input hash is stale")
    request.output_dir.mkdir(parents=True)
    name = "DipTracePlatform-" + uuid.uuid4().hex[:16]
    before = input_desktop_name()
    request_file = request.output_dir / "request.json"
    _dump(request_file, request.model_dump(mode="json"))
    start_signal = request.output_dir / "worker-start"
    with HiddenDesktop(name) as hidden:
        argv = [
            sys.executable,
            "-m",
            "diptrace_mcp.native_cad",
            "--worker",
            str(request_file),
            "--desktop",
            name,
        ]
        with hidden.launch(argv) as child:
            job = KillOnCloseJob.create()
            try:
                job.assign(child.pid)
                start_signal.write_text("start", encoding="ascii")
                code = child.wait(request.timeout_seconds + 30)
                if code is None:
                    raise HeadlessGuiError("Native CAD worker timeout")
            finally:
                job.terminate_and_close()
    result_path = request.output_dir / "native-result.json"
    if not result_path.is_file():
        raise HeadlessGuiError("Native worker did not produce evidence")
    if result_path.stat().st_size > 2 * 1024 * 1024:
        raise HeadlessGuiError("Native evidence exceeds size limit")
    report = json.loads(result_path.read_text(encoding="utf-8"))
    report["worker_exit_code"] = code
    report["input_desktop_unchanged"] = before is not None and input_desktop_name() == before
    report["source_unchanged"] = sha256_bytes(request.source.read_bytes()) == source_sha
    if code != 0 or not report["input_desktop_unchanged"] or not report["source_unchanged"]:
        report["completed"] = False
        report.setdefault("error", "Native isolation invariant failed")
    _dump(result_path, report)
    return dict(report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--desktop", required=True)
    args = parser.parse_args()
    request = NativeCadRequest.model_validate_json(args.worker.read_bytes())
    # No CAD process starts before the parent has assigned its kill-on-close Job.
    deadline = time.monotonic() + 15
    while not (request.output_dir / "worker-start").is_file():
        if time.monotonic() >= deadline:
            raise HeadlessGuiError("Parent failed to establish process ownership")
        time.sleep(0.05)
    report = _worker(request, args.desktop)
    raise SystemExit(0 if report["completed"] else 1)


if __name__ == "__main__":
    main()
