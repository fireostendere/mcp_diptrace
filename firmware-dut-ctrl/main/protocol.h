#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#define PROTOCOL_VERSION 1
#define MAX_SEQ_OPS 64

typedef struct {
    uint32_t id;
    char cmd[40];
    /* generic small args */
    int channel;        /* port / channel / adc ch */
    int state;          /* bool or enum value */
    int duration_ms;
    int seq_id;
} request_t;

typedef void (*cmd_handler_t)(const request_t *req);

void protocol_init(void);
/* Feed one received line (without newline). Reply is written to active transport. */
void protocol_handle_line(const char *line, size_t len);

/* --- sequence engine ------------------------------------------------------ */
typedef enum {
    SEQ_OP_DELAY = 0,
    SEQ_OP_SWITCH,
    SEQ_OP_USB_POWER,
    SEQ_OP_USB_DATA,
    SEQ_OP_PWR,
    SEQ_OP_UART_ROUTE,
    SEQ_OP_ADC_READ,   /* logs result as event */
    SEQ_OP_CURRENT_READ,
} seq_op_kind_t;

typedef struct {
    seq_op_kind_t kind;
    int a;              /* channel/port/op-specific */
    int b;              /* state/value */
    uint32_t ms;        /* delay duration */
} seq_op_t;

typedef struct { int running; int seq_id; size_t idx; size_t len; seq_op_t ops[MAX_SEQ_OPS]; } sequence_t;

esp_err_t sequence_start(int seq_id, const seq_op_t *ops, size_t n);
void sequence_cancel(int seq_id);
bool sequence_tick(void);   /* call from a 1ms task; returns true when any active */
