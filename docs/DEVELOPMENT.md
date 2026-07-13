# Разработка

## Структура

```text
src/diptrace_mcp/
  bridge.py         Windows bridge process and GUI
  config.py         environment and path policy
  inspector.py      DipTrace PCB/Schematic interpretation
  server.py         FastMCP registration and CLI
  service.py        use cases and write workflow
  sessions.py       shared live-session state
  xml_document.py   secure XML parsing and guarded edits
plugin/
  settings/         official DipTrace plug-in settings structure
  build_bridge.ps1  PyInstaller build
  install_plugin.ps1
tests/
  fixtures/         minimal PCB and Schematic XML
```

## Окружение

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Проверки

```bash
pytest
ruff check .
python -m compileall -q src tests
python scripts/mcp_smoke.py
```

По умолчанию smoke-тест использует детерминированный in-memory транспорт MCP. Для
проверки запуска отдельного процесса через stdio выполните:

```bash
python scripts/mcp_smoke.py --transport stdio
```

Тесты не используют установленный DipTrace и работают на минимальных XML fixtures.

## Локальный запуск

```bash
DIPTRACE_MCP_WORKSPACE="$PWD/tests/fixtures" diptrace-mcp
```

Streamable HTTP:

```bash
diptrace-mcp --transport streamable-http --host 127.0.0.1 --port 8765
```

## Проверка bridge без DipTrace

Скопируйте fixture во временный каталог и запустите bridge в headless-режиме:

```bash
cp tests/fixtures/pcb.xml /tmp/plugin_exchange.xml
DIPTRACE_MCP_STATE_DIR=/tmp/diptrace-state \
  python -m diptrace_mcp.bridge --headless --timeout 30 /tmp/plugin_exchange.xml
```

В другом процессе используйте `SessionStore.request_finish("cancel")` или MCP-сервер с тем же `DIPTRACE_MCP_STATE_DIR`.

## Версии SDK

Проект использует стабильную ветку MCP Python SDK 1.x и фиксирует верхнюю границу `<2`, потому что API 2.x развивается отдельно. Обновление major-версии требует отдельной проверки FastMCP API, MCP Inspector и клиентских конфигураций.

## Добавление предметного инструмента

1. Добавьте чистую функцию в `inspector.py` или use case в `service.py`.
2. Добавьте fixture или расширьте существующий минимальным официальным XML-фрагментом.
3. Покройте чистую функцию тестом.
4. Зарегистрируйте thin wrapper в `server.py`.
5. Обновите таблицу инструментов в `docs/USAGE_RU.md`.

## Правила формата

- Не придумывайте имена XML-тегов или смысл чисел.
- Сверяйте изменения со спецификациями из `C:\Program Files\DipTrace\Docs` или с официальной страницей документации.
- Не парсите старый бинарный `.dip`/`.dch` как XML.
- Сохраняйте точные `Id`, `UpdateId` и ссылки между списками.
- Любая новая write-операция должна поддерживать preview, match guard, hash guard и backup.
