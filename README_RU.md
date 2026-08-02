# DipTrace MCP

[English](README.md) | **Русский**

DipTrace MCP — локальный Model Context Protocol сервер для чтения, анализа, инженерного ревью и контролируемого изменения проектов DipTrace через официальные XML-форматы. Репозиторий содержит два связанных компонента:

- `diptrace-mcp` — MCP-сервер для Codex, Claude Desktop и других MCP-клиентов;
- `diptrace_mcp_bridge.exe` — исполняемый плагин-мост для проекта, открытого в PCB Layout или Schematic Capture.

## Текущий уровень готовности

Проект уже пригоден для инженерного использования с человеком в контуре: чтения и ревью PCB/schematic, безопасных semantic edits, schematic authoring, синхронизации schematic → PCB, локального placement/routing, анализа differential pairs и подготовки review-артефактов.

Это пока не полная замена интерактивному EDA-движку DipTrace. Для проверенных PCB/schematic live-путей уже есть контролируемые Windows/WSL apply, cancel, wrong-SHA, GUI, save и re-export доказательства. Главный незакрытый слой теперь — более широкие redistributable evidence для остальных writers, вариантов исходных файлов, native libraries и optional external-tool путей. Создание/изменение native Component/Pattern Libraries и native manufacturing outputs по-прежнему намеренно не заявлены как готовые возможности.

Актуальный порядок работ и критерии завершения находятся в [roadmap](docs/ROADMAP.md). Фактическую доступность конкретной операции всегда определяет `get_capabilities`.

## Статус публичного релиза

Проект лицензирован под Apache License 2.0 — OSI-approved open-source
лицензией; полный текст закоммичен как [`LICENSE`](LICENSE). Обоснование
выбора записано в
[docs/LICENSE_DECISION.md](docs/LICENSE_DECISION.md).

В репозитории опубликованы правила участия и релиза:

- [процесс contribution](CONTRIBUTING.md);
- [текущий governance](GOVERNANCE.md);
- [license decision matrix и запись о выборе](docs/LICENSE_DECISION.md);
- [чек-лист публичного релиза](docs/PUBLIC_RELEASE_CHECKLIST.md) и
  [release process](docs/RELEASE_PROCESS.md), включая
  [установку из опубликованных release assets](docs/INSTALL_FROM_RELEASE.md);
- [changelog](CHANGELOG.md) и [citation metadata](CITATION.cff).

Issues и pull requests принимаются по правилам DCO 1.1 и provenance из
[CONTRIBUTING.md](CONTRIBUTING.md); право merge остаётся у владельца
репозитория. Подозрения на уязвимости отправляйте только через приватный
security-канал, опубликованный в [SECURITY.md](SECURITY.md), а не в публичных
issues. Проверенного канала для Code of Conduct пока нет, поэтому политика
Code of Conduct не публикуется. Signing, dependency, bundled-content и
independent-review остаются явными blockers для более сильных release claims.
Ветка `main` защищена pull request, DCO и обязательными CI-проверками; текущая
проверка правил опубликована в
[docs/compliance/BRANCH_PROTECTION_STATUS.md](docs/compliance/BRANCH_PROTECTION_STATUS.md).
Репозиторий не заявляет существующее сообщество, adoption, sponsorship, vendor
endorsement или участие в support program. Внешние grant/application
материалы владелец репозитория хранит приватно.

Текущий development-stage релиз — версия 0.1.2. Его tag, unsigned-артефакты,
`SHA256SUMS.txt` и provenance-запись в
[docs/releases/v0.1.2.md](docs/releases/v0.1.2.md) указывают на один и тот же
commit. Предыдущий релиз `v0.1.1` сохранён для аудита, но явно
[withdrawn](docs/releases/v0.1.1.md) из-за рассинхронизации документации и
несогласованности release-документов; его старые assets не являются актуальными.
CI собирает Python source distribution и wheel по точному versioned
allowlist и проверяет их содержимое, ограничения, entry points, packaged
skills и wheel `RECORD`. Wheel содержит MCP-сервер и packaged skills; для
полной live-интеграции на Windows также нужны отдельно поставляемые bridge
settings, installer и executable. Путь установки без clone описан в
[INSTALL_FROM_RELEASE.md](docs/INSTALL_FROM_RELEASE.md).

## Что уже работает

