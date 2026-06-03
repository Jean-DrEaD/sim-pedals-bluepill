/* =====================================================================
   SIM PEDALS - STM32F103 (BluePill) - Roger Clark core + USBComposite
   ---------------------------------------------------------------------
   v1.0.0 - release:
     + bscale (escala ajustável do freio, -10..10, aceita negativo)
     + bzero/bfull por MEDIANA (robusto a picos de ruído)
     + proteção de range mínimo (evita saturação por bMax~bMin)
     Acelerador (hx) -> Joystick.X()       PA6
     Embreagem  (hy) -> Joystick.Y()       PA7
     Freio      (hb) -> Joystick.Xrotate() HX711 DT=PB4 SCK=PB3
     Botão      (b1) -> Joystick.button(1) PB5 (INPUT_PULLUP)
   ESCALA HID = 0..1023 (10 bits)
   ===================================================================== */

   // ---------------- FIRMWARE VERSION ----------------
#define FW_VERSION "1.0.0"

#include <USBComposite.h>
#include <EEPROM.h>
#include "HX711.h"

// ---------------- USB IDENTITY ----------------
#define USB_VID              0x1EAF
#define USB_PID              0x0024
#define USB_MANUFACTURER     "DrEaD SimGear"
#define USB_PRODUCT_NAME     "SIM Pedals"

// ---------------- PINOS ----------------
#define PIN_ACEL   PA6
#define PIN_EMBR   PA7
#define HX711_SCK  PB3
#define HX711_DT   PB4
#define PIN_BTN    PB5     // botão físico (INPUT_PULLUP)

// ---------------- ESCALA HID (10 bits) ----------------
#define HID_MAX    1023
#define LUT_N      32
#define HID_BTN    1       // número do botão no joystick

// ---------------- EEPROM ----------------
#define EE_MAGIC   0x5353   // struct v3.8 (+ bscale) — magic novo p/ migrar

// proteção: range mínimo do freio (em counts do HX711)
#define BRAKE_MIN_RANGE  20000UL

struct Config {
  uint16_t magic;
  uint16_t axMin, axMax;
  uint16_t ayMin, ayMax;
  uint32_t bMin, bMax;
  uint16_t dz;
  uint8_t  invx, invy, invb;
  float    ga;
  uint16_t emaMillis;
  uint8_t  useCurve;
  uint16_t lut[LUT_N];
  uint8_t  btnEn;          // habilita botão físico
  uint8_t  invBtn;         // inverte lógica do botão
  float    bscale;         // NOVO: escala do freio (-10..10)
};
Config cfg;

// ---------------- OBJETOS ----------------
USBHID HID;
HIDJoystick Joystick(HID);
USBCompositeSerial CompositeSerial;
HX711 scale;

// ---------------- ESTADO ----------------
int lastHx = -1, lastHy = -1, lastHb = -1;
int lastBtn = -1;
float emaAx = -1, emaAy = -1, emaBr = -1;

int  g_rawAx = 0, g_rawAy = 0;
long g_rawB  = 0;
int  g_hx = 0, g_hy = 0, g_hb = 0;
uint8_t g_btn = 0;
bool g_brakeOK = false;

// ---------- debounce do botão ----------
uint8_t  btnStable = 0;
uint8_t  btnRawPrev = 0;
unsigned long btnLastChange = 0;
const uint16_t BTN_DEBOUNCE_MS = 15;

// ---------------- TELEMETRIA ----------------
bool monitor = false;
const uint16_t DATA_INTERVAL_MS = 20; // 50 Hz
unsigned long lastData = 0;

// ---------------- PARSER ----------------
String inBuf = "";

// =====================================================================
// CONFIG DEFAULT / EEPROM
// =====================================================================
void lutLinear() {
  for (int i = 0; i < LUT_N; i++)
    cfg.lut[i] = (uint16_t)((long)i * HID_MAX / (LUT_N - 1));
}

