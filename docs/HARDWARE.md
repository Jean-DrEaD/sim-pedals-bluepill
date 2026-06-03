# Hardware Setup — SIM Pedals Blue Pill

## BOM (Lista de Materiais)

| Item | Qtd | Notas |
|------|-----|-------|
| STM32F103C8T6 (Blue Pill) | 1 | Clone funciona; verifique se tem 64KB ou 128KB de flash |
| Sensor Hall 49E (linear) | 2 | Acelerador + Embreagem — saída analógica linear |
| Célula de carga | 1 | 100 kg recomendado para pedaleira |
| Módulo HX711 | 1 | Amplificador da load cell |
| Switch momentâneo | 1 | Botão físico HID (opcional) |
| Fios dupont / jumpers | — | Para prototipagem |
| Boot jumper | 1 | Para gravar firmware (já incluso na placa) |

## Diagrama de Ligação

Veja [`docs/images/wiring.svg`](./images/wiring.svg) para o diagrama completo.

## Pinagem

| Função | Pino Blue Pill | Tipo | Detalhes |
|--------|----------------|------|----------|
| Acelerador | **PA6** | INPUT_ANALOG | ADC1_IN6 · 0–3.3V · Sensor Hall 49E |
| Embreagem | **PA7** | INPUT_ANALOG | ADC1_IN7 · 0–3.3V · Sensor Hall 49E |
| HX711 DT (DOUT) | **PB4** | INPUT | Data da load cell |
| HX711 SCK | **PB3** | OUTPUT | Clock da load cell |
| Botão HID | **PB5** | INPUT_PULLUP | Switch entre PB5 e GND |

## Diagrama físico do Blue Pill

```
                         ┌───────────────────────────┐
                         │     USB Micro-B ou C      │
                    GND  │ GND              GND ●    │
                    3.3V │ 3.3V             GND ●    │
                    5V   │ 5V              NRST ●    │
                    PA0  │ A0              PB11 ●    │
                    PA1  │ A1              PB10 ●    │
                    PA2  │ A2              PB1  ●    │
                    PA3  │ A3              PB0  ●    │
                    PA4  │ A4              PA7  ● ── Embreagem (Hall 49E OUT)
                    PA5  │ A5              PA6  ● ── Acelerador (Hall 49E OUT)
  HX711 SCK ─────── PB3  │ B3              PA5  ●    │
  HX711 DT ──────── PB4  │ B4              PA4  ●    │
  Botão HID ─────── PB5  │ B5              PA3  ●    │
                    PB6  │ B6              PA2  ●    │
                    PB7  │ B7              PA1  ●    │
                    PB8  │ B8              PA0  ●    │
                    PB9  │ B9   [STM32]   PC15  ●    │
                    5V   │ 5V             PC14  ●    │
                    GND  │ GND            PC13  ●    │
                    3.3V │ 3.3V           VBAT  ●    │
                         └───────────────────────────┘
                                  [BOOT0] [BOOT1]
```

> **Para gravação de firmware:** coloque BOOT0 = HIGH (jumper em 1) antes de conectar o USB. Após gravar, retorne BOOT0 = LOW (jumper em 0) e reconecte.

## Sensores Hall 49E (Acelerador e Embreagem)

O Hall 49E é um sensor de efeito Hall de saída analógica linear. Diferente de um potenciômetro, ele não tem contato mecânico e responde à posição de um ímã acoplado ao eixo do pedal.

### Pinagem do Hall 49E

O sensor possui **3 pinos**:

| Pino | Função | Conectar em |
|------|--------|-------------|
| 1 (VCC) | Alimentação | **3.3V** do Blue Pill |
| 2 (GND) | Terra | GND do Blue Pill |
| 3 (OUT) | Saída analógica | **PA6** (acelerador) ou **PA7** (embreagem) |

> ⚠️ Use **3.3V**, não 5V. O ADC do STM32F103 aceita no máximo 3.6V.

### Ligação

```
  3.3V ─── VCC  (pino 1 do Hall 49E)
  GND  ─── GND  (pino 2 do Hall 49E)
  PA6  ─── OUT  (pino 3 do Hall 49E — acelerador)

  3.3V ─── VCC  (pino 1 do Hall 49E)
  GND  ─── GND  (pino 2 do Hall 49E)
  PA7  ─── OUT  (pino 3 do Hall 49E — embreagem)
```

> Nenhum resistor pull-up externo é necessário — a saída do Hall 49E já é de baixa impedância.

### Range de saída esperado

Alimentado com 3.3V, o Hall 49E produz:

| Posição do ímã | Tensão OUT | ADC (0–4095) |
|----------------|-----------|--------------|
| Curso mínimo (repouso) | ~0.33 V | ~410 |
| Centro / neutro | ~1.65 V | ~2048 |
| Curso máximo (fundo) | ~2.97 V | ~3685 |

> Os defaults de firmware já refletem esse range (`axMin=410`, `axMax=3685`).  
> Sempre recalibre com **Auto-Cal** na GUI após montar o pedal — o range exato varia com a distância do ímã ao sensor.

### Dicas de montagem

- Posicione o ímã (neodímio, 6–10 mm de diâmetro) alinhado radialmente ao sensor
- A distância ideal entre ímã e face do sensor é **1–3 mm**
- Sensores Hall não sofrem desgaste mecânico — ideal para pedaleiras de alta durabilidade

## Módulo HX711 — Load Cell

### Ligação HX711 → Blue Pill

| Pino HX711 | Conectar em |
|-----------|-------------|
| GND | GND |
| DT | PB4 |
| SCK | PB3 |
| VCC | 5V (recomendado — melhor SNR) |

> O módulo HX711 tem regulador interno — alimentar com 5V melhora a relação sinal/ruído da célula de carga.

### Ligação Célula de Carga → HX711

| Fio (cor típica) | Pino HX711 |
|-----------------|-----------|
| Vermelho (E+) | E+ |
| Preto (E−) | E− |
| Verde (A+) | A+ |
| Branco (A−) | A− |
| Amarelo (Shield, se houver) | E− ou GND |

> Se as leituras forem **invertidas** (freio diminui ao pressionar), troque A+ por A−, ou use o botão **invb** na GUI.

### HX711 a 80 Hz (opcional)

O padrão de fábrica opera a **10 Hz**. Para máxima taxa de atualização:

1. Localize o pino RATE (15) do CI HX711 no módulo
2. Corte a trilha que o conecta ao GND
3. Conecte RATE ao VCC do HX711 (3.3V ou 5V do módulo)

**Com a biblioteca padrão a 10 Hz, o firmware ainda opera suavemente** graças à filtragem EMA. A modificação é opcional.

## Botão Físico HID (opcional)

Conecte um switch momentâneo entre **PB5** e **GND**. O firmware usa INPUT_PULLUP — nenhum resistor externo é necessário.

- Solto = não pressionado (HIGH)
- Pressionado = pressionado (LOW)
- Use **invbtn** na GUI se quiser inverter a lógica

## Alimentação

| Componente | Tensão | Pino de alimentação |
|------------|--------|---------------------|
| Blue Pill | 5V via USB | — |
| Sensores Hall 49E | 3.3V | Pino 3.3V do Blue Pill |
| HX711 | 5V | Pino 5V do Blue Pill |
| GND | Comum | GND do Blue Pill |

> ⚠️ **GND comum é obrigatório.** Conecte o GND do HX711 e dos sensores Hall ao mesmo GND da Blue Pill para evitar flutuação nas leituras.
