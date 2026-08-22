# ATTINY85-20SU rules

Source: Microchip/Atmel, *ATtiny25/45/85 Datasheet*, 2586Q-AVR-08/2013:
https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/Atmel-2586-AVR-8-bit-Microcontroller-ATtiny25-ATtiny45-ATtiny85_Datasheet.pdf

- SOIC-8 pinout, Figure 1-1, PDF page 2: 1 PB5/RESET, 2 PB3, 3 PB4,
  4 GND, 5 PB0/MOSI, 6 PB1/MISO, 7 PB2/SCK, 8 VCC.
- Supply/speed grade, datasheet front page and section 21.3: non-V parts allow
  2.7–5.5 V and up to 10 MHz over that range. Therefore internal 8 MHz at
  +3.3 V is within the published operating area.
- ISP mapping, Table 20-10 on PDF page 151: MOSI=PB0, MISO=PB1, SCK=PB2;
  RESET is asserted for serial programming.
- C6 100 nF VCC decoupling and R7 10 kΩ external RESET pull-up are marked as
  general-practice choices, not values claimed from this datasheet.
- There is no hardware UART peripheral in this device. PB3/PB4 are a firmware
  software-UART allocation in this design.

