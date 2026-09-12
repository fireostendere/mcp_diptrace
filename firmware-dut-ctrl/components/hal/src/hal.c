#include "hal.h"
#include "hal_pins.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"

/* All control lines idle LOW except USB_OE (idles HIGH=disabled).
 * Hardware pulls guarantee these states at reset; we mirror them in FW. */

static bool s_usb_data_connected[3] = { false, false, false };

void hal_all_safe(void)
{
    gpio_reset_pin(PIN_USB1_OE); gpio_set_direction(PIN_USB1_OE, GPIO_MODE_OUTPUT); gpio_set_level(PIN_USB1_OE, 1);
    gpio_reset_pin(PIN_USB2_OE); gpio_set_direction(PIN_USB2_OE, GPIO_MODE_OUTPUT); gpio_set_level(PIN_USB2_OE, 1);
    const int outs_off[] = { PIN_USB1_S, PIN_USB2_S, PIN_VBUS1_EN, PIN_VBUS2_EN,
                             PIN_PWR1_EN, PIN_PWR2_EN,
                             PIN_UART1_POL, PIN_UART1_TXG, PIN_UART1_RXG,
                             PIN_UART2_POL, PIN_UART2_TXG, PIN_UART2_RXG };
    for (unsigned i = 0; i < sizeof(outs_off) / sizeof(outs_off[0]); i++) {
        gpio_reset_pin(outs_off[i]);
        gpio_set_direction(outs_off[i], GPIO_MODE_OUTPUT);
        gpio_set_level(outs_off[i], 0);
    }
    /* PhotoMOS LEDs are driven by PCA9539; its registers reset to inputs. */
    s_usb_data_connected[1] = s_usb_data_connected[2] = false;
}

static esp_err_t pca_write(uint8_t reg, uint8_t val)
{
    /* TODO: i2c_master transmit to I2C_ADDR_PCA9539; skeleton keeps signature */
    (void)reg; (void)val;
    return ESP_OK;
}

esp_err_t hal_switch_set(int channel, sw_state_t st)
{
    if (channel < 1 || channel > 8) return ESP_ERR_INVALID_ARG;
    /* Output register IO0: bit=1 => LED sink OFF (PhotoMOS OPEN).
     * Configure as output-low to CLOSE (LED current flows). */
    uint8_t bit = channel - 1;
    /* TODO: read-modify-write PCA9539 OUTPUT_PORT0 + CONFIG_PORT0 */
    return pca_write(0x02, st == SW_CLOSED ? 0 : (1u << bit)); /* placeholder */
}

esp_err_t hal_switch_press(int channel, uint32_t duration_ms)
{
    esp_err_t err = hal_switch_set(channel, SW_CLOSED);
    if (err != ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(duration_ms));
    event_log_printf("%lu SW%d OPEN", (unsigned long)esp_timer_get_time(), channel);
    return hal_switch_set(channel, SW_OPEN);
}

esp_err_t hal_usb_data(usb_port_t port, bool connect)
{
    if (connect && s_usb_data_connected[1] && port != USB_PORT_1 &&
        s_usb_data_connected[port == USB_PORT_1 ? 2 : 1]) {
        return ESP_ERR_INVALID_STATE;   /* interlock */
    }
    int oe = (port == USB_PORT_1) ? PIN_USB1_OE : PIN_USB2_OE;
    int sel = (port == USB_PORT_1) ? PIN_USB1_S : PIN_USB2_S;
    gpio_set_level(sel, 0);             /* select uplink source */
    gpio_set_level(oe, connect ? 0 : 1);
    s_usb_data_connected[port] = connect;
    if (!connect) return ESP_OK;
    /* disconnect the sibling port (shared uplink pair) */
    usb_port_t other = (port == USB_PORT_1) ? USB_PORT_2 : USB_PORT_1;
    gpio_set_level(other == USB_PORT_1 ? PIN_USB1_OE : PIN_USB2_OE, 1);
    s_usb_data_connected[other] = false;
    return ESP_OK;
}
