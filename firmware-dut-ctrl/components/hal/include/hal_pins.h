#pragma once
/* Single source of truth for the Rev.A pin map.
 * Mirrors docs/DUT_CONTROLLER_REVA_DESIGN.md section 3. */

#define PIN_I2C_SDA        2
#define PIN_I2C_SCL        4

#define PIN_UART1_POL      5
#define PIN_UART1_TXG      6
#define PIN_UART1_RXG      7
#define PIN_UART2_POL      13
#define PIN_UART2_TXG      14
#define PIN_UART2_RXG      15

#define PIN_USB1_OE        9    /* active-low enable, board PU100k = off */
#define PIN_USB1_S         10
#define PIN_USB2_OE        11
#define PIN_USB2_S         12

#define PIN_VBUS1_EN       16   /* SY6280 EN, PD100k = off */
#define PIN_VBUS2_EN       17
#define PIN_PWR1_EN        18   /* NPN gate driver, PD100k = off */
#define PIN_PWR2_EN        21

#define PIN_UART1_TXD      1    /* IO1 -> LVC1T45 A */
#define PIN_UART1_RXD      8    /* IO8 <- LVC1T45 A */
#define PIN_UART2_TXD      26
#define PIN_UART2_RXD      35

#define PIN_AUX1_IO1       33
#define PIN_AUX1_IO2       34
#define PIN_AUX1_IO3       32
#define PIN_AUX1_IO4       36
#define PIN_AUX2_IO1       37
#define PIN_AUX2_IO2       38
#define PIN_AUX2_IO3       47
#define PIN_AUX2_IO4       48   /* shares JTAG MTMS header pin */

#define PIN_LED_STATUS     -1   /* driven by PCA9539 IO1_7 over I2C */

/* PCA9539 @0x77: O0.0..O0.7 = PhotoMOS SW1..SW8 (reset=input => OPEN) */
#define I2C_ADDR_PCA9539   0x77
#define I2C_ADDR_ADS7830   0x48
/* INA226 addresses: USB1=0x40 USB2=0x41 PWR1=0x42 PWR2=0x43 */
