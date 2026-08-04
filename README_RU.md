# DipTrace MCP

<!-- mcp-name: io.github.fireostendere/diptrace-mcp -->

[English](README.md) | **Русский**

[![CI](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/fireostendere/mcp_diptrace/actions/workflows/ci.yml)
[![Coverage gate](docs/badges/coverage.svg)](.github/workflows/ci.yml)

DipTrace MCP — локальный Model Context Protocol сервер для чтения, анализа,
инженерного ревью и контролируемого изменения PCB и schematic проектов
DipTrace. Проект состоит из двух компонентов:

- `diptrace-mcp` — MCP-сервер для Codex, Claude Desktop и других MCP-клиентов;
- `diptrace_mcp_bridge.exe` — Windows bridge-плагин для проектов, открытых в
  DipTrace.

## Текущее состояние

Версия `0.2.1` — текущая distribution line. Она подготовлена как явно
обозначенный unsigned alpha/development релиз со следующими каналами:

- Python package `diptrace-mcp==0.2.1` для PyPI;
- `DipTrace-MCP-Setup-0.2.1.exe`;
- `DipTrace-MCP-Portable-0.2.1.zip`;
- `DipTrace-MCP-0.2.1-windows.mcpb`;
- wheel, source distribution, checksums, SBOM, dependency, notice, provenance и
  release records.

Предыдущий релиз
[`v0.2.0`](https://github.com/fireostendere/mcp_diptrace/releases/tag/v0.2.0)
остаётся immutable. Существующие tags и files никогда не заменяются.

Windows executables unsigned. CI, SHA-256, PyPI Trusted Publishing и package
attestations подтверждают проверенное поведение, идентичность файлов и
происхождение публикации. Они не являются trusted Authenticode signature,
доказательством universal compatibility, independent review или production
readiness.

## Статус публичного релиза

Проект использует OSI-approved open-source `LICENSE` Apache-2.0. Правила участия
и релиза находятся в `CONTRIBUTING.md`, `GOVERNANCE.md`,
`docs/LICENSE_DECISION.md`, `docs/PUBLIC_RELEASE_CHECKLIST.md`,
`docs/RELEASE_PROCESS.md`, `CHANGELOG.md` и `CITATION.cff`. Сообщения о security
отправляются через приватный канал; проверенный Code of Conduct канал для
enforcement пока не опубликован.

- Python archives собираются по точному allowlist и проверяются по entry points,
  packaged skills, bounds, metadata и каждому `RECORD` hash и size.
- PyPI publication использует GitHub OpenID Connect и protected environment
  `pypi`; long-lived PyPI API token не хранится.
- PyPI publish job получает только уже проверенные wheel и source distribution
  из отдельного build job.
- Windows installer, bridge, standalone executable, configurator, portable
  bundle и MCPB остаются unsigned development assets.
- CI, checksums, Trusted Publishing и attestations не создают code-signing или
  production-readiness claim.

## Возможности

Публичный MCP-контракт содержит 159 зарегистрированных tools, 157 публичных
методов `DipTraceService` и 148 явных Facade → domain-service делегаций.
Фактическим источником истины для конкретной установки и документа остаётся
`get_capabilities`.

Основные группы возможностей:

- чтение и модели PCB, schematic, Component Library и Pattern Library;
- structured DRC/ERC, connectivity, BOM, assembly, DFM/DFA/DFT, comparison и
  signal-integrity assistance;
- guarded workflows для компонентов, schematic, NetClass, текста, трасс, via,
  panelisation, placement, routing и synchronization;
- preview, expected SHA-256, policy, backup, atomic replace, rollback и
  live-session apply/cancel;
- optional process adapters для Freerouting, ngspice и openEMS;
- локальный stdio и trusted-loopback Streamable HTTP.

DipTrace MCP не заменяет интерактивный EDA-движок DipTrace. Проект не заявляет
native Component/Pattern Library mutation, native Gerber/NC Drill generation,
fabrication sign-off, Novarm/DipTrace endorsement или universal compatibility
со всеми версиями DipTrace 5.x.

## Установка

### PyPI

Требуется Python 3.10 или новее:

```bash
python -m pip install diptrace-mcp==0.2.1
diptrace-mcp --help
```

PyPI package устанавливает Python MCP-сервер и packaged skills. Windows
DipTrace bridge-плагин автоматически не устанавливается.

### Windows installer

1. Скачайте `DipTrace-MCP-Setup-0.2.1.exe` и `SHA256SUMS.txt` из одного и того же
   GitHub Release `v0.2.1`.
2. Проверьте SHA-256.
3. Запустите installer и выберите DipTrace location, workspace, state directory
   и при необходимости настройку Codex/Claude.
4. Перезапустите DipTrace и MCP-клиент.
5. Вызовите `get_capabilities`.

Windows может показать SmartScreen warning, поскольку binaries unsigned.

### Portable Windows bundle

Скачайте и проверьте `DipTrace-MCP-Portable-0.2.1.zip`, распакуйте в постоянную
локальную директорию, прочитайте `README_FIRST.txt` и используйте включённые
helper tools.

### Установка из исходного кода

```bash
git clone https://github.com/fireostendere/mcp_diptrace.git
cd mcp_diptrace
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

Полный путь описан в
[инструкции установки из release assets](docs/INSTALL_FROM_RELEASE.md).

## MCPB, Registry и Smithery

Версия `0.2.1` добавляет immutable distribution route, подготовленный после
`v0.2.0`:

- deterministic Windows MCPB packaging;
- canonical Registry identity `io.github.fireostendere/diptrace-mcp`;
- официальный `server.json`, генерируемый из public MCPB URL и проверенного
  SHA-256;
- Smithery publication из того же public MCPB;
- PyPI Trusted Publishing для Python-сервера.

MCPB содержит self-contained Windows stdio server. Он не устанавливает DipTrace
bridge-плагин скрытно. Для live exchange нужны matching bridge и settings из
того же GitHub release.

См. [MCP distribution и package publication](docs/MCP_DISTRIBUTION.md).

## Архитектура

```text
MCP client (Codex / Claude / другой)
                 |
                 | stdio или trusted loopback HTTP
                 v
             FastMCP
                 |
                 v
      публичный Facade DipTraceService
                 |
                 +--> typed domain services
                 +--> shared stores, policy, cache, document gateway
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

## Модель безопасности

Основные write invariants:

1. пути остаются внутри configured allowed roots;
2. XML ограничивается и парсится до mutation;
3. preview и commit привязаны к точным SHA-256;
4. существующие targets получают backup;
5. запись использует temporary files и atomic replacement;
6. применяются policy и консервативные write-impact limits;
7. live apply повторно проверяет working, exchange и original-file identity;
8. cancel не изменяет host exchange file;
9. пользовательские sidecars не могут самостоятельно выдать высокий trust.

Q1 Component Angle GUI/re-export validation остаётся `NOT_RUN`. Несколько
проверок на реальной Windows, в DipTrace и MCP-клиентах остаются явно
задокументированными ограничениями.

## Обработка данных

- `DIPTRACE_MCP_WORKSPACE` задаёт обычный workspace; пути дополнительно
  ограничиваются `DIPTRACE_MCP_ALLOWED_ROOTS` и literal path checks.
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

## Документация

- [Использование](docs/USAGE.md)
- [MCP tools и resources](docs/MCP_TOOLS.md)
- [Архитектура](docs/ARCHITECTURE.md)
- [MCP distribution и package publication](docs/MCP_DISTRIBUTION.md)
- [Установка в Windows и Python](docs/INSTALL_FROM_RELEASE.md)
- [Тестирование](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Security и policy](docs/SECURITY_AND_POLICY.md)
- [Transactions](docs/TRANSACTIONS.md)
- [Release process](docs/RELEASE_PROCESS.md)
- [Checklist релиза v0.2.1](docs/RELEASE_0_2_1_CHECKLIST.md)
- [Release record v0.2.1](docs/releases/v0.2.1.md)

## Участие, security и лицензия

Contributions принимаются по DCO 1.1 и provenance/privacy rules из
[CONTRIBUTING.md](CONTRIBUTING.md). Сообщения об уязвимостях отправляйте через
приватный канал из [SECURITY.md](SECURITY.md), а не в публичные issues.

Apache License 2.0. См. [LICENSE](LICENSE).
