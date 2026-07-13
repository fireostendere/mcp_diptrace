# DipTrace MCP

MCP-сервер для чтения, анализа и контролируемого изменения проектов DipTrace через официальный XML-формат. Репозиторий содержит два связанных компонента:

- `diptrace-mcp` — локальный Model Context Protocol сервер для Codex, Claude Desktop и других MCP-клиентов;
- `diptrace_mcp_bridge.exe` — плагин-мост для работы с проектом, который прямо сейчас открыт в PCB Layout или Schematic Capture.

## Что уже работает

- сводка по схеме или плате: компоненты, части, выводы, цепи, слои и дифференциальные пары;
- поиск компонентов по `RefDes`, имени, значению и дополнительным полям;
- просмотр цепей с конечными точками `RefDes + pin/pad`;
- чтение настроек ERC, DRC, net classes, via styles и routing defaults;
- ограниченное чтение исходного XML по XPath;
- безопасные XML-правки с обязательным числом совпадений;
- режим предварительного просмотра `dry_run` с diff;
- защита от одновременного изменения через `SHA-256`;
- автоматическая резервная копия перед каждой записью;
- live-сессия с явным завершением `apply` или `cancel`;
- offline-работа с экспортированным или нативным XML без запуска DipTrace;
- `stdio` и Streamable HTTP транспорты MCP.

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

## Ограничения

- сервер не управляет GUI DipTrace и не нажимает пункты меню;
- DipTrace блокирует текущий документ, пока live-плагин ожидает `apply`/`cancel`;
- MCP не заменяет визуальную проверку, ERC/DRC и инженерное ревью;
- универсальные XML-операции позволяют менять структуру, но модель должна соблюдать официальную схему DipTrace;
- старые бинарные проекты требуют экспорта в XML;
- одновременно поддерживается одна live-сессия;
- неподписанный bridge `.exe` может потребовать разрешения Windows Defender/SmartScreen.

## Документация

- [Полное руководство на русском](docs/USAGE_RU.md)
- [Архитектура и модель безопасности](docs/ARCHITECTURE.md)
- [Разработка и тестирование](docs/DEVELOPMENT.md)
- [Официальные спецификации DipTrace XML и плагинов](https://diptrace.com/support/tutorials/)
- [Официальный Python SDK MCP](https://github.com/modelcontextprotocol/python-sdk)
- [Подключение MCP к Codex](https://learn.chatgpt.com/docs/extend/mcp)

## Разработка

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
```
