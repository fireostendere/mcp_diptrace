# Полное руководство DipTrace MCP

## 1. Назначение

DipTrace MCP даёт языковой модели структурированный доступ к данным платы или схемы. Он не эмулирует мышь и клавиатуру. Основой служит официальный DipTrace XML, в котором представлены компоненты, цепи, геометрия, правила и другие объекты проекта.

Есть два режима:

1. **Live** — анализ и правки проекта, открытого в DipTrace.
2. **Offline** — анализ и правки XML-файла на диске без запущенного DipTrace.

Live-режим удобен для интерактивной работы. Offline-режим удобен для ревью, автоматических отчётов, version control и пакетной обработки уже сохранённых XML-файлов.

## 2. Установка сервера

### 2.1 Windows

Установите Python 3.10–3.13. Проверьте:

```powershell
py -3 --version
```

Создайте окружение и установите проект:

```powershell
cd C:\path\to\mcp_diptrace
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Проверка:

```powershell
.\.venv\Scripts\diptrace-mcp.exe --help
```

### 2.2 Linux/macOS

Live-плагин предназначен для Windows, но offline-сервер кроссплатформенный:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
diptrace-mcp --help
```

### 2.3 WSL

DipTrace работает в Windows, а MCP-сервер может работать в WSL. Оба процесса должны смотреть на один каталог состояния Windows:

```bash
export DIPTRACE_MCP_WORKSPACE=/mnt/c/Users/you/Documents/DipTrace
export DIPTRACE_MCP_STATE_DIR=/mnt/c/Users/you/AppData/Local/DipTraceMCP
```

Если workspace расположен внутри `/mnt/<drive>/Users/<user>/...`, сервер обычно определяет Windows state directory автоматически. Явная переменная исключает неоднозначность.

## 3. Сборка DipTrace bridge

DipTrace требует исполняемый `.exe`. Скрипт собирает его через PyInstaller и включает только стандартную Python-библиотеку и модули bridge:

```powershell
cd C:\path\to\mcp_diptrace
powershell -ExecutionPolicy Bypass -File .\plugin\build_bridge.ps1
```

Результат:

```text
plugin\dist\diptrace_mcp_bridge.exe
```

Чистая пересборка:

```powershell
.\plugin\build_bridge.ps1 -Clean
```

Если команда Python называется не `py`:

```powershell
.\plugin\build_bridge.ps1 -PythonCommand "C:\Python312\python.exe"
```

## 4. Установка плагина в DipTrace

Закройте PCB Layout и Schematic Capture: список плагинов читается при запуске модуля.

Откройте PowerShell от имени администратора:

```powershell
cd C:\path\to\mcp_diptrace
.\plugin\install_plugin.ps1
```

По умолчанию создаются:

```text
C:\Program Files\DipTrace\Plugins\Pcb\DipTraceMCP\
C:\Program Files\DipTrace\Plugins\Schematic\DipTraceMCP\
```

В каждом каталоге находятся:

```text
diptrace_mcp_bridge.exe
settings.xml
```

Установка только для PCB Layout:

```powershell
.\plugin\install_plugin.ps1 -Mode PCB
```

Установка только для Schematic Capture:

```powershell
.\plugin\install_plugin.ps1 -Mode Schematic
```

Нестандартный каталог DipTrace:

```powershell
.\plugin\install_plugin.ps1 -DipTraceDir "D:\EDA\DipTrace"
```

Удаление:

```powershell
.\plugin\install_plugin.ps1 -Uninstall
```

После установки перезапустите DipTrace и проверьте `Tools → Plugins → DipTrace MCP Bridge`.

## 5. Подключение MCP-клиента

### 5.1 Codex CLI

Codex хранит MCP-серверы в `~/.codex/config.toml`. Быстрее всего добавить сервер командой:

```powershell
codex mcp add diptrace `
  --env "DIPTRACE_MCP_WORKSPACE=C:\Users\you\Documents\DipTrace" `
  -- "C:\path\to\mcp_diptrace\.venv\Scripts\diptrace-mcp.exe"
```

Проверка:

```powershell
codex mcp get diptrace --json
codex mcp list
```

Ручная конфигурация:

```toml
[mcp_servers.diptrace]
command = "C:\\path\\to\\mcp_diptrace\\.venv\\Scripts\\diptrace-mcp.exe"
cwd = "C:\\path\\to\\mcp_diptrace"

[mcp_servers.diptrace.env]
DIPTRACE_MCP_WORKSPACE = "C:\\Users\\you\\Documents\\DipTrace"
```

