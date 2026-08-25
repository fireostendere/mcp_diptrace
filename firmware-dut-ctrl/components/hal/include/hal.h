#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

/* Every actuator transitions to its hardware-safe state here. */
void hal_all_safe(void);

/* usb.data() interlock: only one port may be data-connected (shared uplink). */
typedef enum { USB_PORT_1 = 1, USB_PORT_2 = 2 } usb_port_t;

esp_err_t hal_usb_power(usb_port_t port, bool on);          /* SY6280 EN */
esp_err_t hal_usb_data(usb_port_t port, bool connect);      /* TS3USB221 OE/S */
esp_err_t hal_pwr(usb_port_t ch, bool on);                  /* P-FET gate */

typedef enum { SW_OPEN = 0, SW_CLOSED = 1 } sw_state_t;
esp_err_t hal_switch_set(int channel /*1..8*/, sw_state_t st);   /* PCA9539 */
esp_err_t hal_switch_press(int channel, uint32_t duration_ms);

typedef enum { UART_ROUTE_NORMAL = 0, UART_ROUTE_SWAPPED, UART_ROUTE_RX_ONLY, UART_ROUTE_OFF } uart_route_t;
esp_err_t hal_uart_route(int port /*1|2*/, uart_route_t r);

int hal_adc_read_mv(int ch0_7);                    /* ADS7830, 0..5000 mV scaled */
esp_err_t hal_current_read(int mon /*0..3*/, float *ma, float *mv);  /* INA226 */
