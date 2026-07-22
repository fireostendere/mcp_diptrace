# DipTrace MCP

[English](README.md) | **Русский**

MCP-сервер для чтения, анализа и контролируемого изменения проектов DipTrace через официальный XML-формат. Репозиторий содержит два связанных компонента:

- `diptrace-mcp` — локальный Model Context Protocol сервер для Codex, Claude Desktop и других MCP-клиентов;
- `diptrace_mcp_bridge.exe` — плагин-мост для работы с проектом, который прямо сейчас открыт в PCB Layout или Schematic Capture.

## Что уже работает

- capability discovery (`get_capabilities`) с явным описанием доступных и недоступных возможностей;
- normalized document/model layer для PCB и schematic на основе DipTrace XML fixtures;
- project scaffolding: создание новых schematic/PCB XML-документов с нуля (листы, контур,
  слои, стекап, via styles, net classes, DRC) через `create_schematic_document` и `create_pcb_document`;
- schematic-authoring: листы, размещение part по ComponentStyle, соединение пинов в цепи,
  провода по официальной схеме `Wire/Points`, net labels — `add_sheet`, `place_part`,
  `connect_pins`, `disconnect_pins`, `add_wire`, `delete_wire`, `add_net_label`;
- schematic-to-PCB synchronization: перенос RefDes/value/fields, footprint, pin-to-pad
  connectivity, nets и ratlines через `sync_schematic_to_pcb`; по умолчанию режим additive,
  а guarded `exact` reconciliation удаляет подтверждённые расхождения; footprint definitions
  могут копироваться из проверенных Component/Pattern Library документов;
- официальная панелизация DipTrace (`Panel`, V-Scoring / Tab Routing): `set_panelization` и `clear_panelization`;
- query API по объектам, включая document models, connectivity graph и spatial selectors;
- сводка по схеме или плате: компоненты, части, выводы, цепи, слои и дифференциальные пары;
- поиск компонентов по `RefDes`, имени, значению и дополнительным полям;
- просмотр цепей с конечными точками `RefDes + pin/pad`;
- чтение настроек ERC, DRC, net classes, via styles и routing defaults;
- ограниченное чтение исходного XML по XPath;
- безопасные XML-правки с обязательным числом совпадений;
- raw-preserving byte-span compiler: unknown XML, BOM и форматирование вне targets
  не пересериализуются;
- режим предварительного просмотра `dry_run` с diff;
- защита от одновременного изменения через `SHA-256`;
- автоматическая резервная копия перед каждой записью;
- semantic transactions with preview/commit/rollback for all high-level writes;
- component/part move/rotate/side/lock/properties/pattern/align/distribute/group operations;
- documented net-class edits and standalone-pad testpoint add/move/remove;
- Component/Pattern Library normalized read, validation and pin-to-pad checks;
- registry-based offline DRC/ERC review v1 with persistent structured findings;
- deterministic silkscreen planning with locked-label preservation, previews and transactional apply;
- bounded local component placement with score breakdown, legalization and post-plan DRC comparison;
- explicit trace/via operations, bounded multi-layer 45-degree A* and symmetric vias;
- congestion-ordered multi-net routing with bounded rip-up/retry (`route_connections`) и
  read-only evidence через `analyze_routing_congestion`;
- atomic coupled differential-pair routing from one centerline with plan/preview/rollback;
- bounded DSN export, Freerouting jobs and guarded SES inspect/import;
- stackup, net length/skew, differential-pair geometry and preliminary single/differential
  microstrip impedance plus IPC-2141 symmetric stripline;
- ngspice batch adapter for user-supplied netlists with typed log results;
- опциональный typed openEMS-runner adapter для frequency-dependent centered/off-center
  stripline с bounded jobs и строгой проверкой результата;
- return-path/plane heuristics, advanced DFM/DFA/DFT/BOM review and design comparison;
- generic BOM/fabrication/assembly manifests with bounded resource artifacts;
- policy profiles `read_only`, `review`, `interactive_edit`, `automation`, `manufacturing`;
- live-сессия с явным завершением `apply` или `cancel`;
- offline-работа с экспортированным или нативным XML без запуска DipTrace;
- `stdio` и Streamable HTTP транспорты MCP.

`get_capabilities` — авторитетный источник возможностей для конкретной установки и
активного документа. Наличие зарегистрированного tool не означает, что операция
доступна без требуемой геометрии, правил, stackup или внешнего adapter.

