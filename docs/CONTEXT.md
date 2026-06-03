# 📌 Contexto do Projeto — SIM Pedals BluePill

> Documento de contexto técnico para desenvolvimento e manutenção.
> **Versão atual: 1.0.0**

---

## 🎯 Objetivo

Pedaleira USB HID para simuladores, baseada em STM32 BluePill (F103C8),
com freio por célula de carga (HX711) e acelerador/embreagem analógicos.

---

## 🧱 Arquitetura

- **Firmware** (`src/sim_pedals/sim_pedals.ino`):
  - Leitura HX711 (freio) + ADC (acelerador/embreagem).
  - Processamento: zero/escala → `bscale` → curva (gamma/LUT) → EMA → deadzone.
  - Saída USB HID (joystick com 3 eixos).
  - Protocolo serial de configuração + persistência em EEPROM.
- **GUI** (`gui/pedals_gui.py`):
  - Monitor ao vivo, auto-calibração, editor de curva, osciloscópio.
  - Comunicação em **thread separada** com **debounce de 150 ms**.
  - Perfis em `.json`.

---

## 🔧 Subsistema de Freio (load cell)

### Pipeline de processamento
```
HX711 raw → (raw - bMin) / (bMax - bMin) → aplica bscale → curva → EMA → deadzone → HID
```

### Calibração robusta
- `bzero` / `bfull` usam **mediana de 9 leituras** (substituiu `read_average(4)`)
  para reduzir ruído na captura dos extremos.
- **Proteção de range mínimo**: `bMax` é forçado a ser
  `≥ bMin + BRAKE_MIN_RANGE` (**20.000 counts**), evitando saturação precoce
  ("freio no talo" / leitura grudada em 1023).

### Parâmetro `bscale`
- Faixa: **-10 a 10**.
- Ajusta **sensibilidade** e **sentido** (inversão) do freio.
- Valores típicos para reduzir sensibilidade: **0.6 – 0.8**.
- Persistido em EEPROM.

### Diagnóstico
- Comando `diag` mede **pico a pico (P2P)** das leituras do HX711,
  útil para validar ruído e definir bom range de calibração.

---

## 💾 EEPROM

- `EE_MAGIC = 0x5353`.
- ⚠️ Alteração do magic invalida layouts antigos: na **primeira inicialização
  após o flash**, a placa **regrava os defaults**.
  → Necessário **recalibrar** (`bzero`/`bfull`) ou **carregar perfil** pela GUI.
- Campos persistidos: `bMin`, `bMax`, `bscale`, `gamma`, `ema`, `dz`, flags de
  inversão, LUT (32 pontos), `usecurve`.

---

## 🖥️ GUI — pontos de atenção

- Envio da **curva LUT** e comandos roda em **thread separada** com
  **debounce de 150 ms** (evita travamentos da UI).
- Controle de `bscale`: **slider de -3 a +3**, **presets** (0, +1, -1) e
  **spinbox** para ajuste rápido.

---

## 🗺️ Mapa de arquivos

| Caminho                       | Conteúdo                              |
| ----------------------------- | ------------------------------------- |
| `src/sim_pedals/sim_pedals.ino` | Firmware principal                  |
| `gui/pedals_gui.py`           | Aplicação GUI                         |
| `include/config.h.example`    | Template de configuração              |
| `docs/CALIBRATION.md`         | Procedimento de calibração            |
| `docs/TUNING.md`              | Ajuste fino (`bscale`, curvas)        |
| `docs/HARDWARE.md`            | Pinagem e montagem                    |
| `ci/libraries.txt`            | Dependências de build (CI)            |

---

## 🔄 Histórico relevante (1.0.0)

- Mediana de 9 leituras em `bzero`/`bfull`.
- Proteção de range mínimo (20k counts).
- Reintrodução do parâmetro `bscale` (-10 a 10).
- `diag` com medição P2P.
- GUI: thread + debounce 150 ms, controle de `bscale`.
- `EE_MAGIC` → `0x5353`.