void loadDefaults() {
  cfg.magic = EE_MAGIC;
  cfg.axMin = 410;   cfg.axMax = 3685;   // Hall 49E @ 3.3V (era 0/4095)
  cfg.ayMin = 410;   cfg.ayMax = 3685;   // Hall 49E @ 3.3V (era 0/4095)
  cfg.bMin  = 0;     cfg.bMax  = 1000000UL;
  cfg.dz    = 8;
  cfg.invx  = 0; cfg.invy = 0; cfg.invb = 0;
  cfg.ga    = 1.6f;
  cfg.emaMillis = 60;                     // padrão documentado (era 200)
  cfg.useCurve = 0;
  lutLinear();
  cfg.btnEn  = 1;
  cfg.invBtn = 0;
  cfg.bscale = 1.0f;     // escala neutra
}

void saveConfig() {
  uint16_t* p = (uint16_t*)&cfg;
  for (uint16_t i = 0; i < sizeof(Config)/2; i++) EEPROM.write(i, p[i]);
}

void loadConfig() {
  uint16_t* p = (uint16_t*)&cfg;
  for (uint16_t i = 0; i < sizeof(Config)/2; i++) p[i] = EEPROM.read(i);
  if (cfg.magic != EE_MAGIC) { loadDefaults(); saveConfig(); }
  // sanidade do bscale (caso lixo na flash)
  if (cfg.bscale < -10.0f || cfg.bscale > 10.0f || cfg.bscale == 0.0f)
    cfg.bscale = 1.0f;
}

// =====================================================================
// FUNÇÕES DE SINAL
// =====================================================================
float emaAlpha() { return cfg.emaMillis / 1000.0f; }

int applyEMA(int prev, int cur) {
  if (prev < 0) return cur;
  float a = emaAlpha();
  return (int)(prev + a * (cur - prev));
}

int applyDeadzoneFloor(int v, int dz) {
  if (v <= dz) return 0;
  return (int)((long)(v - dz) * HID_MAX / (HID_MAX - dz));
}

int applyLUT(int v) {
  if (v <= 0) return cfg.lut[0];
  if (v >= HID_MAX) return cfg.lut[LUT_N - 1];
  float pos = (float)v / HID_MAX * (LUT_N - 1);
  int i0 = (int)pos;
  if (i0 >= LUT_N - 1) return cfg.lut[LUT_N - 1];
  float fr = pos - i0;
  float out = cfg.lut[i0] + (cfg.lut[i0 + 1] - cfg.lut[i0]) * fr;
  if (out < 0) out = 0;
  if (out > HID_MAX) out = HID_MAX;
  return (int)out;
}

long readBrakeRaw() {
  if (scale.is_ready()) return scale.read_average(4);
  return g_rawB;
}

// mediana de N leituras — robusto a picos do HX711 (p/ bzero/bfull)
long readBrakeMedian(uint8_t n) {
  if (n < 3) n = 3;
  if (n > 15) n = 15;
  long buf[15];
  uint8_t got = 0;
  unsigned long t0 = millis();
  while (got < n && (millis() - t0) < 800) {
    if (scale.is_ready()) buf[got++] = scale.read();
  }
  if (got == 0) return g_rawB;
  // insertion sort
  for (uint8_t i = 1; i < got; i++) {
    long key = buf[i]; int j = i - 1;
    while (j >= 0 && buf[j] > key) { buf[j + 1] = buf[j]; j--; }
    buf[j + 1] = key;
  }
  return buf[got / 2];
}

// debounce: retorna estado lógico do botão (1 = pressionado, já com invBtn)
uint8_t readButton() {
  uint8_t raw = (digitalRead(PIN_BTN) == LOW) ? 1 : 0;
  if (raw != btnRawPrev) {
    btnRawPrev = raw;
    btnLastChange = millis();
  }
  if (millis() - btnLastChange >= BTN_DEBOUNCE_MS) {
    btnStable = raw;
  }
  uint8_t out = btnStable;
  if (cfg.invBtn) out = out ? 0 : 1;
  return out;
}

