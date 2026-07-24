# DipTrace MCP

[English](README.md) | **Русский**

DipTrace MCP — локальный Model Context Protocol сервер для чтения, анализа, инженерного ревью и контролируемого изменения проектов DipTrace через официальные XML-форматы. Репозиторий содержит два связанных компонента:

- `diptrace-mcp` — MCP-сервер для Codex, Claude Desktop и других MCP-клиентов;
- `diptrace_mcp_bridge.exe` — исполняемый плагин-мост для проекта, открытого в PCB Layout или Schematic Capture.

## Текущий уровень готовности

Проект уже пригоден для инженерного использования с человеком в контуре: чтения и ревью PCB/schematic, безопасных semantic edits, schematic authoring, синхронизации schematic → PCB, локального placement/routing, анализа differential pairs и подготовки review-артефактов.

Это пока не полная замена интерактивному EDA-движку DipTrace. Наиболее важный незакрытый слой — не количество MCP tools, а доказанная совместимость write-paths с реальным DipTrace 5.3 через контролируемые open/save/re-export fixtures. Создание/изменение native Component/Pattern Libraries и native manufacturing outputs пока намеренно не заявлены как готовые возможности.

Актуальный порядок работ и критерии завершения находятся в [roadmap](docs/ROADMAP.md). Фактическую доступность конкретной операции всегда определяет `get_capabilities`.

## Что уже работает

- runtime capability discovery через `get_capabilities`, включая точные причины недоступности;
- project scaffolding: новые schematic/PCB XML-документы с листами, контуром, слоями, stackup, via styles, net classes и DRC (`create_schematic_document`, `create_pcb_document`); **это synthetic MCP-generated XML, а не DipTrace-verified файлы**;
- seed-based создание проекта: копирование реального DipTrace-exported XML seed с сохранением provenance (`create_document_from_seed`);
- schematic authoring: листы, размещение part по библиотечному `ComponentStyle`, pin/net connectivity, провода по официальной структуре `Wire`/`Points` и net labels (`add_sheet`, `place_part`, `connect_pins`, `disconnect_pins`, `add_wire`, `delete_wire`, `add_net_label`);
- schematic-to-PCB synchronization RefDes/value/fields, footprint references, pin-to-pad connectivity, nets и ratlines; по умолчанию используется additive mode, а guarded `exact` reconciliation может удалять подтверждённые расхождения и затронутые traces только при изменении endpoint set;
- копирование проверенных pattern-library subtrees при schematic-to-PCB sync;
- официальные параметры панелизации DipTrace (`Panel`, V-Scoring / Tab Routing) через `set_panelization` и `clear_panelization`;
- нормализованные domain models для PCB, schematic, Component Library и Pattern Library;
- стабильные object references, structured selectors, connectivity graph и spatial queries;
- геометрия в миллиметрах, transforms, mirroring, arcs, optional exact GEOS geometry и SVG/JSON preview;
- raw-preserving XML patches: unknown XML, BOM, line endings и форматирование вне изменяемых узлов сохраняются;
- semantic transactions с plan, preview, validation, expected SHA-256, commit, backup и rollback;
- move/rotate/side/lock/property/pattern/alignment/distribution/group operations для компонентов и частей;
- board-text edits, документированные NetClass rules и standalone-pad test points;
- чтение и validation Component/Pattern Libraries, включая pin-to-pad checks;
- machine-readable serializer reference с XML enums, defaults, aliases и import semantics, извлечёнными из документации; reference ограничивает parser/writer поведение, но сам по себе не создаёт DipTrace round-trip trust;
- registry-based offline DRC/ERC review с persistent structured findings;
- deterministic silkscreen planner и bounded local placement planner;
- explicit trace/via operations, bounded multi-layer 45-degree A* и symmetric via insertion;
- congestion-ordered multi-net routing с bounded rip-up/retry (`route_connections`) и read-only priority evidence (`analyze_routing_congestion`);
- atomic coupled differential-pair routing от centerline;
- bounded DSN export, Freerouting jobs и guarded SES inspect/import;
- stackup, net length/skew, differential-pair geometry, return-path heuristics и preliminary analytical impedance: Hammerstad-Jensen microstrip (single/differential) и IPC-2141 centered symmetric stripline;
- ngspice batch adapter для пользовательских netlists с typed log results;
- optional typed openEMS-runner adapter для frequency-dependent centered/off-center stripline с bounded jobs и строгим parsing результата;
- BOM, DFM/DFA/DFT, thermal-metadata, assembly и design-comparison reviews;
- generic BOM, fabrication-review и assembly-review manifests;
- policy profiles `read_only`, `review`, `interactive_edit`, `automation`, `manufacturing`;
- live- и offline-работа через MCP stdio или Streamable HTTP.

