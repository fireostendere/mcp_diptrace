# DipTrace MCP

[English](README.md) | **Русский**

[![CI](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml)
[![Coverage gate](docs/badges/coverage.svg)](.github/workflows/ci.yml)

DipTrace MCP — локальный Model Context Protocol сервер для чтения, анализа,
инженерного ревью и контролируемого изменения XML-проектов DipTrace. Проект
состоит из двух связанных компонентов:

- `diptrace-mcp` — MCP-сервер для Codex, Claude Desktop и других MCP-клиентов;
- `diptrace_mcp_bridge.exe` — Windows-плагин, который обменивается XML с
  проектом, открытым в PCB Layout или Schematic Capture.

## Текущее состояние

Исходный код и build metadata уже имеют версию **0.2.0**. Последний
опубликованный GitHub-релиз пока остаётся **v0.1.2**. Версия 0.2.0 —
проверенный unsigned release candidate уровня alpha/development-stage; тег и
публичный релиз не создаются, пока не закрыты оставшиеся проверки на реальной
Windows и в DipTrace.

Текущий код пригоден для инженерной работы с человеком в контуре: чтения PCB,
schematic и libraries; structured review; guarded semantic writes; schematic
authoring и synchronization; bounded placement/routing; live PCB/Schematic
exchange; Windows installer и portable candidate builds.

Проект не заменяет интерактивный EDA-движок DipTrace. Native mutation
Component/Pattern Library и native manufacturing output намеренно недоступны.
Для конкретной установки, документа, policy и внешних adapter фактическим
источником истины является `get_capabilities`.

## Статус публичного релиза

Проект использует OSI-approved open-source лицензию `LICENSE` Apache-2.0.
Правила участия и релиза находятся в `CONTRIBUTING.md`, `GOVERNANCE.md`,
`docs/LICENSE_DECISION.md`, `docs/PUBLIC_RELEASE_CHECKLIST.md`,
`docs/RELEASE_PROCESS.md`, `CHANGELOG.md` и `CITATION.cff`. Сообщения о
security отправляются через приватный канал; проверенный Code of Conduct канал
для enforcement пока не опубликован.

- Последний опубликованный development release — `v0.1.2`; его source distribution,
  wheel, Windows bridge executable, hashes и provenance неизменны.
- Текущая версия source/package — `0.2.0`; это reviewed candidate без tag и
  публикации.
- Windows installer, bridge, standalone executable, configurator и portable
  bundle 0.2.0 проходят CI, но ещё не являются публичными downloads.
- Python archives собираются по точному allowlist и проверяются по wheel entry
  points, packaged skills, bounds и каждому `RECORD` hash/size.
- Candidate Windows binaries unsigned; CI и SHA-256 не являются code signature,
  production-ready или universal-compatibility claim не заявляется.

Запись кандидата и оставшиеся gate находятся в
[`docs/releases/v0.2.0.md`](docs/releases/v0.2.0.md) и
[`docs/RELEASE_0_2_0_CHECKLIST.md`](docs/RELEASE_0_2_0_CHECKLIST.md).
Инструкции для уже опубликованного v0.1.2 находятся в
[`docs/INSTALL_FROM_RELEASE.md`](docs/INSTALL_FROM_RELEASE.md).

## Публичный MCP-контракт

Текущая публичная поверхность содержит:

- 159 зарегистрированных MCP tools;
- 157 публичных методов `DipTraceService`;
- 148 явных Facade → domain-service делегаций;
- один server-owned AnyIO worker-thread boundary для всех зарегистрированных
  tools.

Полный wire-level `tools/list` закреплён в
[`reference/mcp-tools-list.snapshot.json`](reference/mcp-tools-list.snapshot.json):
159 tools, 142 746 canonical UTF-8 bytes, SHA-256
`073f53681306fd13c5f3f29d61baed9a83fc9eb5c1ed14883846005a39d812db`.

Наличие tool в registry не означает доступность для любого документа и не
является доказательством реального DipTrace round-trip. Подробности находятся в
[`docs/MCP_TOOLS.md`](docs/MCP_TOOLS.md).

## Основные возможности

### Чтение и модели

- normalised models для PCB, schematic, Component Library и Pattern Library;
- стабильные object identifiers, selectors, spatial queries и connectivity;
- design rules, stackup, net classes, via styles, traces, pours, lengths и
  differential pairs;
- BOM extraction, consistency checks и bounded export records;
- byte-preserving XML-доступ для поддерживаемых кодировок с отказом на hostile
  DTD/entity input.

### Review и анализ

- bounded DRC/ERC, connectivity, BOM, assembly, DFM/DFA/DFT, thermal-metadata и
  design-comparison workflows;
- persistent findings и явные skipped/partial categories;
- NetClass-aware routing и trace-to-trace clearance resolution;
- предварительные расчёты Hammerstad-Jensen microstrip и IPC-2141 centred
  stripline;
- optional typed process boundaries для Freerouting, ngspice и openEMS.

Эти проверки помогают инженеру, но не являются fabrication, assembly или
regulatory sign-off.

### Контролируемые изменения

- move, rotate, side, lock, value, property, pattern, alignment, distribution и
  grouping для компонентов и schematic parts;
- board-text, NetClass, test-point, trace, via и panelisation edits;
- schematic sheets, parts, wires, labels, connectivity и no-connect state;
- additive и guarded exact schematic-to-PCB synchronization;
- synthetic PCB/schematic scaffolding и seed-based creation;
- transaction preview, validation, expected SHA-256, commit, backup, rollback и
  консервативные write-impact limits;
- live `apply`/`cancel` через bridge с повторной проверкой exchange path,
  working SHA и original-file SHA.

Где предусмотрено, значение по умолчанию — `dry_run=true`. Raw XML editing
остаётся expert escape hatch.

### Placement и routing

- deterministic silkscreen и bounded local placement plans;
- trace/via primitives и bounded multi-layer 45-degree A* routing;
- congestion-ordered multi-net routing с bounded batch-local rip-up/retry;
- atomic centreline-based differential-pair routing;
- DSN export, guarded Freerouting jobs и SES inspection/import.

Router не является push-and-shove, free-angle или global EDA autorouter.

## Архитектура

```text
MCP client (Codex / Claude / другой)
                 |
                 | stdio или loopback Streamable HTTP
                 v
       FastMCP server.py
                 |
                 v
  публичный Facade DipTraceService
                 |
                 +--> typed in-process domain services
                 +--> shared stores, cache, policy и document gateway
                 |
                 v
       XML files / shared state
                 ^
                 |
       diptrace_mcp_bridge.exe
                 ^
                 |
              DipTrace
```

`DipTraceService` остаётся стабильным публичным Facade и владельцем top-level
dependencies. Реализации доменов находятся в `src/diptrace_mcp/services/`;
они получают узкие typed dependencies, не держат весь Facade и не создают
дублирующие stores. См. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) и
[`docs/SERVICE_DECOMPOSITION.md`](docs/SERVICE_DECOMPOSITION.md).