// =====================================================================
// TELEMETRIA / CFG
// =====================================================================
void printCfg() {
  CompositeSerial.print("CFG,");
  CompositeSerial.print(cfg.axMin); CompositeSerial.print(',');
  CompositeSerial.print(cfg.axMax); CompositeSerial.print(',');
  CompositeSerial.print(cfg.ayMin); CompositeSerial.print(',');
  CompositeSerial.print(cfg.ayMax); CompositeSerial.print(',');
  CompositeSerial.print(cfg.bMin);  CompositeSerial.print(',');
  CompositeSerial.print(cfg.bMax);  CompositeSerial.print(',');
  CompositeSerial.print(cfg.dz);    CompositeSerial.print(',');
  CompositeSerial.print(cfg.invx);  CompositeSerial.print(',');
  CompositeSerial.print(cfg.invy);  CompositeSerial.print(',');
  CompositeSerial.print(cfg.invb);  CompositeSerial.print(',');
  CompositeSerial.print(cfg.ga, 3); CompositeSerial.print(',');
  CompositeSerial.print(cfg.emaMillis); CompositeSerial.print(',');
  CompositeSerial.print(cfg.useCurve); CompositeSerial.print(',');
  CompositeSerial.print(cfg.btnEn);  CompositeSerial.print(',');
  CompositeSerial.print(cfg.invBtn); CompositeSerial.print(',');
  CompositeSerial.println(cfg.bscale, 3);   // NOVO campo no fim
}

void printCurve() {
  CompositeSerial.print("CURVE");
  for (int i = 0; i < LUT_N; i++) {
    CompositeSerial.print(',');
    CompositeSerial.print(cfg.lut[i]);
  }
  CompositeSerial.println();
}

void sendData() {
  if (!monitor) return;
  if (millis() - lastData < DATA_INTERVAL_MS) return;
  lastData = millis();

  CompositeSerial.print("DATA,");
  CompositeSerial.print(g_rawAx); CompositeSerial.print(',');
  CompositeSerial.print(g_rawAy); CompositeSerial.print(',');
  CompositeSerial.print(g_rawB);  CompositeSerial.print(',');
  CompositeSerial.print(g_hx);    CompositeSerial.print(',');
  CompositeSerial.print(g_hy);    CompositeSerial.print(',');
  CompositeSerial.print(g_hb);    CompositeSerial.print(',');
  CompositeSerial.println(g_btn);
}

// =====================================================================
// PARSER DE COMANDOS
// =====================================================================
void handleCurveCmd(String val) {
  int sp = val.indexOf(' ');
  if (sp < 0) return;
  int idx = val.substring(0, sp).toInt();
  String rest = val.substring(sp + 1);
  int count = 0;
  while (rest.length() && idx + count < LUT_N && count < 8) {
    rest.trim();
    int s2 = rest.indexOf(' ');
    String tok = (s2 < 0) ? rest : rest.substring(0, s2);
    int v = tok.toInt();
    if (v < 0) v = 0; if (v > HID_MAX) v = HID_MAX;
    cfg.lut[idx + count] = (uint16_t)v;
    count++;
    if (s2 < 0) break;
    rest = rest.substring(s2 + 1);
  }
}