## Статус проверки

Текущий MCP-код проходит полный core test suite, Ruff и strict Mypy. Отдельный live-тест
с DipTrace 5.3.0.2 подтвердил SHA-защиту, backup, atomic write, применение 41
`RefDesMarking`-правки на листе Power и независимый повторный export из DipTrace.
Все 41 координаты сохранились; нормализованные количества листов, частей, выводов,
цепей, шин и differential pairs не изменились; новых offline ERC errors не появилось.

Это подтверждает проверенный сценарий, но не является обещанием полной совместимости со
всеми версиями DipTrace и всеми XML objects.

## Как это устроено

```text
MCP-клиент                  diptrace-mcp
(Codex/Claude)  <-------->  анализ и безопасные XML-правки
                                  |
                                  | shared state directory
                                  v
DipTrace  <-------->  diptrace_mcp_bridge.exe
          temporary plugin_exchange.xml
```

DipTrace официально запускает плагин как отдельный `.exe`, передаёт ему путь к временному XML-файлу, а после завершения процесса импортирует XML обратно. Мост сохраняет рабочую копию в `%LOCALAPPDATA%\DipTraceMCP`, ждёт команды MCP-сервера и только после явного `apply` возвращает изменённый XML в DipTrace.

## Требования

- Windows 10/11 для live-интеграции с настольным DipTrace;
- DipTrace с поддержкой XML-плагинов;
- Python 3.10 или новее;
- MCP-клиент: Codex, Claude Desktop или совместимое приложение;
- PowerShell и доступ администратора только для установки плагина в `C:\Program Files\DipTrace`.

Offline-анализ XML работает также в Linux, macOS и WSL.

## Быстрый старт на Windows

### 1. Установить MCP-сервер

```powershell
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Для exact polygon/ellipse/obround geometry и GEOS spatial DRC установите optional extra:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[geometry]"
```

Проверка запуска:

```powershell
.\.venv\Scripts\diptrace-mcp.exe --help
```

### 2. Собрать и установить DipTrace-плагин

Сборка выполняется локально, поэтому вы сами получаете неподписанный `.exe` из исходного кода этого репозитория:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugin\build_bridge.ps1
```

Закройте все модули DipTrace. Затем откройте PowerShell **от имени администратора**:

```powershell
powershell -ExecutionPolicy Bypass -File .\plugin\install_plugin.ps1
```

Installer сначала ищет `C:\Program Files\DipTrace5`, затем legacy-каталог
`C:\Program Files\DipTrace`. Для другой установки передайте `-DipTraceDir`.

Для нестандартного каталога:

```powershell
.\plugin\install_plugin.ps1 -DipTraceDir "D:\Apps\DipTrace" -Mode Both
```

### 3. Подключить к Codex

```powershell
codex mcp add diptrace `
  --env "DIPTRACE_MCP_WORKSPACE=C:\Users\you\Documents\DipTrace" `
  -- "C:\path\to\mcp_diptrace\.venv\Scripts\diptrace-mcp.exe"