После изменения конфигурации перезапустите Codex или обновите MCP-серверы в клиенте.

### 5.2 Codex в WSL

```bash
codex mcp add diptrace \
  --env DIPTRACE_MCP_WORKSPACE=/mnt/c/Users/you/Documents/DipTrace \
  --env DIPTRACE_MCP_STATE_DIR=/mnt/c/Users/you/AppData/Local/DipTraceMCP \
  -- /mnt/c/path/to/mcp_diptrace/.venv/bin/diptrace-mcp
```

Python-окружение для WSL должно быть создано Linux Python, а не Windows Python.

### 5.3 Claude Desktop

Добавьте сервер в конфигурацию Claude Desktop и замените пути:

```json
{
  "mcpServers": {
    "diptrace": {
      "command": "C:\\path\\to\\mcp_diptrace\\.venv\\Scripts\\diptrace-mcp.exe",
      "env": {
        "DIPTRACE_MCP_WORKSPACE": "C:\\Users\\you\\Documents\\DipTrace"
      }
    }
  }
}
```

Полный шаблон лежит в `examples/claude_desktop_config.json`. После изменения полностью перезапустите Claude Desktop.

### 5.4 Любой STDIO MCP-клиент

Используйте:

```text
command: C:\path\to\.venv\Scripts\diptrace-mcp.exe
args: []
transport: stdio
```

Не направляйте диагностические сообщения сервера в `stdout`: этот канал занят JSON-RPC MCP.

### 5.5 Streamable HTTP

Запуск локального HTTP endpoint:

```powershell
.\.venv\Scripts\diptrace-mcp.exe --transport streamable-http --host 127.0.0.1 --port 8765
```

URL клиента:

```text
http://127.0.0.1:8765/mcp
```

Сервер не реализует собственную авторизацию. Не публикуйте его на внешнем интерфейсе. Для обычного локального клиента предпочтительнее `stdio`.

## 6. Live-сценарий

### 6.1 Начало

1. Откройте схему или плату.
2. Сохраните проект штатной командой DipTrace.
3. Запустите `Tools → Plugins → DipTrace MCP Bridge`.
4. Появится окно с идентификатором сессии.
5. DipTrace будет ждать завершения `.exe`; редактировать текущий документ в это время нельзя.
6. В MCP-клиенте попросите проверить статус.

Пример запроса:

> Используй DipTrace MCP. Покажи статус и краткую сводку активного проекта. Ничего не меняй.

Сервер вызывает `diptrace_status`, затем `summarize_design` без параметра `path`. Отсутствие `path` означает активную live-сессию.

### 6.2 Анализ

Примеры естественных запросов:

> Покажи все компоненты, содержащие `USB`, и их подключённые цепи.

> Найди R17 и перечисли цепи на всех его выводах.

> Покажи DRC, net classes и via styles активной платы.

> Проверь схему на выводы с `NetId=-1`, но отличай их от намеренного `NotConnected=Y`.

> Прочитай XML-фрагмент цепи `USB_D+` и не выводи остальной проект.

### 6.3 Изменение

Рекомендуемый запрос:

> Измени `Value` компонента R1 с 10k на 22k. Сначала выполни dry-run, проверь, что XPath совпал ровно один раз, покажи diff. Затем повтори запись с `expected_sha256` из preview.

После записи рабочая XML-копия изменена, но DipTrace ещё не импортировал её.

### 6.4 Завершение

Применить рабочую копию:

```text
finish_live_session(action="apply")
```

Отменить всю live-сессию:

```text
finish_live_session(action="cancel")
```

Можно нажать соответствующую кнопку в окне bridge. После закрытия процесса DipTrace импортирует файл или получает исходный неизменённый файл.

После `apply` обязательно:

1. визуально проверьте изменённые объекты;
2. запустите ERC для схемы или DRC/Check Net Connectivity для платы;
3. сохраните проект в DipTrace под контролируемой ревизией.

## 7. Offline-сценарий

### 7.1 Подготовка файла

Если проект хранится в старом бинарном формате:

```text
File → Export → DipTrace XML
```

Схему и плату экспортируют отдельно. Поместите файл внутри `DIPTRACE_MCP_WORKSPACE` или одного из `DIPTRACE_MCP_ALLOWED_ROOTS`.

### 7.2 Поиск