- runtime capability discovery через `get_capabilities`, включая точные причины недоступности;
- project scaffolding: новые schematic/PCB XML-документы с листами, контуром, слоями, stackup, via styles, net classes и DRC (`create_schematic_document`, `create_pcb_document`); вызывающий код может задать литерал XML `format_version`, но это не преобразует структуру scaffold и не подтверждает совместимость; **это synthetic MCP-generated XML, а не DipTrace-verified файлы**;
- seed-based создание проекта: копирование реального DipTrace-exported XML seed с сохранением provenance (`create_document_from_seed`);
- schematic authoring: листы, размещение part по библиотечному `ComponentStyle`, pin/net connectivity, провода по официальной структуре `Wire`/`Points` и net labels (`add_sheet`, `place_part`, `connect_pins`, `disconnect_pins`, `add_wire`, `delete_wire`, `add_net_label`);
- schematic-to-PCB synchronization RefDes/value/fields, footprint references, pin-to-pad connectivity, nets и ratlines; по умолчанию используется additive mode, а guarded `exact` reconciliation может удалять подтверждённые расхождения и затронутые traces только при изменении endpoint set;
- копирование проверенных pattern-library subtrees при schematic-to-PCB sync;
- официальные параметры панелизации DipTrace (`Panel`, V-Scoring / Tab Routing) через `set_panelization` и `clear_panelization`;
- нормализованные domain models для PCB, schematic, Component Library и Pattern Library;
- стабильные object references, structured selectors, connectivity graph и spatial queries;
- геометрия в миллиметрах, transforms, mirroring, arcs, optional exact GEOS geometry и SVG/JSON preview;
- raw-preserving XML patches для поддерживаемых UTF-8/UTF-16LE/BE/ASCII/Latin-1
  sources: unknown XML, исходный BOM, line endings и форматирование вне изменяемых
  узлов сохраняются; неподдерживаемые кодировки приводят к fail-closed результату;
- semantic transactions с plan, preview, validation, expected SHA-256, commit, backup и rollback;
- move/rotate/side/lock/property/pattern/alignment/distribution/group operations для компонентов и частей;
- board-text edits, документированные NetClass rules и standalone-pad test points;
- чтение и validation Component/Pattern Libraries, включая pin-to-pad checks;
- ограниченные registry-based offline DRC/ERC review с persistent findings,
  structured skips и явной [матрицей implemented/partial/missing](docs/REVIEW_ENGINE.md);
- deterministic silkscreen planner и bounded local placement planner;
- explicit trace/via operations, bounded multi-layer 45-degree A* и symmetric via insertion;
- congestion-ordered multi-net routing с bounded rip-up/retry (`route_connections`) и read-only priority evidence (`analyze_routing_congestion`);
- atomic coupled differential-pair routing от centerline;
- bounded DSN export, Freerouting jobs и guarded SES inspect/import;
- stackup, net length/skew, differential-pair geometry, return-path heuristics и preliminary analytical impedance: Hammerstad-Jensen microstrip (single/differential) и IPC-2141 centered symmetric stripline;
- ngspice batch adapter для пользовательских netlists с typed log results;
- optional typed openEMS-runner adapter для frequency-dependent centered/off-center stripline с bounded jobs и строгим parsing результата;
- ограниченные профили BOM, DFM/DFA/DFT, thermal-metadata, assembly и
  design-comparison review; их ограничения по геометрии и evidence описаны явно, и они
  не являются fabrication- или assembly-sign-off;
- generic BOM, fabrication-review и assembly-review manifests;
- policy profiles `read_only`, `review`, `interactive_edit`, `automation`, `manufacturing`;
- live- и offline-работа через MCP stdio или Streamable HTTP.

`get_capabilities` — авторитетный источник для конкретной установки и документа. Зарегистрированный MCP tool может быть недоступен, если активный source type не содержит требуемую геометрию, rules, stackup или внешний adapter.

## Статус проверки

CI разделяет проверки по платформам и назначению:

- полный pytest на Linux с Python 3.10, 3.12 и 3.13;
- Ruff, strict Mypy и generated-skill checks на Linux/Python 3.12;
- полный pytest и CLI smoke tests на macOS и Windows/Python 3.12;
- нативная Windows-сборка с проверкой и smoke-запуском `diptrace_mcp_bridge.exe`.

Текущая ветка `main` проходит эту матрицу. Regression coverage включает fail-closed trust authority boundary, обязательные категории semantic comparison для PCB и schematic, Windows atomic-job поведение и terminal cancellation semantics для Freerouting, ngspice и openEMS.