void handleLine(String line) {
  line.trim();
  if (!line.length()) return;

  if (line == "l") {
    monitor = !monitor;
    CompositeSerial.print(">>> monitor ");
    CompositeSerial.println(monitor ? "ON" : "OFF");
    return;
  }
  if (line == "?")        { printCfg(); return; }
  if (line == "getcurve") { printCurve(); return; }
  if (line == "save") { saveConfig(); CompositeSerial.println(">>> saved");  return; }
  if (line == "load") { loadConfig(); CompositeSerial.println(">>> loaded"); printCfg(); return; }
  if (line == "def")  { loadDefaults(); CompositeSerial.println(">>> defaults"); printCfg(); return; }

  if (line == "bzero") {
    long r = readBrakeMedian(9);     // mediana robusta
    cfg.bMin = (uint32_t)r;
    CompositeSerial.print(">>> bMin = "); CompositeSerial.println(cfg.bMin);
    printCfg();
    return;
  }
  if (line == "bfull") {
    long r = readBrakeMedian(9);     // mediana robusta
    // proteção: garante range mínimo, evita freio "no talo"
    if ((uint32_t)r <= cfg.bMin + BRAKE_MIN_RANGE) {
      uint32_t corrigido = cfg.bMin + BRAKE_MIN_RANGE;
      CompositeSerial.print(">>> AVISO: bfull baixo, range forcado. bMax = ");
      CompositeSerial.println(corrigido);
      cfg.bMax = corrigido;
    } else {
      cfg.bMax = (uint32_t)r;
      CompositeSerial.print(">>> bMax = "); CompositeSerial.println(cfg.bMax);
    }
    printCfg();
    return;
  }
  if (line == "diag") {
    // mede pico-a-pico (P2P) de ~30 amostras de cada
    long bmin = 99999999, bmax = -99999999;
    for (int i = 0; i < 30; i++) {
      if (scale.is_ready()) { long v = scale.read(); if (v<bmin) bmin=v; if (v>bmax) bmax=v; }
    }
    CompositeSerial.print(">>> diag B: P2P="); CompositeSerial.println(bmax - bmin);
    return;
  }

  int sp = line.indexOf(' ');
  if (sp < 0) { CompositeSerial.println(">>> cmd?"); return; }
  String key = line.substring(0, sp);
  String val = line.substring(sp + 1); val.trim();

  if (key == "curve") { handleCurveCmd(val); return; }

  long  iv = val.toInt();
  float fv = val.toFloat();

  if      (key == "axMin")    cfg.axMin = iv;
  else if (key == "axMax")    cfg.axMax = iv;
  else if (key == "ayMin")    cfg.ayMin = iv;
  else if (key == "ayMax")    cfg.ayMax = iv;
  else if (key == "bMin")     cfg.bMin  = (uint32_t)iv;
  else if (key == "bMax")     cfg.bMax  = (uint32_t)iv;
  else if (key == "dz")       cfg.dz    = iv;
  else if (key == "invx")     cfg.invx  = iv ? 1 : 0;
  else if (key == "invy")     cfg.invy  = iv ? 1 : 0;
  else if (key == "invb")     { cfg.invb = iv ? 1 : 0; }
  else if (key == "ga")       cfg.ga    = fv;
  else if (key == "ema")      cfg.emaMillis = iv;
  else if (key == "usecurve") cfg.useCurve = iv ? 1 : 0;
  else if (key == "btnen")    cfg.btnEn  = iv ? 1 : 0;
  else if (key == "invbtn")   cfg.invBtn = iv ? 1 : 0;
  else if (key == "bscale") {                 // NOVO
    if (fv < -10.0f) fv = -10.0f;
    if (fv >  10.0f) fv =  10.0f;
    if (fv == 0.0f)  fv = 0.001f;             // nunca zero (evita divisão de sentido)
    cfg.bscale = fv;
  }
  else if (key == "btnpin")   { /* informativo: pino fixo PB5 */ }
  else { CompositeSerial.println(">>> chave?"); return; }

  CompositeSerial.print(">>> "); CompositeSerial.print(key);
  CompositeSerial.print(" = ");  CompositeSerial.println(val);
}

void readSerial() {
  while (CompositeSerial.available()) {
    char c = CompositeSerial.read();
    if (c == '\n' || c == '\r') {
      if (inBuf.length()) { handleLine(inBuf); inBuf = ""; }
    } else {
      inBuf += c;
      if (inBuf.length() > 96) inBuf = "";
    }
  }
}