```text
scan_diptrace_documents(root="C:\\Projects\\BoardA", recursive=true)
```

Сканируются расширения `.xml`, `.dip`, `.dch`, `.eli`, `.lib`, но результатом становятся только файлы с XML-корнем `<Source Type="DipTrace-...">`.

### 7.3 Анализ конкретного файла

```text
summarize_design(path="BoardA/controller.xml")
list_components(path="BoardA/controller.xml", query="USB")
list_nets(path="BoardA/controller.xml", query="GND")
```

Относительные пути считаются от `DIPTRACE_MCP_WORKSPACE`.

## 8. Инструменты

| Инструмент | Назначение | Меняет файлы |
|---|---|---:|
| `diptrace_status` | Конфигурация и активная live-сессия | Нет |
| `scan_diptrace_documents` | Поиск DipTrace XML | Нет |
| `summarize_design` | Сводка схемы/платы | Нет |
| `list_components` | Список и поиск компонентов | Нет |
| `get_component` | Компонент и подключённые цепи | Нет |
| `list_nets` | Цепи и конечные точки | Нет |
| `get_design_rules` | ERC/DRC/net classes/via styles | Нет |
| `read_xml_fragment` | Ограниченное чтение XPath | Нет |
| `apply_xml_edits` | Preview или запись XML-операций | Только при `dry_run=false` |
| `finish_live_session` | Импорт или отмена live-сессии | Управляет live-сессией |

## 9. XML-операции

Поддерживаются:

- `set_text` — заменить текст элемента;
- `set_attribute` — установить атрибут;
- `remove_attribute` — удалить существующий атрибут;
- `append_xml` — добавить один XML-элемент внутрь найденного родителя;
- `replace_xml` — заменить найденный элемент одним XML-элементом;
- `delete_element` — удалить найденный элемент.

### 9.1 Изменить значение компонента

Preview:

```json
{
  "path": "controller.xml",
  "dry_run": true,
  "edits": [
    {
      "operation": "set_text",
      "xpath": "./Board/Components/Component[RefDes='R1']/Value",
      "value": "22k",
      "expected_matches": 1
    }
  ]
}
```

Запись повторяет тот же массив:

```json
{
  "path": "controller.xml",
  "dry_run": false,
  "expected_sha256": "SHA_ИЗ_PREVIEW",
  "edits": [
    {
      "operation": "set_text",
      "xpath": "./Board/Components/Component[RefDes='R1']/Value",
      "value": "22k",
      "expected_matches": 1
    }
  ]
}
```

Для схемы путь к значению обычно выглядит так:

```text
./Schematic/Components/Part[RefDes='R1']/Value
```

Многосекционный компонент может дать несколько совпадений. В таком случае задайте точный `expected_matches` или уточните XPath через `PartRefDes`, `PartNumber`, `Id` или другой признак.

### 9.2 Изменить атрибут

```json
{
  "operation": "set_attribute",
  "xpath": "./Board/Components/Component[RefDes='U1']",
  "attribute": "Locked",
  "value": "Y",
  "expected_matches": 1
}
```

### 9.3 Добавить дополнительное поле

Если у компонента нет `AddFields`, добавьте контейнер:

```json
{
  "operation": "append_xml",
  "xpath": "./Board/Components/Component[RefDes='U1']",
  "value": "<AddFields><AddField Type='Text'><Name>MPN</Name><Text>ABC-123</Text></AddField></AddFields>",
  "expected_matches": 1
}
```

Если `AddFields` уже существует, добавляйте только `AddField` внутрь него.

### 9.4 XPath

Используется синтаксис `xml.etree.ElementTree`, а не полный XPath 1.0. Поддерживаются обычные пути, `.//Tag`, индекс и простые предикаты, например `[RefDes='R1']` или `[@Id='0']`.

Корнем документа всегда является `Source`. Эквивалентны:

```text
./Board/Components
/Source/Board/Components
Source/Board/Components
```

Удаление или замена самого `<Source>` запрещены.

## 10. Переменные окружения