## Модель безопасности

Основные write invariants:

1. caller paths остаются внутри configured allowed roots;
2. входной XML ограничивается по размеру, reparsed и проверяется до mutation;
3. preview и commit привязаны к точным SHA-256;
4. существующий target получает backup до replacement;
5. запись выполняется через temporary file и `os.replace`;
6. применяются policy и консервативные write-impact limits;
7. live apply повторно проверяет working SHA, exchange path и original exchange
   SHA;
8. explicit cancel не меняет exchange XML;
9. пользовательские sidecars не могут самостоятельно выдать высокий trust.

Capability report намеренно не заявляет полное trust-invalidation coverage для
`plan_apply`, `ses_import`, `schematic_to_pcb_sync` и `live_session_apply`.
Q1 Component Angle GUI/re-export evidence также остаётся `NOT_RUN`, поэтому
rotation results содержат structured warning.

## Обработка данных

- `DIPTRACE_MCP_WORKSPACE` задаёт обычный workspace; пути дополнительно
  ограничиваются `DIPTRACE_MCP_ALLOWED_ROOTS` и literal caller-path checks.
- `DIPTRACE_MCP_STATE_DIR` хранит локальные records, а live session —
  `original.xml` и `working.xml`; финализация выполняется через `apply` или
  `cancel`.
