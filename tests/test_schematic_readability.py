"""Synthetic regressions and an opt-in local reproduction; no redistributed private CAD."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from diptrace_mcp.adapters import build_snapshot
from diptrace_mcp.config import Settings
from diptrace_mcp.errors import DocumentError
from diptrace_mcp.review import run_checks
from diptrace_mcp.server import create_server
from diptrace_mcp.xml_document import DipTraceDocument
from scripts.pcb_quality_gate import main as quality_gate_main
from scripts.pcb_quality_gate import run_schematic_review


def _root() -> ET.Element:
    root = ET.fromstring(
        '<Source Type="DipTrace-Schematic" Version="4.3.0.3" Units="mm">'
        '<Library Type="DipTrace-ComponentLibrary"><Components/></Library>'
        '<Schematic><SheetSettings><ActiveSheet>0</ActiveSheet><Sheets/></SheetSettings>'
        '<Components/><Nets/><Shapes/></Schematic></Source>'
    )
    sheets = root.find('./Schematic/SheetSettings/Sheets')
    nets = root.find('./Schematic/Nets')
    assert sheets is not None and nets is not None
    for index in range(3):
        sheet = ET.SubElement(sheets, 'Sheet')
        for field, value in (
            ('Id', str(index + 10)), ('Name', f'Sheet {index}'), ('Type', 'Normal'),
            ('SheetWidth', '200'), ('SheetHeight', '200'), ('LeftMargin', '5'),
            ('RightMargin', '5'), ('TopMargin', '5'), ('BottomMargin', '5'),
        ):
            ET.SubElement(sheet, field).text = value
    for index in range(2):
        net = ET.SubElement(nets, 'Net', Id=str(index))
        ET.SubElement(net, 'Name').text = f'SIGNAL_{index}'
        ET.SubElement(net, 'Pins')
        ET.SubElement(net, 'Wires')
    return root


def _wire(root: ET.Element, net: int, points: list[tuple[float, float]], sheet: int = 1):
    wires = root.find(f'./Schematic/Nets/Net[@Id="{net}"]/Wires')
    assert wires is not None
    wire = ET.SubElement(wires, 'Wire', Id=str(len(wires)), Sheet=str(sheet))
    container = ET.SubElement(wire, 'Points')
    for x, y in points:
        ET.SubElement(container, 'Point', X=str(x), Y=str(y))
    return wire


def _shape(root: ET.Element, kind: str, points: list[tuple[float, float]], sheet: int = 0):
    shapes = root.find('./Schematic/Shapes')
    assert shapes is not None
    shape = ET.SubElement(shapes, 'Shape', Type=kind, Id=str(len(shapes)), Sheet=str(sheet))
    container = ET.SubElement(shape, 'Points')
    for x, y in points:
        ET.SubElement(container, 'Point', X=str(x), Y=str(y))
    return shape


def _part(root: ET.Element, *, port: bool = False, x: float = 0, sheet: int = 1):
    components = root.find('./Library/Components')
    instances = root.find('./Schematic/Components')
    assert components is not None and instances is not None
    index = len(components)
    component = ET.SubElement(components, 'Component', ComponentStyle=f'CompType{index}')
    unit = ET.SubElement(component, 'Part', Id='0', Width='2', Height='2',
                         PartType='Net Port' if port else 'Normal', RefDes='NP' if port else 'U')
    ET.SubElement(unit, 'Name').text = f'SYMBOL_{index}'
    pins = ET.SubElement(unit, 'Pins')
    pin = ET.SubElement(pins, 'Pin', Id='0', X='1', Y='0', Length='4', Orientation='180',
                        ElectricType='Passive')
    ET.SubElement(pin, 'Name').text = 'IO'
    shapes = ET.SubElement(unit, 'Shapes')
    shape = ET.SubElement(shapes, 'Shape', Type='Rectangle', Id='0')
    points = ET.SubElement(shape, 'Points')
    ET.SubElement(points, 'Point', X='-1', Y='-1')
    ET.SubElement(points, 'Point', X='1', Y='1')
    instance = ET.SubElement(instances, 'Part', Id=str(index), ComponentStyle=f'CompType{index}',
                            ComponentPart='0', Sheet=str(sheet), X=str(x), Y='0', Angle='0')
    ET.SubElement(instance, 'Name').text = 'SIGNAL_1' if port else f'SYMBOL_{index}'
    ET.SubElement(instance, 'RefDes').text = f'NP{index}' if port else f'U{index}'
    ET.SubElement(ET.SubElement(instance, 'Pins'), 'Pin', NetId='1' if port else '0')
    return instance, unit


def _snapshot(root: ET.Element):
    return build_snapshot(DipTraceDocument.from_bytes(Path('synthetic.dchxml'), ET.tostring(root)))


def _review(root: ET.Element, **kwargs):
    findings, metrics, skipped, count = run_checks(_snapshot(root), categories={'readability'},
                                                   **kwargs)
    assert count == 1
    return findings, metrics['schematic.readability'], skipped


def test_inactive_sheet_full_polyline_crossing_blocks_whole_review_and_gate(tmp_path: Path):
    root = _root()
    _wire(root, 0, [(-10, -10), (-10, 0), (10, 0)])
    _wire(root, 1, [(0, -5), (0, 5)])
    findings, metrics, skipped = _review(root)
    assert not skipped
    assert metrics['scope'] == 'all_sheets'
    assert metrics['checked_sheet_indices'] == [0, 1, 2]
    assert [row['different_net_crossings'] for row in metrics['sheets']] == [0, 1, 0]
    assert [finding.check_id for finding in findings] == ['schematic.readability.wire_crossing']
    assert findings[0].severity == 'error' and findings[0].object_ids
    assert [f.finding_id for f in findings] == [f.finding_id for f in _review(root)[0]]
    path = tmp_path / 'schematic.dchxml'
    path.write_bytes(ET.tostring(root))
    report = run_schematic_review(path)
    assert report['errors']['schematic.readability.wire_crossing'] == 1
    assert report['readability']['checked_sheet_indices'] == [0, 1, 2]


@pytest.mark.parametrize(('second', 'net', 'crossings', 'overlaps'), [
    ([(0, -5), (0, 5)], 1, 1, 0),
    ([(0, 0), (20, 0)], 1, 0, 1),
    ([(0, -5), (0, 5)], 0, 0, 0),  # intentional same-net junction
    ([(0, 0), (20, 0)], 0, 0, 1),  # same-net duplicate lane is still ambiguous
    ([(10, 0), (20, 0)], 1, 1, 0),  # foreign-net shared endpoint is not a junction
])
def test_point_contacts_and_collinear_overlaps_are_distinct(second, net, crossings, overlaps):
    root = _root()
    _wire(root, 0, [(-10, 0), (10, 0)])
    _wire(root, net, second)
    _, metrics, skipped = _review(root)
    assert not skipped
    assert metrics['sheets'][1]['different_net_crossings'] == crossings
    assert metrics['sheets'][1]['collinear_overlaps'] == overlaps


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('diagonal', [False, True])
def test_contained_collinear_overlap_is_detected_in_both_orders(
    reverse: bool, diagonal: bool, tmp_path: Path,
):
    root = _root()
    short = [(0, 0), (1, 1 if diagonal else 0)]
    long = [(-1, -1 if diagonal else 0), (2, 2 if diagonal else 0)]
    for points in ([long, short] if reverse else [short, long]):
        _wire(root, 0, points)
    findings, metrics, skipped = _review(root)
    assert not skipped
    assert metrics['sheets'][1]['collinear_overlaps'] == 1
    assert metrics['sheets'][1]['different_net_crossings'] == 0
    assert [f.check_id for f in findings] == ['schematic.readability.wire_overlap']
    path = tmp_path / 'overlap.dchxml'
    path.write_bytes(ET.tostring(root))
    assert run_schematic_review(path)['errors']['schematic.readability.wire_overlap'] == 1


def test_documentary_lines_are_separate_from_rectangle_borders_and_shared_endpoints():
    root = _root()
    _shape(root, 'Rectangle', [(-10, -10), (10, 10)])
    _shape(root, 'Line', [(-20, 0), (20, 0)])
    _shape(root, 'Line', [(0, -20), (0, 20)])
    _shape(root, 'Line', [(20, 0), (30, 0)])
    _shape(root, 'Line', [(-5, 0), (5, 0)])
    _, metrics, skipped = _review(root)
    assert not skipped
    assert metrics['sheets'][0]['documentary_segments'] == 4
    assert metrics['sheets'][0]['documentary_crossings'] == 2
    assert metrics['sheets'][0]['documentary_overlaps'] == 1
    assert metrics['sheets'][0]['different_net_crossings'] == 0


def test_explicit_sheet_scope_is_bounded_and_cannot_claim_design_wide_coverage():
    root = _root()
    _wire(root, 0, [(-10, 0), (10, 0)])
    _wire(root, 1, [(0, -5), (0, 5)])
    snapshot = _snapshot(root)
    before = snapshot.schematic.model_dump()
    findings, metrics, skipped = _review(root, sheets=[0, 2])
    assert not findings and not skipped
    assert metrics['scope'] == 'selected_sheets'
    assert metrics['checked_sheet_indices'] == [0, 2]
    assert metrics['excluded_sheet_indices'] == [1]
    assert metrics['all_sheets_checked'] is False
    assert snapshot.schematic.model_dump() == before


@pytest.mark.parametrize('sheets', [[], [99], [-1], [True], [0, 0], list(range(257))])
def test_invalid_sheet_selectors_fail_closed(sheets):
    with pytest.raises(DocumentError):
        _review(_root(), sheets=sheets)


@pytest.mark.parametrize('points', [[], [(0, 0)], [(0, 0), (0, 0)]])
def test_missing_wire_geometry_is_not_a_clean_result(points):
    root = _root()
    _wire(root, 0, points)
    _, metrics, skipped = _review(root)
    assert skipped and metrics['geometry_complete'] is False
    assert metrics['sheets'][1]['missing_geometry']


def test_missing_coordinate_and_undeclared_sheet_are_explicit():
    root = _root()
    wire = _wire(root, 0, [(-10, 0), (10, 0)])
    wire.find('./Points/Point').attrib.pop('X')
    _wire(root, 1, [(0, -5), (0, 5)], sheet=99)
    _, metrics, skipped = _review(root)
    assert skipped and metrics['geometry_complete'] is False
    assert metrics['unassigned_objects']


def test_glyph_and_foreign_pin_stub_conflicts_and_legitimate_pin_attachment():
    root = _root()
    _part(root)
    _wire(root, 1, [(-10, 0), (10, 0)])
    findings, metrics, _ = _review(root)
    assert {'schematic.readability.wire_body', 'schematic.readability.wire_pin_stub'} <= {
        f.check_id for f in findings
    }
    assert metrics['sheets'][1]['pin_stubs_checked'] == 1
    root = _root()
    _part(root)
    wire = _wire(root, 0, [(5, 0), (10, 0)])
    wire.attrib.update(Connected1='Pin', Object1='0', SubObject1='0')
    assert not _review(root)[0]


def test_legitimate_tip_contact_does_not_hide_a_later_shaft_crossing():
    root = _root()
    _part(root)
    wire = _wire(root, 0, [(5, 0), (10, 0), (10, -5), (3, -5), (3, 5)])
    wire.attrib.update(Connected1='Pin', Object1='0', SubObject1='0')
    findings, metrics, skipped = _review(root)
    assert not skipped
    assert 'schematic.readability.wire_pin_stub' in {f.check_id for f in findings}
    assert metrics['sheets'][1]['pin_stub_conflicts'] == 1


def test_port_tip_on_foreign_pin_shaft_without_any_wire_is_detected():
    root = _root()
    _part(root)
    _part(root, port=True, x=-2)
    findings, metrics, _ = _review(root)
    assert 'schematic.readability.port_tip' in {f.check_id for f in findings}
    assert metrics['sheets'][1]['port_tip_conflicts'] == 1


def test_caption_orientation_clearance_and_containment_with_native_metric_limits():
    root = _root()
    part, _ = _part(root)
    ET.SubElement(part, 'RefDesMarking', Show='Show', Align='Position', Horz='Left',
                  Vert='Bottom', X='3', Y='0', Angle=str(math.pi / 2),
                  TextWidth='4', TextHeight='2')
    text = _shape(root, 'Text', [(96, 0)], sheet=1)
    text.attrib.update(TextWidth='10', TextHeight='2', Angle='0')
    ET.SubElement(ET.SubElement(text, 'TextLines'), 'TextLine').text = 'NOTE'
    findings, metrics, _ = _review(root)
    assert {'schematic.readability.text_orientation', 'schematic.readability.text_collision',
            'schematic.readability.sheet_containment'} <= {f.check_id for f in findings}
    assert metrics['limitations'] and metrics['text_evidence_class'] == 'heuristic'


@pytest.mark.parametrize('stored_bounds', [False, True])
def test_estimated_marking_conflict_warns_instead_of_claiming_measured_failure(
    stored_bounds, tmp_path: Path,
):
    root = _root()
    part, _ = _part(root)
    marking = ET.SubElement(part, 'RefDesMarking', Show='Show', Align='Position', Horz='Left',
                            Vert='Bottom', X='3', Y='-1', Angle='0')
    if stored_bounds:
        marking.attrib.update(TextWidth='4', TextHeight='2')
    findings, metrics, skipped = _review(root)
    assert not skipped
    collisions = [f for f in findings if f.check_id == 'schematic.readability.text_collision']
    assert collisions
    assert {f.severity for f in collisions} == {'error' if stored_bounds else 'warning'}
    row = metrics['sheets'][1]
    assert row['stored_texts_checked'] == int(stored_bounds)
    assert row['estimated_texts_checked'] == int(not stored_bounds)
    path = tmp_path / 'marking.dchxml'
    path.write_bytes(ET.tostring(root))
    report = run_schematic_review(path)
    bucket = 'errors' if stored_bounds else 'warnings'
    assert report[bucket]['schematic.readability.text_collision'] > 0
    if not stored_bounds:
        assert not report['errors']


def test_missing_symbol_geometry_is_reported_without_proxy_acceptance():
    root = _root()
    _part(root)
    root.find('./Library/Components').clear()
    _, metrics, skipped = _review(root)
    assert skipped and metrics['geometry_complete'] is False
    assert metrics['sheets'][1]['missing_geometry']


def test_public_mcp_contract_defaults_to_all_sheets_and_preserves_scope(tmp_path: Path):
    root = _root()
    _wire(root, 0, [(-10, 0), (10, 0)])
    _wire(root, 1, [(0, -5), (0, 5)])
    path = tmp_path / 'schematic.dchxml'
    source = ET.tostring(root)
    path.write_bytes(source)
    shutil.copyfile(Path(__file__).parent / 'fixtures/pcb.xml', tmp_path / 'pcb.xml')

    async def verify():
        server = create_server(Settings(workspace=tmp_path, allowed_roots=(tmp_path,),
                                        state_dir=tmp_path / 'state'))
        async with create_connected_server_and_client_session(
            server.protocol_server, read_timeout_seconds=timedelta(seconds=30),
        ) as session:
            tools = await session.list_tools()
            tool = next(tool for tool in tools.tools if tool.name == 'run_review')
            props = tool.inputSchema['properties']
            assert 'schematic_readability' in props['profile']['enum']
            selector = props['sheets']
            assert selector['type'] == 'array'
            assert selector['minItems'] == 1 and selector['maxItems'] == 256
            assert selector['items']['minimum'] == 0
            for profile, sheets, expected in (
                ('schematic_readability', None, 1), ('schematic_review', None, 1),
                ('schematic_readability', [0, 2], 0),
            ):
                args = {'profile': profile, 'path': str(path)}
                if sheets is not None:
                    args['sheets'] = sheets
                response = await session.call_tool('run_review', args)
                assert not response.isError, response.content
                content = response.structuredContent
                assert content is not None and content['ok'] is True
                result = content['result']
                metrics = result['metrics']['schematic.readability']
                assert metrics['sheets'][0]['index'] == 0
                assert metrics['all_sheets_checked'] is (sheets is None)
                assert sum(s['different_net_crossings'] for s in metrics['sheets']) == expected
                assert content['document']['sha256'] == hashlib.sha256(source).hexdigest()
                assert result['summary']['by_severity']['error'] == expected
            for profile, sheets in (
                ('schematic_readability', []), ('schematic_readability', [99]),
                ('schematic_readability', [0, 0]), ('schematic_readability', [True]),
                ('schematic_readability', [1.5]), ('schematic_readability', list(range(257))),
                ('schematic_review', [0]), ('erc_basic', [0]),
            ):
                response = await session.call_tool('run_review', {
                    'profile': profile, 'path': str(path), 'sheets': sheets,
                })
                assert response.isError or response.structuredContent['ok'] is False
            response = await session.call_tool('run_review', {
                'profile': 'schematic_readability', 'path': str(tmp_path / 'pcb.xml'),
            })
            assert response.isError or response.structuredContent['ok'] is False

    asyncio.run(verify())
    assert path.read_bytes() == source


def test_quality_gate_fails_for_a_crossing_on_an_inactive_sheet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
):
    root = _root()
    _wire(root, 0, [(-10, 0), (10, 0)], sheet=2)
    _wire(root, 1, [(0, -5), (0, 5)], sheet=2)
    path = tmp_path / 'candidate.dchxml'
    path.write_bytes(ET.tostring(root))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / 'PCB_BUILD.md').write_text(
        f'Gate stage: schematic\nInput schematic: candidate.dchxml\n'
        f'Input schematic SHA-256: `{digest}`\nCurrent board: none\n'
        '| 1. Electrical checks | PARTIAL | candidate |\n', encoding='utf-8',
    )
    monkeypatch.setattr(sys, 'argv', ['pcb_quality_gate.py', str(tmp_path), '--json'])
    assert quality_gate_main() == 1
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'BLOCKED'
    assert report['schematic_review']['errors'] == {'schematic.readability.wire_crossing': 1}
    assert report['schematic_review']['readability']['checked_sheet_indices'] == [0, 1, 2]
    assert path.read_bytes() == ET.tostring(root)


def test_opt_in_five_sheet_local_reproduction_preserves_private_source(tmp_path: Path):
    configured = os.environ.get('DIPTRACE_READABILITY_FIXTURE')
    if configured is None:
        pytest.skip(
            'Set DIPTRACE_READABILITY_FIXTURE for the private local five-sheet reproduction'
        )
    source = Path(configured)
    raw = source.read_bytes()
    expected_sha = '23be2eabb12481313e1543b1fd3af4597b1320c862a30daa764d5bf9b399b23b'
    assert hashlib.sha256(raw).hexdigest() == expected_sha
    isolated = tmp_path / 'baseline.dchxml'
    shutil.copyfile(source, isolated)
    report = run_schematic_review(isolated)
    metrics = report['readability']
    assert metrics['checked_sheet_indices'] == [0, 1, 2, 3, 4]
    assert [s['different_net_crossings'] for s in metrics['sheets']] == [0, 0, 86, 22, 14]
    assert metrics['sheets'][0]['documentary_segments'] == 32
    assert metrics['sheets'][0]['documentary_crossings'] > 0
    assert report['errors']['schematic.readability.wire_crossing'] == 122
    assert isolated.read_bytes() == raw == source.read_bytes()
