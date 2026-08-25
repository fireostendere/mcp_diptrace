# DUT Controller Rev.A — firmware skeleton (ESP-IDF)

Target: ESP32-S3-MINI-1U-N8, ESP-IDF >= 5.x.

```
idf.py set-target esp32s3
idf.py build flash monitor
```

Transport: USB-CDC (native USB-Serial-JTAG) and optional Wi-Fi TCP server on
port 4242 with the same framed protocol.

## Layout

| File | Role |
|---|---|
| `main/protocol.h/.c` | framed JSON-lines protocol: request id, ok/error, timestamp_us |
| `main/event_log.h/.c` | monotonic event log + UART RX ring buffers with timestamps |
| `main/sequence_engine.h/.c` | local deterministic op sequences (delay/cancel/timeout) |
| `components/hal` | hal_power, hal_usb_switch, hal_switch, hal_uart, hal_gpio, hal_adc, hal_current |

Pin map is the single source of truth in `components/hal/include/hal_pins.h`
and mirrors docs/DUT_CONTROLLER_REVA_DESIGN.md §3. Every actuator line has a
hardware pull to its safe state; firmware additionally drives all outputs to
safe levels in `hal_all_safe()` called from app_main start and from a panic
handler hook.