- Freerouting, ngspice и openEMS запускаются только через typed local process
  boundaries и isolated job directories; online sourcing по умолчанию отключён.
- MCP `stdio` использует локальные process pipes и не открывает network listener.
- `streamable-http` предназначен только для trusted loopback, например
  `127.0.0.1:8765`; OAuth и multi-user isolation не реализованы.
- User projects, private evidence, proprietary libraries и screenshots не
  загружаются и не коммитятся автоматически; внешние данные и публикацию
  контролирует оператор.

## Установка

### Текущий source tree

Требуется Python 3.10 или новее.

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

Windows PowerShell:

```powershell
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\diptrace-mcp.exe --help
```

Установите `.[geometry]`, когда нужны exact Shapely/GEOS geometry paths. Source
installation не устанавливает executable plug-in DipTrace автоматически;
advanced-путь описан в [`plugin/`](plugin/) и
[`docs/USAGE.md`](docs/USAGE.md).

### Опубликованные release assets

Для последнего immutable public release используйте
[`v0.1.2`](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.1.2).
Installer и portable bundle 0.2.0 пока являются только candidate build outputs.
Имена файлов из candidate-документации нельзя считать существующими downloads
до публикации `v0.2.0`.

## Проверка

CI matrix включает:

- Linux Python 3.10, 3.12 и 3.13;
- macOS и Windows Python 3.12;
- Shapely/GEOS и отдельный no-Shapely fallback;
- Ruff, strict Mypy, DCO, public tool snapshot, service-Facade contract,
  service-decomposition safety, event-loop responsiveness, release artifacts и
  provenance/compliance checks;
- native Windows bridge, standalone server, configurator, installer и portable
  bundle builds/smoke tests.

Exact head release-candidate PR #49 прошёл CI run `30940972328` и Windows
installer run `30940972331`. Ранее controlled live acceptance проверил отдельные
пути DipTrace 5.3 schematic и DipTrace 5.2.0.4 PCB/Schematic. Это не доказывает
универсальную совместимость со всеми версиями DipTrace 5.x.

## Оставшиеся release blockers для v0.2.0

- clean Windows 11 install, repair и uninstall acceptance;
- реальный текущий DipTrace 5 в PCB, Schematic, Component и Pattern modules;
- реальные Codex и Claude Desktop configuration/restart checks;
- elevated plug-in install с сохранением original user profile;
- custom-state preservation acceptance;
- final frozen artifacts, per-file checksums, public-download verification и
  необходимый внешний legal review.

## Документация

- [Использование](docs/USAGE.md)
- [MCP tools и resources](docs/MCP_TOOLS.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [Разработка](docs/DEVELOPMENT.md)
- [Тестирование](docs/TESTING.md)
- [Roadmap и фактическое состояние](docs/ROADMAP.md)
- [Покрытие review](docs/REVIEW_ENGINE.md)
- [Security и policy](docs/SECURITY_AND_POLICY.md)
- [Transactions](docs/TRANSACTIONS.md)
- [Windows installer](docs/WINDOWS_INSTALLER.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [Открытые вопросы совместимости](docs/OPEN_QUESTIONS.md)

## Участие и security

Contributions принимаются по DCO 1.1 и provenance/privacy rules из
[`CONTRIBUTING.md`](CONTRIBUTING.md). Merge authority остаётся у владельца
репозитория. Подозрения на уязвимость отправляйте только через приватный канал
из [`SECURITY.md`](SECURITY.md), а не в публичные issues.

Проект не заявляет Novarm/DipTrace endorsement, production deployments,
independent review, signed binaries, universal compatibility или complete
manufacturing sign-off.

## Лицензия

Apache License 2.0. См. [`LICENSE`](LICENSE).