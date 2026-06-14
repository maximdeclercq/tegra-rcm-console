#ifndef CONF_H
#define CONF_H

/* TB_ prefix dodges arduino-pico's own USB_VID/PID macros. */

#define TB_USB_VID        0x1209
#define TB_USB_PID        0x0001
#define TB_USB_PRODUCT    "tegra-button"
#define SERIAL_IFACE_STR  "tegra-button serial"
#define JETSON_UART_BAUD  115200
#define CTRL_LINE_MAX     32

#endif /* CONF_H */
