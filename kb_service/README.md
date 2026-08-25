# Knowledge RAG Service

Локальная инженерная база знаний (RAG): datasheet'ы, application notes, гайды по
PCB/layout, документация DipTrace, YouTube-транскрипты. Поиск — гибридный
(семантика + BM25) с локальным реранкером, доступ агенту OpenCode — через MCP.

Полностью локальный: Qdrant в Docker, эмбеддинги и реранкер через FastEmbed
(локальный ONNX), без внешних API.

## Быстрый старт

```bash
cd kb_service

# 1. Зависимости (Python >= 3.10)
uv venv .venv && uv pip install -e ".[dev,youtube]" --python .venv/bin/python
# или: python -m venv .venv && .venv/bin/pip install -e ".[youtube]"

# 2. Qdrant
docker compose up -d

# 3. Первая индексация настроенных источников (config/sources.yaml)
.venv/bin/knowledge ingest-all

# 4. Проверка поиска
.venv/bin/knowledge search "TPS62130 layout recommendations"
.venv/bin/knowledge search "как уменьшить токовую петлю импульсного преобразователя"

# 5. MCP-сервер для OpenCode (stdio)
.venv/bin/knowledge-mcp
```

Повторный запуск `ingest-all` инкрементален: неизменившиеся файлы пропускаются
(по SHA-256 контента), изменённые переиндексируются точечно, новые добавляются.
Пересоздание коллекции Qdrant не страшно: реестр заметит отсутствие векторов и
доиндексирует только нужное.

## OpenCode

Уже подключено в `.opencode/opencode.json` репозитория:

```json
"knowledge": {
  "type": "local",
  "command": ["/mnt/c/Users/fireo/mcp_diptrace/kb_service/.venv/bin/knowledge-mcp"],
  "enabled": true
}
```

Для другой машины поменяйте путь. После запуска OpenCode в этом репозитории
доступны инструменты `knowledge_*`. Альтернатива на уровне пользователя:
`~/.config/opencode/opencode.json`, та же секция `mcp`.

## Инструменты MCP

| Tool | Назначение |
|------|-----------|
| `knowledge_search(query, filters?, top_k?)` | гибридный поиск; фильтры: `authority`, `doc_type`, `manufacturer`, `part_number`, `title`, `filename`, `source`; возвращает чанки + собранный `context` в рамках токен-бюджета |
| `knowledge_get(document_id, section?)` | все чанки документа (опционально одна секция) |
| `knowledge_ingest(source)` | индексация локального пути или URL (web/YouTube/PDF) |
| `knowledge_sources(query?)` | список проиндексированных документов с id |
| `knowledge_status()` | состояние сервиса, счётчики, источники |
| `knowledge_research(query)` | **намеренная заглушка** |

### knowledge_research

Честная заглушка вместо фейка: полноценный web-research требует внешний
search API (Tavily / Brave Search API / SearXNG). Когда появится — реализуется
как «поиск в интернете → knowledge_ingest найденных URL → knowledge_search».
Инструмент никогда не пишет ответы LLM обратно в базу: в индекс попадают только
материалы с provenance (путь/URL + хеш + дата).

## CLI

```
knowledge ingest <path|url> [--force]   # один источник
knowledge ingest-all [--force]          # всё из config/sources.yaml
knowledge search "<query>" [--top-k N] [--filter '{"authority":"datasheet"}'] [--json]
knowledge get <document_id> [--section "..."]
knowledge sources [<query>]
knowledge delete <doc_id|source-substring>
knowledge status
knowledge serve                          # = knowledge-mcp
```

## Источники и доверие

`config/sources.yaml`: типы `directory | file | website | youtube`.
Tier доверия (`authority`) берётся из поля источника либо выводится из пути/URL
(`datasheets/` → datasheet, `appnotes/` → appnote, diptrace.com → official_docs).
Веса заданы в `config/settings.yaml` (`authority_weights`) и используются как
мягкий бонус при ранжировании + доступны как фильтр.

Расширяемость ingestion: `register_type(name, handler)` в
`src/knowledge_base/ingest.py` — точка подключения GitHub/KiCad/Gerber/ODB++
парсеров без правки диспетчера.

## Конфигурация

`config/settings.yaml` + переменные окружения (см. `.env.example`):
`QDRANT_URL`, `KB_COLLECTION`, `KB_DATA_DIR`, `KB_EMBEDDING_MODEL`,
`KB_RERANK_MODEL` (пусто = выключить реранкер), `KB_CHUNK_SIZE`,
`KB_CHUNK_OVERLAP`, `KB_MAX_CONTEXT_TOKENS`.

Модели скачиваются один раз при первом использовании и кэшируются
(`~/.cache/fastembed`, суммарно ~1 ГБ для e5-large + reranker).

## Тесты

```bash
docker compose up -d          # нужен живой Qdrant
.venv/bin/python -m pytest tests/ -q
```

Покрывают: ingest PDF → дедупликация → обновление изменённого файла,
семантический RU-поиск, поиск по парт-номеру, metadata-фильтры,
provenance (источник/страница/секция), работу после переподключения,
и end-to-end запуск MCP-сервера по stdio (как это делает OpenCode).
Интернет не нужен: фикстуры лежат в `tests/fixtures/`.

## Структура

```
kb_service/
├── config/{settings,sources}.yaml   # настройки и список источников
├── sources/{datasheets,appnotes,books}/   # ваши материалы (папки)
├── data/                            # Qdrant storage, SQLite-реестр, оригиналы (git ignored)
├── src/knowledge_base/
│   ├── extract.py    # PDF/MD/TXT/HTML -> блоки (заголовки, страницы)
│   ├── chunk.py      # структурные чанки (не режет секции)
│   ├── metadata.py   # парт-номера, revision, manufacturer, authority (без выдумок)
│   ├── sparse.py     # BM25 term-frequency (IDF считает Qdrant)
│   ├── embed.py      # FastEmbed dense + cross-encoder reranker
│   ├── store.py      # Qdrant + SQLite registry
│   ├── ingest.py     # пайплайн + fetchers + register_type()
│   ├── search.py     # гибрид + реранк + фильтры + бюджет
│   ├── cli.py        # команда knowledge
│   └── mcp_server.py # 6 tools для OpenCode
└── tests/
```

## Ограничения v1

- PDF извлекаются через pypdf: сложные таблицы могут читаться криво.
- YouTube-каналы/плейлисты требуют `yt-dlp` (extra `youtube`); видео — только субтитры.
- `website recursive` ограничен тем же доменом и глубиной 2 (`web_max_pages`).
- Реранкер добавляет ~1–3 c на запрос (CPU), отключается `KB_RERANK_MODEL=""`.

## Следующие шаги (логичные)

- PCB-ingestion: Gerber/ODB++/IPC-2581 через `register_type()`.
- `knowledge_research`: Tavily/Brave/SearXNG + авто-ingest находок.
- GitHub-источник (релизы/вики репозиториев).
- Оценка качества поиска (golden questions set) в CI.
