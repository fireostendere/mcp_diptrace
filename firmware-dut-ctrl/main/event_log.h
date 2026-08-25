#pragma once
#include <stdint.h>
#include <stddef.h>

/* Monotonic microsecond timestamp + structured event stream.
 * UART RX chunks are timestamped on DMA-idle detection so boot logs align
 * with power/button events to ~100 us. */

void event_log_init(void);
uint64_t event_now_us(void);
void event_log_printf(const char *fmt, ...);

/* Batched retrieval for the host: returns up to max bytes, advances cursor. */
size_t event_log_read(char *out, size_t max);

/* UART capture: per-port ring buffer with idle-line timestamps. */
void uart_capture_push(int port, const uint8_t *data, size_t len, uint64_t ts_us);
typedef struct {
    uint8_t data[256];
    size_t len;
    uint64_t first_ts_us;
    uint64_t last_ts_us;
} uart_chunk_t;
bool uart_capture_pop(int port, uart_chunk_t *out);