codex mcp list
```

Или добавьте содержимое `examples/codex-config.toml` в `~/.codex/config.toml`, заменив пути на свои.

### 4. Открыть live-сессию

1. Откройте и сохраните проект в DipTrace.
2. Выберите `Tools → Plugins → DipTrace MCP Bridge`.
3. Оставьте окно моста открытым. В это время DipTrace ожидает завершения плагина — это нормально.
4. В MCP-клиенте напишите, например:

   > Проверь активную плату: дай сводку, найди неподключённые цепи и покажи DRC. Ничего не изменяй.

5. Для изменения попросите сначала показать diff:

   > Измени значение R1 на 22k. Сначала сделай dry-run и объясни diff, затем примени правку.

6. После анализа завершите live-сессию через `finish_live_session(action="apply")` или `cancel`. Кнопки в окне моста делают то же самое вручную.

## Offline-режим

Передайте инструментам путь к XML-файлу внутри разрешённого workspace:

> Вызови `summarize_design` для `boards/controller.xml`, затем покажи все цепи питания.

Для старых бинарных `.dip`/`.dch` сначала используйте в DipTrace `File → Export → DipTrace XML`. В версиях с нативным XML `.dip` или `.dch` можно анализировать напрямую, если сам файл действительно начинается с `<Source Type="DipTrace-...">`.

## Безопасность изменений

`apply_xml_edits` по умолчанию ничего не записывает:

1. первый вызов использует `dry_run=true`;
2. сервер возвращает diff, `before_sha256` и `after_sha256`;
3. второй вызов повторяет те же операции с `dry_run=false` и `expected_sha256=<before_sha256>`;
4. перед записью создаётся `.bak`;
5. live-проект импортируется в DipTrace только после отдельного `finish_live_session(action="apply")`.

XML с `DOCTYPE` или `ENTITY` отклоняется. Сервер читает явный workspace и дополнительные каталоги из `DIPTRACE_MCP_ALLOWED_ROOTS`, а не произвольную файловую систему.

Профиль задаётся `DIPTRACE_MCP_POLICY`. Для review-only агента используйте
`review`: semantic previews разрешены, commit и external execution запрещены.

## Ограничения

- сервер не управляет GUI DipTrace и не нажимает пункты меню;
- DipTrace блокирует текущий документ, пока live-плагин ожидает `apply`/`cancel`;
- MCP не заменяет визуальную проверку, ERC/DRC и инженерное ревью;
- универсальные XML-операции позволяют менять структуру, но модель должна соблюдать официальную схему DipTrace;
- старые бинарные проекты требуют экспорта в XML;
- одновременно поддерживается одна live-сессия;
- local router не реализует push-and-shove, free-angle и dynamic neck-down; rip-up/retry
  и congestion-aware ordering доступны в bounded multi-net режиме `route_connections`;
- automatic via routing требует подтверждённый `Lay1`/`Lay2`; omitted span допустим
  только на двухслойной плате;
- coupled router требует согласованных pad-pair spacing/orientation и не строит uncoupled escapes;
- `calculate_impedance` остаётся preliminary analytical estimate; field-solver result
  доступен только через настроенный `run_openems_stripline_analysis` backend;
- `place_part` ссылается на библиотечный ComponentStyle по имени — графику символа и
  распиновку DipTrace подставляет из своих библиотек при импорте;
- ngspice-адаптер запускает пользовательские нетлисты в batch-режиме и не генерирует
  нетлисты из дизайна; openEMS adapter требует внешний совместимый JSON runner, solver
  не поставляется, а parser fixture явно синтетический;
- copper pours представлены boundary, не authoritative refill;
- fabrication manifest не содержит Gerber/NC Drill и не готов к производству;
- library mutation не заявлена без verified fixtures;
- schematic-to-PCB sync сохраняет лишние PCB objects и существующие traces; multi-part
  components требуют явный `part_id + pin -> pad_number` mapping, а новый placement является
  стартовой детерминированной сеткой и требует legalization;
- неподписанный bridge `.exe` может потребовать разрешения Windows Defender/SmartScreen.

## Документация

- [Полное руководство](docs/USAGE.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Domain model](docs/DOMAIN_MODEL.md)
- [XML compatibility matrix](docs/XML_COMPATIBILITY.md)
- [Geometry engine](docs/GEOMETRY_ENGINE.md)
- [Transactions](docs/TRANSACTIONS.md)
- [MCP tools](docs/MCP_TOOLS.md)
- [Review engine](docs/REVIEW_ENGINE.md)
- [Placement engine](docs/PLACEMENT_ENGINE.md)
- [Routing engine](docs/ROUTING_ENGINE.md)
- [Impedance and SI](docs/IMPEDANCE_AND_SI.md)
- [External adapters](docs/EXTERNAL_ADAPTERS.md)
- [Field-solver runner protocol](docs/FIELD_SOLVER_PROTOCOL.md)
- [Security and policy](docs/SECURITY_AND_POLICY.md)
- [Testing and benchmarks](docs/TESTING.md)
- [Skill contracts](docs/SKILL_CONTRACTS.md)
- [Англоязычный каталог PCB skills](skills/README.md)
- [Roadmap](docs/ROADMAP.md)
- [Разработка](docs/DEVELOPMENT.md)
- [Основной README на английском](README.md)
- [Официальные спецификации DipTrace XML и плагинов](https://diptrace.com/support/tutorials/)
- [Официальный Python SDK MCP](https://github.com/modelcontextprotocol/python-sdk)
- [Подключение MCP к Codex](https://learn.chatgpt.com/docs/extend/mcp)

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
