#include <Adafruit_TinyUSB.h>
#include <Arduino.h>

#include "conf.h"
#include "pins.h"
#include "wire.h"

/* Two USB CDC: the button channel is the core Serial (CDC 0) and drives the J14
   lines; the serial channel is cons (CDC 1), bridged to the Jetson UART. */
static Adafruit_USBD_CDC cons;

// clang-format off
static void pin_assert(uint8_t pin)        { digitalWrite(pin, LOW); pinMode(pin, OUTPUT); }
static void pin_release(uint8_t pin)       { pinMode(pin, INPUT); }
static void pin_drive(uint8_t pin, bool on){ if (on) pin_assert(pin); else pin_release(pin); }
static void power_setv(bool on)            { digitalWrite(PIN_POWER, on ? HIGH : LOW); }
// clang-format on

static void button_write(const char *s) {
  Serial.write((const uint8_t *)s, strlen(s));
  Serial.write((const uint8_t *)"\r\n", 2);
  Serial.flush();
}

/* Apply one "<line>=<0|1>" token. recov/reset are open-drain (assert = drive low,
   release = hi-Z); power is push-pull through the BJT. */
static void button_apply(char *tok) {
  char *eq = strchr(tok, '=');
  if (!eq || eq[2] != '\0' || (eq[1] != '0' && eq[1] != '1')) {
    button_write(REP_ERR);
    return;
  }
  const bool on = (eq[1] == '1');
  *eq           = '\0';
  if (strcmp(tok, WIRE_RECOV) == 0)
    pin_drive(PIN_RECOV, on);
  else if (strcmp(tok, WIRE_RESET) == 0)
    pin_drive(PIN_RESET, on);
  else if (strcmp(tok, WIRE_POWER) == 0)
    power_setv(on);
  else {
    button_write(REP_ERR);
    return;
  }
  button_write(REP_OK);
}

/* Tokens are runs of printable non-space chars; any space or control byte
   delimits, so a newline ends a command. */
static void button_pump(void) {
  static char   tok[CTRL_LINE_MAX];
  static size_t len = 0;
  while (Serial.available()) {
    const int c = Serial.read();
    if (c < 0)
      break;
    if (c > 0x20 && c < 0x7F) {
      if (len < CTRL_LINE_MAX - 1)
        tok[len++] = (char)c;
    } else if (len > 0) {
      tok[len] = '\0';
      button_apply(tok);
      len = 0;
    }
  }
}

static void serial_pump(void) {
  while (cons.available() && Serial1.availableForWrite()) {
    const int b = cons.read();
    if (b < 0)
      break;
    Serial1.write((uint8_t)b);
  }
  while (Serial1.available()) {
    const int b = Serial1.read();
    if (b < 0)
      break;
    if (cons.availableForWrite() > 0)
      cons.write((uint8_t)b);
  }
  cons.flush();
}

static void pin_init(void) {
  pin_release(PIN_RECOV);
  pin_release(PIN_RESET);
  digitalWrite(PIN_POWER, LOW);
  pinMode(PIN_POWER, OUTPUT);
}

static void usb_begin(void) {
  USBDevice.setID(TB_USB_VID, TB_USB_PID);
  USBDevice.setProductDescriptor(TB_USB_PRODUCT);
  Serial.begin(115200);
  cons.setStringDescriptor(SERIAL_IFACE_STR);
  cons.begin(115200);
}

void setup(void) {
  pin_init();
#if defined(ARDUINO_ARCH_RP2040)
  Serial1.setTX(PIN_SERIAL_TX);
  Serial1.setRX(PIN_SERIAL_RX);
#endif
  Serial1.begin(JETSON_UART_BAUD);
  usb_begin();
}

void loop(void) {
  button_pump();
  serial_pump();
}