Synthetic 4.3 fixtures покрывают PCB, schematic, Component Library, Pattern Library, geometry, transactions, review, routing, DSN/SES и MCP contracts. Отдельно проведены две контролируемые live acceptance-кампании:

- DipTrace 5.3.0.2, schematic: source-SHA conflict protection, backup equality, atomic write, 41 scoped `RefDesMarking`-правка, bridge apply, независимый re-export, стабильные normalized counts и отсутствие новых offline ERC errors;
- DipTrace 5.2.0.4 на Windows с MCP-сервером в WSL: PCB apply/cancel/wrong-SHA и Schematic apply/cancel/wrong-SHA, Windows-native exchange-path metadata, отсутствие фантомного `C:\mnt\c\...`, GUI-подтверждение для применяемых изменений, Save As/re-export, semantic comparison и неизменная connectivity/counts.

Кампания 2026-07-31 завершилась как `ACCEPTANCE: PASS`, `RELEASE BLOCKER: NO` для этой матрицы. Это сильное доказательство для проверенных путей, но не обещание полной совместимости со всеми версиями DipTrace, всеми XML objects, всеми MCP tools и optional adapters. См. [отчёт acceptance](docs/LIVE_ACCEPTANCE_2026-07-31.md) и [code review](docs/CODE_REVIEW_2026-07-31.md).

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

DipTrace запускает плагин отдельным `.exe` и передаёт путь к временному XML. Bridge хранит рабочую копию в `%LOCALAPPDATA%\DipTraceMCP`, ждёт MCP `apply` или `cancel`, проверяет SHA-256 рабочей копии, который видел caller, заново убеждается, что исходный exchange-файл не изменился и всё ещё находится внутри allowed root, и завершает процесс только после финализации сессии. После `apply` DipTrace импортирует exchange XML обратно. В metadata путь хранится в native-синтаксисе процесса bridge; WSL-сервер вычисляет `/mnt/<drive>/...` только в памяти и никогда не записывает этот derived path обратно.

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

Для exact polygon/ellipse/obround/swept-trace geometry и поддерживаемых exact
spatial-clearance путей установите optional GEOS backend:

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
6. Commit выполняйте с SHA из preview, затем запустите post-write checks, прочитайте последний SHA рабочего документа и вызовите `finish_live_session(action="apply", expected_sha256="...")`; для отмены hash не нужен.

Кнопки bridge выполняют те же явные apply/cancel действия. Окно показывает привязанный
к SHA и ограниченный impact summary: normalized/structural counts и не более первых 20
изменённых stable IDs; unavailable и truncated состояния явно раскрываются. Live apply
проверяет тот же консервативный лимит 500 объектов дважды: при публикации MCP request и
непосредственно в bridge перед заменой. Component и Pattern Editor profiles являются
read-only (`ImpMode=None`); неизвестные profiles также закрыты fail-closed.

`finish_live_session` ограниченно ждёт только локальный результат bridge: `applied`,
`cancelled` или `not_acknowledged`. `applied` означает, что bridge заменил и проверил
локальный exchange XML; это не подтверждение от DipTrace host. Заведомо мёртвый bridge
в той же platform/PID namespace автоматически получает статус `abandoned`. PID namespaces
Windows и WSL никогда не отождествляются по догадке; orphan с неизвестной liveness
завершается по настраиваемому двухчасовому TTL либо явно через
`abandon_live_session(reason="...")`, который никогда не применяет working XML.
Lifecycle-изменения Windows/WSL используют общий атомарный lease-каталог с nonce:
нативные `flock` и Windows byte locks на NTFS не взаимодействуют. Обычные операции
никогда не завершают и не снимают неизвестного владельца lease; явный abandon
возвращает типизированный timeout вместо риска split-brain writer.

## Offline-режим

Передайте путь внутри `DIPTRACE_MCP_WORKSPACE` или `DIPTRACE_MCP_ALLOWED_ROOTS`:

> Запусти `summarize_design` для `boards/controller.xml`, затем покажи цепи питания.

Legacy binary `.dip`/`.dch` сначала экспортируйте через `File > Export > DipTrace XML`. Native XML `.dip`/`.dch` можно читать напрямую только если файл действительно начинается с официального DipTrace XML root.

## Обработка данных

- Переданные через MCP пути design/source должны разрешаться внутри
  `DIPTRACE_MCP_WORKSPACE` или `DIPTRACE_MCP_ALLOWED_ROOTS`. State directory и пути к
  executable являются отдельными operator-owned settings.
