# DUT Controller host protocol v1

JSON Lines over USB-CDC (115200-3M baud) or TCP :4242. One object per line.
UTF-8. Request ids are echoed; timestamps are device-monotonic microseconds.

## Requests / responses

```json
{"id":42,"cmd":"switch.press","channel":2,"duration_ms":100}
```
```json
{"id":42,"ok":true,"timestamp_us":427822103}
```
Errors:
```json
{"id":43,"ok":false,"error":{"code":"interlock","message":"USB1 data active"},"timestamp_us":...}
```

## Commands

| cmd | args | notes |
|---|---|---|
| `info.get` | – | fw version, caps bitmask, uptime |
| `usb.power` | port:1\|2, state:bool | SY6280 EN |
| `usb.data` | port, state:bool | interlocked; auto-disconnects sibling |
| `pwr.set` | ch:1\|2, state:bool | P-FET channel |
| `switch.set` | channel:1..8, state:0\|1 | PhotoMOS |
| `switch.press` | channel, duration_ms | blocking ≤10 s |
| `uart.route` | port:1\|2, route:normal\|swapped\|rx_only\|off | |
| `uart.write` | port, data_b64 | |
| `adc.read` | ch:0..7 | millivolts (divider-compensated on ext channels) |
| `ina.read` | mon:0..3 | {ma, mv} |
| `events.get` | since_us, max | batched event stream |
| `seq.run` | seq_id, ops[] | ops: {op:"delay",ms}\|{op:"switch",ch,state}\|{op:"usb.power",port,state}\|{op:"pwr",ch,state}\|{op:"uart.route",port,route}\|{op:"adc.read",ch}\|{op:"ina.read",mon} |
| `seq.cancel` | seq_id | |

Max 64 ops per sequence; deterministic delays from a 1 kHz tick; results and
every state change are appended to the event log.

## Events (async lines, no id)

```json
{"ev":"usb.power","port":1,"state":true,"ts":427822103}
{"ev":"sw","channel":2,"state":1,"ts":427822433}
{"ev":"adc","ch":2,"mv":3284,"ts":427823006}
{"ev":"uart","port":1,"bytes":14,"t0":427822201,"t1":427822209,"data_b64":"RVNQLVJPTTo="}
```
UART chunks aggregate idle-delimited bursts so boot-log correlation stays
within ~100 µs without per-byte overhead.