`get_capabilities` — авторитетный источник для конкретной установки и документа. Зарегистрированный MCP tool может быть недоступен, если активный source type не содержит требуемую геометрию, rules, stackup или внешний adapter.

## Статус проверки

CI разделяет проверки по платформам и назначению:

- полный pytest на Linux с Python 3.10, 3.12 и 3.13;
- Ruff, strict Mypy и generated-skill checks на Linux/Python 3.12;
- полный pytest и CLI smoke tests на macOS и Windows/Python 3.12;
- нативная Windows-сборка с проверкой непустого `diptrace_mcp_bridge.exe`.

Текущая ветка `main` проходит эту матрицу. Regression coverage включает fail-closed trust authority boundary, обязательные категории semantic comparison для PCB и schematic, Windows atomic-job поведение и terminal cancellation semantics для Freerouting, ngspice и openEMS.

Synthetic 4.3 fixtures покрывают PCB, schematic, Component Library, Pattern Library, geometry, transactions, review, routing, DSN/SES и MCP contracts. Отдельный live acceptance test с DipTrace 5.3.0.2 подтвердил:

- защиту от source-SHA conflict, равенство backup и atomic write;
- 41 scoped `RefDesMarking`-правку на листе Power;
- bridge apply и независимый повторный export из DipTrace;
- сохранение всех 41 координат и неизменность нормализованных количеств sheet/part/pin/net/bus/differential-pair;
- отсутствие новых offline ERC errors после round trip.

Это сильное доказательство для проверенных путей, но не обещание полной совместимости со всеми версиями DipTrace и всеми XML objects. Serializer reference дополнительно ограничивает parser behavior, но не заменяет реальные DipTrace open/save/re-export fixtures.

## Архитектура

```text
MCP-клиент                    diptrace-mcp
(Codex/Claude)  <-------->    анализ и guarded XML edits
                                      |
                                      | shared state directory
                                      v
DipTrace       <-------->    diptrace_mcp_bridge.exe
               temporary plugin_exchange.xml
```

DipTrace запускает плагин отдельным `.exe` и передаёт путь к временному XML. Bridge хранит рабочую копию в `%LOCALAPPDATA%\DipTraceMCP`, ждёт MCP `apply` или `cancel`, проверяет expected SHA-256 и завершает процесс только после финализации сессии. После `apply` DipTrace импортирует exchange XML обратно.

## Требования

- Python 3.10 или новее;
- Windows 10/11 для live-интеграции с настольным DipTrace;
- DipTrace build с поддержкой executable XML plug-ins;
- MCP-клиент, например Codex или Claude Desktop;
- PowerShell и права администратора только для установки плагина в `C:\Program Files\DipTrace`/`DipTrace5`.

Offline XML analysis также работает в Linux, macOS и WSL.

## Быстрый старт на Windows

### 1. Установить MCP-сервер

```powershell
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Для exact polygon/ellipse/obround/swept-trace geometry и spatial DRC установите optional GEOS backend:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[geometry]"
```

Проверка entry point:

```powershell
.\.venv\Scripts\diptrace-mcp.exe --help
```

### 2. Собрать и установить DipTrace-плагин

Соберите неподписанный executable локально из исходного кода:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugin\build_bridge.ps1
```

Закройте все модули DipTrace, откройте PowerShell от имени администратора и установите bridge в PCB Layout, Schematic Capture, Component Editor и Pattern Editor:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugin\install_plugin.ps1
```

Installer сначала проверяет `C:\Program Files\DipTrace5`, затем legacy `C:\Program Files\DipTrace`. Для другой установки:

```powershell
.\plugin\install_plugin.ps1 -DipTraceDir "D:\Apps\DipTrace" -Mode All
```