- `DIPTRACE_MCP_STATE_DIR` может содержать полный design XML в session working copies
  и transaction snapshots, а также operations, previews, plans, review reports,
  external-job logs/results, exports и backups. Считайте этот каталог чувствительными
  данными проекта и задавайте ему соответствующие права доступа.
- В live session DipTrace передаёт временный exchange path. Bridge копирует input в
  `original.xml` и `working.xml` внутри state directory; только явный `apply` с
  expected SHA-256 рабочего файла копирует результат обратно в exchange path.
  `cancel` оставляет исходный exchange input без изменений.
- Offline backups хранятся в настроенном центральном state tree с ключом из hash
  канонического target path, а не в неявном backup-каталоге рядом с design. Если
  требуется такое разделение, размещайте `DIPTRACE_MCP_STATE_DIR` вне project.
  Count/age retention удаляет только validated terminal records и истёкшие backup
  histories на best-effort основе; active, nonterminal, corrupt или unverifiable state
  может остаться, а thresholds не являются storage quotas.
- Freerouting, ngspice и openEMS runner — необязательные локальные subprocesses,
  запускаемые только соответствующими tools. Их isolated job directories и bounded
  logs/results сохраняются в state directory. Process containment не создаёт network
  sandbox для этих сторонних программ.
- Transport `stdio` по умолчанию обменивается запросами и результатами с настроенным
  локальным MCP-клиентом. Необязательный `streamable-http` слушает заданные host/port;
  по умолчанию это loopback (`127.0.0.1:8765`), встроенной remote authentication нет.
  Оставляйте его на loopback, если не настроен authenticated reverse proxy.

