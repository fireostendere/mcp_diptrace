# План физической валидации I²C level-shifter PCB

Статус: `IN PROGRESS — M1 OPERATOR PASS; FREEZE COMMIT PENDING`

Цель: получить честное физическое подтверждение для **одной точной ревизии**
демонстрационной платы 3,3 В ↔ 5 В, а не объявить универсально проверенным весь
PCB-генератор.

Базовый PASS состоит из четырёх независимых результатов:

1. реальный DipTrace принял плату после native refill/DRC/save/reopen/re-export;
2. изготовитель принял пакет, а полученная плата соответствует CAM и чертежу;
3. собранный образец проходит проверки без питания и статический перевод уровней;
4. реальный I²C проходит в обе стороны на 100 кГц без ошибок.

Отдельный `PASS-FM` разрешает claim Fast-mode 400 кГц только после измерения
фронтов. SI/PI/EMC, серийная технологичность и универсальная совместимость этим
планом не заявляются.

## 1. Идентичность кандидата

Начальная точка, найденная при составлении плана:

| Поле | Значение |
| --- | --- |
| Git commit | `2506ca1` |
| PCB source | `i2c-level-shifter-pcb.dipxml` |
| PCB SHA-256 до исправления BOM | `0478717d8fe7fa21746c836a6eaed9d9d0f5f17f87b5ab2fbd1288971cde480c` |
| Schematic source | `i2c-level-shifter-module.dchxml` |
| Schematic SHA-256 до исправления BOM | `88b030b7712c0238897b021f3d572a2a93b20303aca8aca83321d335b56ce51a` |
| Размер платы по XML | 25 × 12 мм |
| Слои | 2, сигналы и питание Top, GND pours Top/Bottom |
| Состав | Q1/Q2 BSS138; R1–R4 pull-up; J1/J2 1×4, 2,54 мм |
| Аппаратный кандидат | `PV-0 / 4,7 кОм; worktree не закоммичен` |
| PCB SHA-256 кандидата | `a272793597e556e87250e9b703a878182629995d2d20dbacf03c897f060fc118` |
| Schematic SHA-256 кандидата | `bb34fca9fb7e6ee9108b77d84be5bd101df9ec32c987e91d8c23a00b5295dd7e` |
| Финальный commit | `TBD после M1/freeze; base commit 2506ca1` |
| DipTrace build/profile | `5.3.0.3 / diptrace-5.3-en-v1` |
| Изготовитель, заказ, stackup | `TBD` |
| Серийные номера образцов | `TBD` |

### PV-0 — блокер до заказа

- [x] Выбрать фактическое сопротивление pull-up и устранить расхождение во всех
  исходниках/BOM.

Закрыто 2026-08-20: R1–R4 зафиксированы как **4,7 кОм ±1 %**, MPN
`0402WGF4701TCE`, LCSC `C25900`; XML разбирается, старые `0402WGF1002TCE` и
`C25744` отсутствуют в физических schematic/PCB-артефактах. Заказ всё ещё
запрещён до успешного M1 и фиксации commit.

## 2. Источники критериев

- Топология и pinout разъёмов: текущие `dchxml`/`dipxml` и генератор
  `scripts/build_i2c_level_shifter_pcb.py`.