`-Mode Both` устанавливает только PCB/Schematic. `-Mode Libraries` — только Component/Pattern Editor bridges. Library sessions экспортируют активную библиотеку целиком, но используют `ImpMode=None`; завершайте их через `cancel`, потому что native library mutation пока evidence-gated.

### 3. Подключить Codex

```powershell
codex mcp add diptrace `
  --env "DIPTRACE_MCP_WORKSPACE=C:\Users\you\Documents\DipTrace" `
  -- "C:\path\to\mcp_diptrace\.venv\Scripts\diptrace-mcp.exe"

codex mcp list
```

Либо перенесите настройки из [`examples/codex-config.toml`](examples/codex-config.toml) в `~/.codex/config.toml` и замените пути.

### 4. Открыть live-сессию

1. Откройте и сохраните design или library в DipTrace.
2. Выберите `Tools > Plugins > DipTrace MCP Bridge`.
3. Оставьте окно bridge открытым, пока MCP-клиент выполняет чтение, planning и edits.
4. Сначала попросите клиента прочитать и проверить документ.
5. Для write-operation сначала требуйте dry-run/transaction preview и проверьте changed object IDs.
6. Commit выполняйте с SHA из preview, затем запустите post-write checks и вызовите `finish_live_session(action="apply")` либо отмените сессию.

Кнопки bridge выполняют те же явные apply/cancel действия. Component и Pattern Editor profiles остаются read-only и после inspection должны завершаться через `cancel`.

## Offline-режим

Передайте путь внутри `DIPTRACE_MCP_WORKSPACE` или `DIPTRACE_MCP_ALLOWED_ROOTS`:

> Запусти `summarize_design` для `boards/controller.xml`, затем покажи цепи питания.

Legacy binary `.dip`/`.dch` сначала экспортируйте через `File > Export > DipTrace XML`. Native XML `.dip`/`.dch` можно читать напрямую только если файл действительно начинается с официального DipTrace XML root.

## Безопасность изменений

High-level writes по умолчанию работают в preview/dry-run режиме. Рекомендуемый workflow:

1. загрузить документ и зафиксировать SHA-256;
2. создать или staged scoped semantic operations;
3. проверить diff и SVG/JSON preview;
4. проверить connectivity и локальный DRC/ERC;
5. commit с `expected_sha256`;
6. повторно распарсить изменённый XML и выполнить post-write checks;
7. явно применить live session либо выполнить rollback/cancel.

`apply_xml_edits` остаётся expert escape hatch. Он требует exact match counts, сохраняет bytes вне target nodes, reparses результат, создаёт backup перед commit и отклоняет SHA conflicts.

XML с `DOCTYPE` или `ENTITY` отклоняется. Доступ к файловой системе ограничен configured roots. Внешние процессы запускаются только через typed allowlisted adapters.

## Модель доверия

Сервер разделяет provenance и authority. Клиент может передать evidence, но не может сам повысить документ до high-trust validation level.

- **Synthetic MCP-generated**: XML из `create_schematic_document`/`create_pcb_document` имеет `synthetic_parser_only`, пока нет более сильного независимо проверенного evidence.
- **Seed-based**: `create_document_from_seed` копирует реальный DipTrace export и сохраняет provenance, но копирование само по себе не создаёт round-trip authority.
- **Recorded evidence**: `record_roundtrip_evidence` связывает before/after files, точные paths, source type, SHA-256 и semantic comparison. User-supplied evidence полезен для audit/regression, но не является trusted root.
- **Serializer reference**: bundled rule set фиксирует и нормализует правила из XML documentation. Он ограничивает parser/writer implementation и tests, но не влияет на trust level.
- **High trust**: повышение до `diptrace_roundtrip_verified`/`external_tool_roundtrip_verified` недоступно до появления authenticated server-owned registry, signature verifier или committed allowlist.

Trust invalidation после MCP write реализован для основных проверенных путей, но capability layer намеренно **не заявляет полное покрытие всех write paths**. Отдельно остаются неполностью закрытыми `plan_apply`, `ses_import`, `schematic_to_pcb_sync` и `live_session_apply`; их полное fail-closed trust invalidation входит в ближайший roadmap. Поэтому `get_capabilities` имеет приоритет над более общими описаниями документации.