Подробные границы описаны в [Usage: Backups and State Directory](docs/USAGE.md#11-backups-and-state-directory),
[Security and Policy](docs/SECURITY_AND_POLICY.md) и
[External Adapters](docs/EXTERNAL_ADAPTERS.md).

## Безопасность изменений

High-level writes по умолчанию работают в preview/dry-run режиме. Рекомендуемый workflow:

1. загрузить документ и зафиксировать SHA-256;
2. создать или staged scoped semantic operations;
3. проверить diff и SVG/JSON preview;
4. повторно запустить применимые ограниченные connectivity/DRC/ERC checks и проверить
   каждый skip;
5. commit с `expected_sha256`;
6. повторно распарсить изменённый XML и выполнить post-write checks;
7. явно применить live session либо выполнить rollback/cancel.

`apply_xml_edits` остаётся expert escape hatch. Он требует exact match counts, сохраняет bytes вне target nodes, reparses результат, создаёт backup перед commit и отклоняет SHA conflicts.

Creation tools могут создать отсутствующий target без hash. Замена существующего target
требует одновременно `overwrite=true` и его текущий, наблюдавшийся вызывающей стороной
`expected_sha256`; `expected_seed_sha256` привязывает seed input и не заменяет target hash.

XML с `DOCTYPE` или `ENTITY` отклоняется. Переданные клиентом пути design/source
ограничены configured roots; server state и executable paths являются отдельными
operator-owned settings. Внешние процессы запускаются только через typed allowlisted
adapters.

### WO-11 safety checkpoint — 2026-07-25

- Пути из MCP calls интерпретируются буквально: переменные окружения и `~` не
  подставляются. Expansion применяется только к operator-owned конфигурации сервера;
  переданные клиентом пути design/source остаются под allowed-root check.
- Поддерживаемые XML writes сохраняют обнаруженные source codec/BOM и untouched
  bytes. Raw edits и raw-preserving semantic edits повторно парсятся и должны
  совпадать с запрошенным semantic element tree; чистый UTF-32 input сейчас
  отклоняется fail closed.
- Typed request data, нормализованные XML numbers и числовые SES tokens отклоняют
  `NaN` и бесконечности. DSN output отклоняет quoted values, которым нужны
  непроверенные escaping или non-ASCII encoding, а SES input отклоняет backslash
  escapes и literal controls в quoted tokens. Реальные конвенции DipTrace остаются
  открытыми evidence questions.
- У external adapters есть bounded streaming logs/results и общий concurrency limit.
  POSIX process groups и Windows kill-on-close Job Objects ограничивают дочерние
  процессы, а завершение root processes явно ожидается.
- Offline backups находятся в центральном state directory и изолированы по hash
  канонического target path. Existing target сохраняется в backup до замены; у нового
  target ещё нет исходных bytes для backup. Retention удаляет validated terminal
  records и истёкшие per-target backup histories, защищает active/nonterminal state и
  считает count/age thresholds целями cleanup, а не жёсткими квотами.

## Модель доверия

Сервер разделяет provenance и authority. Клиент может передать evidence, но не может сам повысить документ до high-trust validation level.

- **Synthetic MCP-generated**: XML из `create_schematic_document`/`create_pcb_document` имеет `synthetic_parser_only`, пока нет более сильного независимо проверенного evidence.
- **Seed-based**: `create_document_from_seed` копирует реальный DipTrace export и сохраняет provenance, но копирование само по себе не создаёт round-trip authority.
- **Публичный приём user-supplied evidence**: `validate_roundtrip_evidence` без записи проверяет разные allowed-root роли source/saved/re-export, точные SHA-256, source type, привязку к документу и, если передан re-export, structural semantic comparison. `record_roundtrip_evidence` после повторной проверки этих gates явно записывает только manifest и provenance sidecar. Оба инструмента сообщают `authority=user_supplied`, сохраняют `requires_diptrace_verification=true` и никогда не дают high trust.
- **High trust**: package-owned exact-hash registry реализован и раскрывается
  через capabilities/resources, но сейчас в нём 0 reviewed entries. Ни один
  существующий документ не повышается. Для
  [первой записи нужна независимая проверка человеком](docs/TRUSTED_PROVENANCE_REGISTRY.md);
  user/workspace data не может добавить запись.

Trust invalidation после MCP write реализован для основных проверенных путей, но capability layer намеренно **не заявляет полное покрытие всех write paths**. Отдельно остаются неполностью закрытыми `plan_apply`, `ses_import`, `schematic_to_pcb_sync` и `live_session_apply`; их полное fail-closed trust invalidation входит в ближайший roadmap. Поэтому `get_capabilities` имеет приоритет над более общими описаниями документации.

Evidence manifests повторно валидируются при использовании и rollback; path aliases, source-type mismatch, stale hashes, неполные comparison categories и semantic differences приводят к fail-closed результату.

## Статус pattern recommendation

Текущий baseline умеет читать и валидировать существующие Pattern Libraries, сравнивать pad mapping и назначать компоненту уже существующий pattern при точном совпадении pad numbers. Pattern Editor bridge sessions намеренно read-only.

Persistent feedback/recommendation tools — `record_pattern_example`, `accept_pattern_suggestion`, `reject_pattern_suggestion` — пока не реализованы. До их разработки roadmap ставит выше закрытие реального DipTrace 5.3 evidence layer: fixture pack, trust-invalidation coverage и mask/paste/courtyard semantics.

После evidence closure планируется append-only provenance-bound feedback dataset, deterministic retrieval похожих принятых примеров и измеримый ranked recommendation workflow. Fine-tuning остаётся более поздней необязательной стадией.

Создание или изменение native Pattern/Component Libraries остаётся заблокировано до controlled DipTrace 5.3 before/after и open/save/re-export fixtures, подтверждающих writer semantics.

## Поставляемые агентские скиллы

Wheel теперь включает восемь компактных workflows в `diptrace_mcp/skills`: project intake,
library audit, schematic ERC review, testpoint planning, critical-net routing, signal-integrity
review, release gating и operator-assisted evidence capture. Они используют одну общую result
schema и выбраны по письменному механическому survival rule; прежний дублированный каталог из
57 пакетов не поставляется.

Скиллы оркестрируют зарегистрированные MCP tools и два поставляемых evidence CLI. Они не добавляют
скрытых EDA capabilities, не повышают trust evidence, не переопределяют runtime
`get_capabilities` и не регистрируются в agent host автоматически: укажите host путь к
установленному каталогу `diptrace_mcp/skills`. См.
[поставляемый каталог и ограничения](skills/README.md).

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
- [Compliance and provenance](docs/compliance/INDEPENDENT_REVIEW_PACKAGE.md)
- [Windows signing preparation](docs/SIGNING.md)
- [Testing and benchmarks](docs/TESTING.md)
- [Skill contracts](docs/SKILL_CONTRACTS.md)
- [PCB skills](skills/README.md)
- [Разработка](docs/DEVELOPMENT.md)
- [Windows/WSL live exchange paths](docs/LIVE_EXCHANGE_PATHS.md)
- [Live acceptance 2026-07-31](docs/LIVE_ACCEPTANCE_2026-07-31.md)
- [Code review 2026-07-31](docs/CODE_REVIEW_2026-07-31.md)
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