- BSS138: [onsemi BSS138/D, Rev. 7, April 2024](https://www.onsemi.com/pdf/datasheet/bss138-d.pdf).
  Pin 1 = Gate, pin 2 = Source, pin 3 = Drain; в текущем PCB это соответственно
  3V3, низковольтная линия и высоковольтная линия.
- Схема двунаправленного перевода: [Nexperia AN10441 Rev. 2](https://assets.nexperia.com/documents/application-note/AN10441.pdf).
  Gate подключается к меньшему VDD, Source — к низковольтной секции, Drain — к
  высоковольтной; нормальное условие `VDD2 >= VDD1`.
- Электрические уровни и времена I²C: [NXP UM10204 Rev. 7](https://www.nxp.com/docs/en/user-guide/UM10204.pdf),
  таблицы 10–11 и раздел 7.1.
- Детали pull-up: [выбранный C25900, 4,7 кОм](https://www.lcsc.com/product-detail/Chip-Resistor-Surface-Mount-UniOhm_4-7KR-4701-1_C25900.html)
  и [его datasheet](https://www.lcsc.com/datasheet/C25900.pdf).

Ниже ни одно неизвестное значение не подменяется догадкой: допуски
изготовителя, реальная ёмкость шины, ток утечки стенда и пределы подключённых
контроллеров записываются после выбора конкретных изделий.

## 3. Карта разъёмов и каналов

| Контакт | J1 — LV | J2 — HV |
| --- | --- | --- |
| 1 | GND | GND |
| 2 | 3V3 | 5V |
| 3 | SCL_3V3, Q2 Source | SCL_5V, Q2 Drain |
| 4 | SDA_3V3, Q1 Source | SDA_5V, Q1 Drain |

R1/R2 подтягивают SDA/SCL LV к 3V3. R3/R4 подтягивают SDA/SCL HV к 5V.
Q1/Q2 Gate подключены к 3V3.

## 4. Оборудование и стенд

| Нужно | Требование | Фактически |
| --- | --- | --- |
| Осмотр | лупа/микроскоп; камера | `___` |
| Геометрия | штангенциркуль; 1:1 распечатка до заказа | `___` |
| Электрика | мультиметр с continuity/diode/µA | `___` |
| Питание | два канала 3,3 В и 5 В с независимым ток-лимитом, общий GND | `___` |
| Сигналы | осциллограф ≥2 каналов; лучше 4, щупы ×10 с известной ёмкостью | `___` |
| Протокол | логический анализатор с допустимым входом 5 В | `___` |
| I²C | 3,3-В controller и 5-В target; для обратного теста — переставляемые роли | `___` |
| Температура | IR/термопара необязательна; при этих мощностях любой заметный нагрев подозрителен | `___` |

Правила стенда:

- GPIO только open-drain (`drive LOW / release`), никогда не push-pull HIGH;
- все встроенные pull-up на dev-board/анализаторе отключить либо записать их
  значение и пересчитать эквивалентное сопротивление;
- до подключения логического анализатора подтвердить его допустимость для 5 В;
- записать модель и входную ёмкость осциллографических щупов: она входит в
  измеряемое время нарастания;
- сначала короткие провода, затем ровно тот кабель/нагрузка, для которых нужен
  claim.

## 5. Фаза A — freeze и native DipTrace acceptance (M1)

- [x] PV-0 закрыт в первичном schematic, физическом schematic и PCB; генератор
  успешно прошёл. Текущий воспроизводимый кандидат содержит 17
  распределённых GND stitching vias.
- [x] PCB, MP4 и GIF повторно сгенерированы 2026-08-20; проверены
  первый/средний/последний кадры и contact sheet 26 стадий.
- [ ] Записаны commit и SHA-256 исходного PCB-кандидата.
- [x] `pcb_native_acceptance` запущен из этого же source commit/editable install,
  а не из опубликованного `v0.4.0`, где post-release модуль ещё отсутствовал;
  окружение: `.venv-win-tests/Scripts/python.exe`, текущий `src` через
  `PYTHONPATH`, DipTrace `Pcb.exe` 5.3.0.3.
- [x] На 1:1 распечатку приложены реальные BSS138, 0402 и 1×4 headers; pitch,
  pad geometry и ориентация pin 1 подтверждены. Печатный лист подготовлен:
  `.local/physical-validation/phase-a/review/09-physical-fit-1to1-A4.pdf`;
  печатать только в режиме 100% / Actual Size и сначала проверить контрольные
  100,00 мм. Наблюдение оператора 2026-08-20: `PASS — физически и по фото всё
  соответствует`; численные измерения не сообщены.
- [x] Выполнен native workflow из `docs/EVIDENCE_CAPTURE.md` на точном DipTrace
  build. Пример команды из Windows PowerShell:

```powershell
py -m diptrace_mcp.pcb_native_acceptance run `
  --diptrace-root "C:\Program Files\DipTrace" `
  --project "C:\work\i2c-level-shifter-pcb.dipxml" `
  --output-xml "C:\work\evidence\i2c-level-shifter.native.dipxml" `
  --evidence-json "C:\work\evidence\i2c-level-shifter.native-evidence.json" `
  --desktop native `
  --refill-menu "#3->#14" `
  --drc-menu "#7->#0" `
  --save-as-menu "#0->#4"
```

- [x] Native copper refill завершён без ошибки.
- [x] Native DRC: `0` blocking errors; диалог `No errors found`:
  `.local/physical-validation/phase-a/inset-visible-verdict.png`.
- [x] После refill GND ratline скрыта DipTrace; J1.1, J2.1 и оба pour
  сохранили один NetId. Необъяснённой ratline нет.
- [x] Bottom GND непрерывен; Top GND полезен; нет островов и узких случайных
  перемычек. Наблюдение: native `Bottom (2)` view показывает сплошную заливку
  без сигнальных трасс; Top view показывает рабочую заливку вокруг трасс.
- [x] Stitching распределён по всей плате, включая верхние/нижние свободные
  области; не принимается один лишь счётчик via. Наблюдение: 17 via видны в
  верхней, центральной и нижней свободных областях полного Top/Bottom view.
- [x] На J1.1/J2.1 после реального refill видны четыре thermal spokes; отдельные
  крупные планы сохранены в пакете визуальных доказательств.
- [x] Все positive-power и signal traces находятся на Top; Bottom не разрезан
  ненужными трассами.
- [x] Outline компактен и равен ожидаемым 25 × 12 мм; компоненты центрированы и
  симметричны без нарушения clearance.
- [x] Silkscreen читаем, привязан к своему компоненту, не касается pad/hole/via
  и не входит в чужой courtyard.
- [x] Save → Close → Reopen → re-export завершены; structural delta
  пуст. `HUMAN_REVIEW_REQUIRED` ограничен пересчётом `CopperPourFills`
  с округлением координат на ±0,000001″; этот bounded delta принят.
- [x] Сохранены source/candidate/native/export hashes, Top/Bottom screenshots,
  thermal/stitching close-ups и единый contact sheet:
  `.local/physical-validation/phase-a/review/`.
- [x] Оператор глазами просмотрел пакет и выдал verdict 2026-08-20:
  `PASS — физически и по фото всё соответствует`; замечаний не заявлено.

### Журнал M1 — 2026-08-20

- Кандидат: 8 физических компонентов + 17 via-components, 7 nets, 14 traces,
  2 pours; source SHA-256
  `a272793597e556e87250e9b703a878182629995d2d20dbacf03c897f060fc118`.
- Реальная карта owner-drawn меню: refill `#3 -> #14`, DRC `#7 -> #0`,
  Save As `#0 -> #4`. Разделители не входят в индексы pywinauto.
- Исходные pours касались outline и после реального refill давали две ошибки
  `Copper pour - Board outline`. Корневая правка: граница обоих pours смещена
  внутрь на board clearance 0,2 мм, `SnapToBoard=N`.
- После правки native refill и DRC завершились сообщением `No errors found`.
  Screenshot SHA-256:
  `5d2e2ac49b6d034adc15de3a2b2d71b4346d727848f7aab322da3673c5d7a936`.
- Полный цикл open → refill → DRC → save → close → reopen → re-export завершён
  без forced termination. Повторный native round-trip имеет пустой structural
  delta и `drc_status=pass`. Evidence:
  `.local/physical-validation/phase-a/i2c-level-shifter.final10-native-evidence.json`,
  SHA-256 `72f865d0ee94734abebcaf81a534c0ca6d440a65eade449e4a22648fe417312d`.
- Native XML SHA-256:
  `928e9047390504fdc48e6db4e91266379af17fe4df711d376003899aa407afcf`.
  Единственный semantic delta второго round-trip — пересчитанные производные
  `CopperPourFills` с округлением координат ±0,000001″; connectivity, counts,
  topology и атрибуты не изменились. Bounded review принят.
- MP4/GIF пересобраны из 26 стадий: сначала outline, затем 8 компонентов,
  14 трасс и финальные pours + 17 vias. SHA-256 MP4
  `30c4765e7e0e47948b35ba8de6686df95ada3397eae8752dd4cb622c0b9bfcc4`,
  GIF `05716de6e42220069287aa6d3c8ebd3ea019ac482ff7497991b432f3394d83ba`.
- Собран пакет для человеческой верификации:
  `.local/physical-validation/phase-a/review/README.md`; общий лист
  `00-review-sheet.png`, SHA-256
  `6b4850004e8de5b1aded782cf4b9f23747706508c7e3565a4cfb279e193dc65a`.
  Полный реестр находится в `review/SHA256SUMS`.
- Оператор 2026-08-20 подтвердил `PASS` физической примерки и просмотра фото;
  замечаний не заявил. Численные размеры отдельно не переданы.
- Verdict: проверки M1 — `PASS`. Формальный freeze M1 завершится после записи
  финального commit и его SHA-256 в идентичность кандидата.

**Стоп:** любой DRC error, необъяснённая ratline/island, неверный pin mapping,
потерянный thermal или semantic/connectivity delta возвращает плату на
исправление; к производству не переходить.

## 6. Фаза B — manufacturing package (M6-lite)

- [ ] Зафиксированы: PCB revision, BOM, footprint list, 2-layer stackup, copper
  weight, finish, solder-mask, board thickness и правила выбранного
  изготовителя. Значения изготовителя: `___`.
- [ ] Gerber/NC Drill и, если нужна сборка, BOM/CPL экспортированы штатным
  DipTrace/проверенным экспортёром из **native-saved** файла. Репозиторий не
  считается самостоятельным авторитетным Gerber-генератором.
- [ ] SHA-256 производственного ZIP: `___`.
- [ ] В независимом CAM viewer просмотрены outline, оба copper, mask, silk и
  drill; mirrored/missing/duplicate layers отсутствуют.
- [ ] Проверены 0,3-мм finished via holes, annular rings, header holes, mask
  dams, 0402 paste openings, copper-to-edge и silkscreen-to-pad по rule deck
  изготовителя. Принятые реальные допуски: `___`.
- [ ] В CAM подтверждены Top/Bottom GND, 17 распределённых stitching vias и
  четыре spokes на обоих GND header pads.
- [ ] Изготовитель закрыл DFM без blocking warning; waiver ledger: `___`.
- [ ] Сохранены CAM screenshots, DRC, DFM report, order ID и точный package hash.

Минимальный физический proof допускает ручную сборку одного экземпляра. Claim
готовности к серийной PCBA требует отдельно принятого BOM/CPL и сборочного DFM.

## 7. Фаза C — входной и визуальный контроль (без питания)

Для каждого образца завести ID: `A___ / B___ / C___`.

- [ ] Фото Top/Bottom до пайки и после пайки.
- [ ] Размеры платы: X `___` мм, Y `___` мм; соответствуют чертежу и допуску
  изготовителя `___`.
- [ ] Headers входят без усилия/раздвигания отверстий; фактический pitch `___`.
- [ ] Нет замыканий/недотрава/разрывов, повреждённой маски, поднятых pad,
  смещённых отверстий и острых краёв.
- [ ] Q1/Q2: правильная ориентация pin 1, нет bridges и непропая SOT-23.
- [ ] R1–R4: все четыре установлены, без tombstone/bridge; фактический MPN и
  номинал из assembly record `___`.
- [ ] J1/J2: pin 1 и сторона LV/HV однозначно различимы.
- [ ] При ручной пайке одинаковым процессом GND pads J1.1/J2.1 смачиваются без
  заметно большего времени/температуры, чем соседние pads. Наблюдение: `___`.

## 8. Фаза D — проверки без питания

Внешние платы и источники отключены.

| Проверка | Ожидание из netlist/datasheet | Измерено | PASS |
| --- | --- | --- | --- |
| J1.1 ↔ J2.1 | continuity, GND | `___` | `[ ]` |
| J1.2 ↔ GND | OL/no continuity | `___` | `[ ]` |
| J2.2 ↔ GND | OL/no continuity | `___` | `[ ]` |
| J1.2 ↔ J2.2 | нет прямого rail connection | `___` | `[ ]` |
| J1.3 ↔ Q2 Source/R2 signal pad | continuity | `___` | `[ ]` |
| J2.3 ↔ Q2 Drain/R4 signal pad | continuity | `___` | `[ ]` |
| J1.4 ↔ Q1 Source/R1 signal pad | continuity | `___` | `[ ]` |
| J2.4 ↔ Q1 Drain/R3 signal pad | continuity | `___` | `[ ]` |
| Q1/Q2 Gate ↔ J1.2 | continuity | `___` | `[ ]` |
| Q1 Source → Drain, diode mode | diode только в одном направлении; reverse OL | `___` | `[ ]` |
| Q2 Source → Drain, diode mode | diode только в одном направлении; reverse OL | `___` | `[ ]` |
| R1–R4 | выбранный номинал ±1 % плюс точность DMM | `___` | `[ ]` |

Если in-circuit измерение резистора искажено параллельным путём, номинал
подтверждается на spare part/assembly reel; результат не «подгоняется».

**Стоп:** continuity rail-to-GND, перепутанная ориентация body diode, неверная
цепь разъёма или необъяснимый номинал.

## 9. Фаза E — первое питание с ток-лимитом

Сначала плата без внешних I²C-устройств. Общий GND источников подключается к
J1.1/J2.1. До этой фазы оператор отдельно подтверждает готовность.

Для варианта 4,7 кОм ±1 %:

- `Rmin = 4653 Ω`;
- максимум при удержании обеих линий LOW на LV:
  `2 × 3.3 / Rmin = 1.419 mA`;
- максимум при удержании обеих линий LOW на HV:
  `2 × 5 / Rmin = 2.150 mA`.

Поэтому рабочие стартовые limits: **2,0 мА для 3V3 и 3,0 мА для 5V**. Они
пересчитываются, если PV-0 выбрал другой номинал. Если ЛБП не держит столь малый
limit, для первого idle-smoke допустимы временные series resistors 680 Ω в 3V3
и 1 кΩ в 5V: при прямом КЗ они ограничивают ток примерно 4,9/5 мА; перед
динамическими тестами их удалить после успешной проверки.

- [ ] Проверка только 3V3, 5V физически отключён: limit не срабатывает,
  напряжение/ток записаны `___`.
- [ ] Проверка только 5V, 3V3 физически отключён: limit не срабатывает,
  напряжение/ток записаны `___`.
- [ ] Оба rail включены, `VDD2 >= VDD1`; фактические VDD: `___ / ___`.
- [ ] Idle signals: J1.3/J1.4 находятся у измеренного 3V3, J2.3/J2.4 — у
  измеренного 5V. Значения: `___`.
- [ ] Idle supply current не вызывает limit и соответствует только утечкам
  платы плюс известной утечке стенда; фактически `___ / ___`.
- [ ] Через 60 с нет заметного нагрева; температура/наблюдение `___`.

**Стоп:** срабатывание limit, просадка rail, signal HIGH на неправильном уровне,
запах или нагрев. Питание снять и вернуться к локализации rail/component.

## 10. Фаза F — статический двунаправленный перевод

LOW создаётся open-drain ключом. Для каждой строки сначала измеряется idle HIGH,
затем LOW на обеих сторонах и ток каждого источника.

| Канал и возбуждение | Ожидание | LV/HV LOW | I3V3/I5V | PASS |
| --- | --- | --- | --- | --- |
| J1.4 SDA_LV → LOW | J2.4 также LOW | `___ / ___` | `___ / ___` | `[ ]` |
| J2.4 SDA_HV → LOW | J1.4 также LOW | `___ / ___` | `___ / ___` | `[ ]` |
| J1.3 SCL_LV → LOW | J2.3 также LOW | `___ / ___` | `___ / ___` | `[ ]` |
| J2.3 SCL_HV → LOW | J1.3 также LOW | `___ / ___` | `___ / ___` | `[ ]` |

Критерии:

- HIGH каждой стороны не ниже `0.7 ×` её **измеренного** VDD и практически
  подтянут к своему rail;
- LOW обеих сторон ≤ 0,4 В;
- при одной LOW-линии ожидаемый ток pull-up примерно `VDD/R`; при двух —
  `2×VDD/R`, с учётом допуска R и точности приборов;
- после release обе стороны возвращаются HIGH без защёлкивания;
- SDA и SCL проходят все четыре направления одинаково.

## 11. Фаза G — реальный I²C и осциллограф

### G1. Подготовка

- [ ] Зафиксированы controller/target, firmware hashes, адрес target, кабель,
  эффективные pull-up и модели щупов: `___`.
- [ ] Одновременно наблюдаются LV/HV одной линии; measurement thresholds
  выставлены 30–70 % от соответствующего измеренного VDD.
- [ ] Логический анализатор декодирует START, address, ACK, data, repeated START
  и STOP.

### G2. Базовый claim — Standard-mode 100 кГц

- [ ] Controller на 3,3-В стороне, target на 5-В стороне: не менее 10 000
  write/read transactions с шаблонами `00 FF 55 AA`/счётчиком; 0 NACK,
  timeout и data mismatch. Результат: `___`.
- [ ] Роли/стороны переставлены: controller на 5 В, target на 3,3 В; тот же
  тест, 0 ошибок. Результат: `___`.
- [ ] Если target умеет clock stretching, один тест явно подтверждает передачу
  LOW SCL с target-стороны; иначе этот subclaim помечается `NOT TESTED`, а не PASS.
- [ ] На SDA и SCL обеих сторон: `tr(30–70 %) <= 1000 ns`, `tf <= 300 ns`,
  `VOL <= 0.4 V`, HIGH >= `0.7×VDD`; нет повторного пересечения порога из-за
  ringing. Таблица измерений заполнена ниже.

### G3. Усиленный claim — Fast-mode 400 кГц

Выполняется только если проект хочет писать о поддержке 400 кГц.

- [ ] Оба направления проходят те же 10 000 transactions без ошибок.
- [ ] На всех четырёх наблюдаемых линиях `tr(30–70 %) <= 300 ns` и
  `tf <= 300 ns`; остальные уровни остаются в пределах G2.
- [ ] Проверено на целевом кабеле/нагрузке, а не только на коротком лабораторном
  проводе.

| Режим | Линия | Сторона | tr | tf | VOL | VOH | PASS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 100 кГц | SDA | LV | `___` | `___` | `___` | `___` | `[ ]` |
| 100 кГц | SDA | HV | `___` | `___` | `___` | `___` | `[ ]` |
| 100 кГц | SCL | LV | `___` | `___` | `___` | `___` | `[ ]` |
| 100 кГц | SCL | HV | `___` | `___` | `___` | `___` | `[ ]` |
| 400 кГц | SDA | LV | `___` | `___` | `___` | `___` | `[ ]` |
| 400 кГц | SDA | HV | `___` | `___` | `___` | `___` | `[ ]` |
| 400 кГц | SCL | LV | `___` | `___` | `___` | `___` | `[ ]` |
| 400 кГц | SCL | HV | `___` | `___` | `___` | `___` | `[ ]` |

Для оценки причины медленного фронта допускается формула UM10204
`tr = 0.8473 × Rp × Cb`; это оценка полной ёмкости конкретного стенда, не новый
datasheet claim. Для 4,7 кОм теоретический предел Cb — около 251 пФ при 100 кГц
и 75 пФ при 400 кГц; для 10 кОм — около 118 пФ и 35 пФ соответственно.

## 12. Фаза H — power-state и повторяемость

- [ ] При отключённом 3V3 и активном 5V нет необъяснимого back-power;
  измеренные rail/signal/current `___`.
- [ ] При отключённом 5V и активном 3V3 нет необъяснимого back-power;
  измеренные rail/signal/current `___`.
- [ ] Power-off состояние сверено с пределами конкретных controller/target;
  отсутствие повреждения не считается доказательством допустимого back-power.
- [ ] Полный G1–G3 выполнен на одном representative specimen.
- [ ] На всех остальных собранных экземплярах выполнены минимум фазы C–F и
  100-кГц smoke; результаты `___`.
- [ ] Любой repair/rework записан с фото и причиной; repaired unit не скрывается
  внутри общего PASS.

## 13. Evidence pack и итоговый verdict

Хранить вне исходников либо в явно выбранном capture root; в репозитории
достаточно ссылок, хешей и компактного отчёта.

- [ ] manifest: commit, все SHA, DipTrace/OS/profile, rule deck, fab order,
  board/assembly revisions и specimen IDs;
- [ ] native evidence JSON, native DRC, source/native/export XML;
- [ ] manufacturing ZIP, CAM/DFM reports и layer screenshots;
- [ ] фото Top/Bottom/микроскоп/размеры;
- [ ] таблицы continuity, rails, currents, static levels;
- [ ] raw scope captures и screenshots для SDA/SCL LV/HV;
- [ ] I²C logs с числом транзакций и ошибок;
- [ ] failure/rework/waiver ledger;
- [ ] датированный operator verdict и имя ответственного.

| Verdict | Условие | Результат |
| --- | --- | --- |
| `PASS-M1` | native refill/DRC/round-trip и визуальная проверка | `NATIVE PASS; operator checks pending` |
| `PASS-FAB` | точный пакет принят, полученная геометрия совпала | `___` |
| `PASS-HW` | C–F и 100-кГц G2 пройдены | `___` |
| `PASS-FM` | дополнительно пройден G3 на целевой нагрузке | `___` |

Общий базовый PASS возможен только при `PASS-M1 + PASS-FAB + PASS-HW` и без
необъяснённого waiver. `PASS-FM` не нужен для базового результата.

## 14. Короткий маршрут исполнения

1. ~~Закрыть PV-0: 4,7 кОм / `0402WGF4701TCE` / `C25900`.~~ Выполнено.
2. Выполнить оставшиеся operator checks M1 и заморозить commit при записанных SHA.
3. Выполнить фазу B и заказать минимальную первую партию.
4. После получения вести этот файл в режиме bring-up по одному пункту, начиная
   с фазы C; при любом стоп-условии не переходить дальше.
5. Завершить базовый PASS на 100 кГц; G3 делать только ради явного 400-кГц claim.