Evidence manifests повторно валидируются при использовании и rollback; path aliases, source-type mismatch, stale hashes, неполные comparison categories и semantic differences приводят к fail-closed результату.

## Статус pattern recommendation

Текущий baseline умеет читать и валидировать существующие Pattern Libraries, сравнивать pad mapping и назначать компоненту уже существующий pattern при точном совпадении pad numbers. Pattern Editor bridge sessions намеренно read-only.

Persistent feedback/recommendation tools — `record_pattern_example`, `accept_pattern_suggestion`, `reject_pattern_suggestion` — пока не реализованы. До их разработки roadmap ставит выше закрытие реального DipTrace 5.3 evidence layer: fixture pack, trust-invalidation coverage и mask/paste/courtyard semantics.

После evidence closure планируется append-only provenance-bound feedback dataset, deterministic retrieval похожих принятых примеров и измеримый ranked recommendation workflow. Fine-tuning остаётся более поздней необязательной стадией.

Создание или изменение native Pattern/Component Libraries остаётся заблокировано до controlled DipTrace 5.3 before/after и open/save/re-export fixtures, подтверждающих writer semantics.

## Известные ограничения

- сервер не автоматизирует GUI DipTrace;
- DipTrace синхронно ждёт завершения live plug-in session;
- одновременно поддерживается одна live-сессия;
- LLM не заменяет visual review, ERC/DRC и инженерное решение;
- local router не реализует push-and-shove, free-angle routing или dynamic neck-down; congestion-aware ordering и bounded rip-up/retry доступны через `route_connections`;
- automatic via routing на multilayer board требует подтверждённый `Lay1`/`Lay2` span;
- coupled router требует совместимых endpoint spacing/orientation и не синтезирует произвольные uncoupled escapes;
- `calculate_impedance` остаётся preliminary analytical estimate; field-solver result доступен только через настроенный `run_openems_stripline_analysis` backend;
- `place_part` ссылается на library `ComponentStyle` по имени; symbol graphics и pin mapping DipTrace разрешает из собственных libraries при import;
- ngspice adapter запускает user-supplied netlists и не генерирует netlist из design;
- openEMS adapter требует совместимый внешний JSON runner; solver не bundled, а committed parser fixture синтетический;
- copper-pour boundaries не считаются authoritative refill geometry;
- generic fabrication manifests не содержат Gerber или NC Drill;
- persistent pattern-training/recommendation tools пока отсутствуют;
- native Component/Pattern Library mutation недоступна до verified DipTrace 5.3 round-trip fixtures;
- schematic wire authoring и ratline generation требуют дополнительного real DipTrace 5.3 round-trip evidence;
- real-openEMS golden validation остаётся внешней acceptance-задачей.

## Документация

- [Roadmap и фактический статус](docs/ROADMAP.md)
- [Serializer reference](docs/SERIALIZER_REFERENCE.md)
- [XML compatibility](docs/XML_COMPATIBILITY.md)
- [Полное руководство](docs/USAGE.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Domain model](docs/DOMAIN_MODEL.md)
- [Geometry engine](docs/GEOMETRY_ENGINE.md)
- [Transactions](docs/TRANSACTIONS.md)
- [MCP tools](docs/MCP_TOOLS.md)
- [Review engine](docs/REVIEW_ENGINE.md)
- [Placement engine](docs/PLACEMENT_ENGINE.md)
- [Routing engine](docs/ROUTING_ENGINE.md)
- [Impedance and SI](docs/IMPEDANCE_AND_SI.md)
- [External adapters](docs/EXTERNAL_ADAPTERS.md)
- [Security and policy](docs/SECURITY_AND_POLICY.md)
- [Testing and benchmarks](docs/TESTING.md)
- [Skill contracts](docs/SKILL_CONTRACTS.md)
- [PCB skills](skills/README.md)
- [Разработка](docs/DEVELOPMENT.md)
- [English README](README.md)

## Разработка

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/generate_pcb_skills.py --check
python -m pytest -q
python -m ruff check --no-cache src tests benchmarks scripts
python -m mypy --no-incremental src/diptrace_mcp
```
