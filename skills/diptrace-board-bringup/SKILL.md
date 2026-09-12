---
name: diptrace-board-bringup
description: RAG-backed. Plan or guide first power-on, programming, measurements, functional acceptance, and repeatable production tests for a specific DipTrace board revision. Use for assembled boards, bring-up, fixture plans, or production test procedures; «первое включение», «проверка собранной платы». Use when the user says “Plan or run bring-up for this DipTrace board.”
---

Read [runtime access](../shared/runtime.md) before selecting tools or declaring a
capability unavailable. MCP tools and native/headless CLI are separate interfaces.

# DipTrace board bring-up and production test

RAG: **engineering memory by default** — [shared workflow](../shared/rag.md).
Use indexed measurement, circuit and bring-up material to derive the test sequence,
probe strategy, limits and fault-isolation plan for this exact board.

Use the exact schematic/PCB, fitted BOM, component rules, release evidence, and
firmware revision. Planning produces a procedure; a physical test passes only from
actual observed measurements. Do not energize or flash hardware from a planning request.

## Prepare the procedure

1. Resolve board revision and unit/serial identity, assembly/rework state, available
   instruments, supply, programming interface, and requested mode: plan or guided run.
   Check pinouts and testpoint nets from the actual design; do not reuse another
   board's connector order.
2. Read `rules/` and the project specification. For every measurement define the
   condition/load, probe points and reference, method, expected range/tolerance,
   source/calculation, and stop condition.
3. Derive supply voltage, initial current limit, rail/startup expectations, and thermal
   limits from this design and the instruments. Leave unknown values unresolved.
   Never choose a universal current limit or infer a short from a generic resistance
   threshold. Inspect low-resistance rails and charging capacitors in context.
4. Plan access to power/GND, reset/boot, debug, and representative interfaces. If PCB
   changes are requested, use [testpoint-planner](../testpoint-planner/SKILL.md)
   and an ECO; existing connector access may suffice. Do not load sensitive RF,
   crystal, high-impedance, or fast nets with an unspecified probe or long stub.

## First article sequence

1. Unpowered inspection: correct parts/variant, orientation/polarity, solder bridges,
   connector mating, exposed pads, missing/DNP parts, and known assembly defects.
2. With power removed, check ground and supply continuity/resistance and isolation
   required by the design. Account for capacitors and parallel semiconductor paths.
3. Power from the specified current-limited source using the approved connection
   sequence. Observe input current, rails, sequencing, reset, and heating. Stop and
   remove power on a defined limit violation, unexpected heating, or abnormal behavior;
   record the fault before retrying.
4. Use the exact target/programmer and verify device identity before flashing. Record
   firmware hash, boot configuration, programming/verification results, and logs.
   Mass erase, irreversible fuses, and security provisioning require their own scope.
   Use an installed flashing/serial tool only after discovering its actual capability.
5. Exercise one subsystem at a time, then combined loads and interfaces. Test RF last
   when present. Compare measurements with the planned bounds; a missing instrument
   leaves that test NOT_RUN, not PASS.
6. For failures, preserve logs and measurements, isolate the owning subsystem, and
   record any physical rework as an ECO through
   [diptrace-revision-review](../diptrace-revision-review/SKILL.md).

## Records and repeatable production test

Create/update `BRINGUP.md` with the procedure and append actual runs to
`TEST_RESULTS.csv`: unit, hardware revision, firmware hash, timestamp, test/conditions,
expected range, measured value/unit, result, instrument, and evidence path.
Keep planned values separate from measured values.

After first-article validation, write `PRODUCTION_TEST.md` with fixture pin map and
access, power/flash/test order, limits derived from specifications and observed
validation, calibration needs, cycle time, serialization, pass/fail handling, and rework
retest rules. Include environmental, EMC, reliability, or safety qualification only
when applicable to the specification; bench success does not certify those categories.
Fixture contact/access must be physically validated, not inferred from a CAD grid.

Return the procedure, actual results, failing or unrun tests, and the next concrete
measurement. If no hardware/instruments are available, finish the plan and report that
physical acceptance remains unverified.

Return [the shared result](../shared/result.schema.json); use `document: null` when
no CAD document is involved. Record concrete artifacts and unavailable checks; a
completed plan is not physical or manufacturing acceptance.