// =====================================================================
// SETUP
// =====================================================================
void setup() {
  pinMode(PIN_ACEL, INPUT_ANALOG);
  pinMode(PIN_EMBR, INPUT_ANALOG);
  pinMode(PIN_BTN,  INPUT_PULLUP);
  scale.begin(HX711_DT, HX711_SCK);

  loadConfig();

  USBComposite.setVendorId(USB_VID);
  USBComposite.setProductId(USB_PID);
  USBComposite.setManufacturerString(USB_MANUFACTURER);
  USBComposite.setProductString(USB_PRODUCT_NAME);
  Joystick.setManualReportMode(true);

  HID.registerComponent();
  CompositeSerial.registerComponent();
  USBComposite.begin();

  CompositeSerial.print("SIM Pedals OK v");
  CompositeSerial.println(FW_VERSION);
}

// =====================================================================
// LOOP
// =====================================================================
void loop() {
  readSerial();

  int rawAx = analogRead(PIN_ACEL);
  int rawAy = analogRead(PIN_EMBR);

  static long rawB = 0;
  static bool brakeOK = false;
  if (scale.is_ready()) { rawB = scale.read(); brakeOK = true; }

  emaAx = applyEMA((int)emaAx, rawAx);
  emaAy = applyEMA((int)emaAy, rawAy);

  int hx = map(constrain((int)emaAx, cfg.axMin, cfg.axMax), cfg.axMin, cfg.axMax, 0, HID_MAX);
  int hy = map(constrain((int)emaAy, cfg.ayMin, cfg.ayMax), cfg.ayMin, cfg.ayMax, 0, HID_MAX);

  int hb;
  // proteção de range mínimo: evita saturação por bMax ~ bMin
  uint32_t bSpan = (cfg.bMax > cfg.bMin) ? (cfg.bMax - cfg.bMin) : 0;
  if (brakeOK && bSpan >= 1) {
    long bc = constrain(rawB, (long)cfg.bMin, (long)cfg.bMax);
    // normaliza 0..1 com bscale (escala/sentido ajustável)
    float norm = (float)(bc - (long)cfg.bMin) / (float)bSpan;
    norm *= cfg.bscale;
    if (norm < 0.0f) norm = 0.0f;
    if (norm > 1.0f) norm = 1.0f;
    int braw = (int)(norm * HID_MAX);
    emaBr = applyEMA((int)emaBr, braw);

    int bn = (int)emaBr;
    if (cfg.useCurve) hb = applyLUT(bn);
    else {
      float f = (float)bn / (float)HID_MAX;
      f = powf(f, cfg.ga);
      hb = (int)(f * HID_MAX);
    }
  } else hb = 0;

  hx = applyDeadzoneFloor(hx, cfg.dz);
  hy = applyDeadzoneFloor(hy, cfg.dz);

  if (cfg.invx) hx = HID_MAX - hx;
  if (cfg.invy) hy = HID_MAX - hy;
  if (cfg.invb) hb = HID_MAX - hb;

  hx = constrain(hx, 0, HID_MAX);
  hy = constrain(hy, 0, HID_MAX);
  hb = constrain(hb, 0, HID_MAX);

  uint8_t btn = cfg.btnEn ? readButton() : 0;

  bool mudou = false;
  if (hx != lastHx) { Joystick.X(hx);       lastHx = hx; mudou = true; }
  if (hy != lastHy) { Joystick.Y(hy);       lastHy = hy; mudou = true; }
  if (hb != lastHb) { Joystick.Xrotate(hb); lastHb = hb; mudou = true; }
  if ((int)btn != lastBtn) {
    Joystick.button(HID_BTN, btn ? true : false);
    lastBtn = btn; mudou = true;
  }
  if (mudou) Joystick.send();

  g_rawAx = rawAx; g_rawAy = rawAy; g_rawB = rawB;
  g_hx = hx; g_hy = hy; g_hb = hb; g_btn = btn; g_brakeOK = brakeOK;

  sendData();
}