| Переменная | По умолчанию | Значение |
|---|---|---|
| `DIPTRACE_MCP_WORKSPACE` | текущий каталог процесса | Базовый каталог относительных путей |
| `DIPTRACE_MCP_ALLOWED_ROOTS` | только workspace | Дополнительные корни, разделённые `;` в Windows и `:` в Unix |
| `DIPTRACE_MCP_STATE_DIR` | `%LOCALAPPDATA%\DipTraceMCP` в Windows | Общий каталог live-сессий |
| `DIPTRACE_MCP_MAX_DOCUMENT_BYTES` | `134217728` | Максимальный размер одного XML |
| `DIPTRACE_MCP_MAX_SCAN_FILES` | `500` | Максимум проверяемых файлов при сканировании |
| `DIPTRACE_MCP_SESSION_TIMEOUT` | `7200` | Таймаут bridge в секундах |
| `DIPTRACE_MCP_TRANSPORT` | `stdio` | `stdio` или `streamable-http` |
| `DIPTRACE_MCP_HOST` | `127.0.0.1` | Адрес HTTP-сервера |
| `DIPTRACE_MCP_PORT` | `8765` | Порт HTTP-сервера |

Пример нескольких разрешённых корней Windows:

```text
DIPTRACE_MCP_ALLOWED_ROOTS=C:\Projects\Boards;D:\Archive\DipTrace
```

## 11. Резервные копии и state directory

Offline backup:

```text
<каталог XML>\.diptrace-mcp-backups\<имя>.<UTC>.<hash>.bak
```

Live state:

```text
%LOCALAPPDATA%\DipTraceMCP\
  active.json
  sessions\<uuid>\
    metadata.json
    original.xml
    working.xml
    control.json
    backups\
```

`original.xml` остаётся диагностической копией live-входа. `working.xml` изменяет MCP. `control.json` передаёт bridge только `apply` или `cancel` вместе с ожидаемым hash.

## 12. Диагностика

### Плагин не появился в меню

- полностью закройте все модули DipTrace;
- проверьте `Plugins\Pcb\DipTraceMCP\settings.xml` или `Plugins\Schematic\DipTraceMCP\settings.xml`;
- убедитесь, что рядом находится `diptrace_mcp_bridge.exe`;
- проверьте `ExeFile="diptrace_mcp_bridge.exe"`;
- запустите DipTrace заново.

### `No active DipTrace session`

- сначала запустите плагин из открытого документа;
- сравните `state_dir` в `diptrace_status` с `%LOCALAPPDATA%\DipTraceMCP`;
- для WSL явно задайте `DIPTRACE_MCP_STATE_DIR`;
- не запускайте вторую live-сессию до завершения первой.

### DipTrace выглядит зависшим

Во время live-сессии это ожидаемо: DipTrace ждёт завершения процесса плагина. Завершите сессию через MCP или кнопкой `Cancel` в bridge.

### Сервер отклоняет путь

Файл находится вне `DIPTRACE_MCP_WORKSPACE` и `DIPTRACE_MCP_ALLOWED_ROOTS`. Добавьте только нужный каталог, перезапустите MCP-сервер и повторите.

### `Expected <Source> root`

Передан не DipTrace XML. Старый `.dip`/`.dch` может быть бинарным. Экспортируйте `DipTrace XML` или включите нативное XML-сохранение в поддерживающей его версии.

### `matched N elements, expected M`

Защита сработала правильно. Сначала прочитайте подходящий фрагмент через `read_xml_fragment`, затем уточните XPath или явно укажите правильное число совпадений.

### `Document changed: expected ..., current ...`

Файл изменился после preview. Не обходите проверку: повторите dry-run на актуальной версии.

### Windows блокирует bridge

Собирайте `.exe` локально из репозитория. Проверьте hash и исходный код. При необходимости разрешите конкретный файл в корпоративной политике. Не отключайте защиту системы целиком.

### Проверка сервера вручную

```powershell
$env:DIPTRACE_MCP_WORKSPACE = "C:\Users\you\Documents\DipTrace"
.\.venv\Scripts\diptrace-mcp.exe --transport stdio
```

В `stdio` режиме процесс ожидает JSON-RPC и визуально ничего не выводит. Остановите `Ctrl+C`.

## 13. Инженерные ограничения

Изменение валидного XML ещё не доказывает корректность электрической схемы или платы. После любой записи проверяйте:

- уникальность и смысл `Id`/`UpdateId`;
- соответствие ссылок на component/part/pad/pin;
- net class и via style identifiers;
- единицы измерения из `Source@Units`;
- ERC/DRC и connectivity;
- визуальную геометрию, слои, маску, пасту и board outline;
- итоговый производственный экспорт.

Официальные схемы формата находятся в каталоге `Docs` установленного DipTrace и на странице [Tutorials & Docs](https://diptrace.com/support/tutorials/).
