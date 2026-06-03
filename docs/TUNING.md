# Ajuste Fino — SIM Pedals Blue Pill

## EMA (Filtro de Suavização)

O firmware usa um filtro **EMA (Exponential Moving Average)** para suavizar as leituras brutas dos sensores.

### Parâmetro `ema`

- Conceito: **fator de suavização** (NÃO é tempo em milissegundos)
- Faixa: 1 – 1000
- Relação: `alpha = ema / 1000` aplicado em `y = y + alpha*(x - y)`
- **Padrão: 60** (alpha = 0.06 — bom balanço entre resposta e filtragem)

> **Atenção à direção:** `ema` **menor** → alpha menor → filtra **mais** → resposta
> mais **suave/lenta** (mais lag). `ema` **maior** → filtra **menos** → resposta
> mais **rápida** (menos lag, deixa passar mais ruído).

| `ema` | alpha | Comportamento | Quando usar |
|-------|-------|--------------|-------------|
| 20–40 | 0.02–0.04 | Muito suave, filtra forte, lag perceptível | Freio/sensor muito ruidoso |
| 60 | 0.06 | **Padrão** — bom para a maioria | Uso geral |
| 100–200 | 0.10–0.20 | Mais responsivo, filtra menos | Sensores limpos / hardware bom |
| 300+ | 0.30+ | Quase cru, pouca filtragem | Não recomendado |

> **Regra prática:** comece com o padrão (60). Se ver oscilação em repouso no
> osciloscópio, **diminua** para 30–40 (mais filtragem). Se sentir lag e o sinal
> for limpo, **aumente** para 100–150.

#### Aplicação por eixo

A GUI aplica o mesmo `ema` para os três eixos (acelerador, embreagem e freio).
O firmware v1.0.0 usa EMA uniforme. Para ajuste independente por eixo,
seria necessário expandir o protocolo (planejado para versões futuras).

---

## Curva Gamma

> Para load cells (freio): **1.6–2.0** é o mais comum em sim racing.  
> Para os eixos Hall 49E (acelerador/embreagem) a resposta já é linear por hardware — o gamma do firmware atua apenas no **freio**.

### Fórmula

```saída = (entrada / 1023)^ga × 1023```

```
| `ga` | Curva | Sensação |
|------|-------|---------|
| 0.5 | Muito côncava | Muito sensível no início |
| 1.0 | Linear | Sem curva — 1:1 |
| **1.6** | **Levemente convexa** | **Padrão — ideal para load cell** |
| 2.0–2.5 | Convexa média | Mais força necessária para acionar |
| 3.0–5.0 | Muito convexa | Morder muito no final do curso — uso extremo |
```

> Para load cells: **1.6–2.0** é o mais comum em sim racing.  
> Para potenciômetros: **1.0** (linear) costuma ser o melhor.

---

## LUT (Look-Up Table) — Curva Personalizada

A LUT de 32 pontos substitui o gamma, permitindo **qualquer forma de curva**.

### Quando usar LUT

- Você quer uma curva em S (suave no início, forte no meio, suave no fim)
- Você quer compensar comportamento não-linear da sua load cell
- Você quer experimentar curvas que o gamma não cobre

### Como usar na GUI

1. Abra a aba **Curva do Freio**
2. Arraste os **pontos vermelhos** para moldar a curva
3. Use os presets como ponto de partida:
   - **Linear** — equivale a gamma 1.0
   - **Progressiva** — equivale a gamma ~1.6
   - **Agressiva** — muito sensível no início (gamma <1)
   - **S-curve** — suave-agressivo-suave
4. Marque **Ativar curva no firmware** para usar a LUT
5. Clique **Enviar curva** e **Salvar EEPROM**

> A linha azul no editor mostra a força atual do freio (Monitor ON).

---

## Deadzone (`dz`)

A deadzone evita que valores de ruído em repouso sejam reportados como movimento.

**Comportamento:** valores ≤ dz viram 0. Acima, o range é reescalado para manter resolução completa (sem "pulo" no primeiro valor acima da dz). A deadzone é aplicada nos **3 eixos** (acelerador, embreagem e freio).

| `dz` | Quando usar |
|------|-------------|
| 0 | Sem deadzone — sinal muito limpo |
| 8 (padrão) | Boa para a maioria dos casos |
| 15–25 | Load cell ruidosa em repouso |
| 50+ | Problemas severos de ruído (investigue a causa) |

> A tara do freio (`bzero`) é o primeiro ajuste — ela zera o offset do sensor. Use `dz` para suprimir o ruído residual que permanece mesmo após a tara.
> Para o acelerador e embreagem em bom estado, `dz 5–8` é geralmente suficiente.

---

## Diagnóstico de Ruído

Use o **Osciloscópio** (aba Osciloscópio, Monitor ON) para observar o ruído:

1. **Deixe todos os pedais em repouso** (não toque)
2. Observe se as linhas ficam estáveis ou oscilam
3. Para uma leitura quantitativa, deixe os pedais em repouso e observe a linha no osciloscópio — a variação peak-to-peak no repouso é o ruído a gerenciar

| Resultado P2P | Qualidade | Ação |
|--------------|-----------|------|
| < 5 | Excelente | Nenhuma |
| 5–15 | Bom | `dz 8` (padrão) é suficiente |
| 15–50 | Regular | `ema 40` + `dz 15` |
| > 50 | Ruim | Verificar GND / alimentação / blindagem dos fios |

---

## Tabela completa de parâmetros

| Parâmetro | Faixa | Padrão | Descrição |
|-----------|-------|--------|-----------|
| `ga` | 0.2 – 5.0 | 1.6 | Curva gamma do freio |
| `ema` | 1 – 1000 | 60 | Fator de suavização EMA (alpha = ema/1000; menor = mais suave/lento) |
| `dz` | 0 – 200 | 8 | Deadzone em unidades HID |
| `usecurve` | 0 / 1 | 0 | 0 = gamma, 1 = LUT |
| `invx` | 0 / 1 | 0 | Inverte acelerador |
| `invy` | 0 / 1 | 0 | Inverte embreagem |
| `invb` | 0 / 1 | 0 | Inverte freio |
| `btnen` | 0 / 1 | 1 | Habilita botão físico |
| `invbtn` | 0 / 1 | 0 | Inverte lógica do botão |

---

## Perfis sugeridos para sim racing

| Estilo | `ga` | `ema` | `dz` | Notas |
|--------|------|-------|------|-------|
| GT / Endurance | 1.6 | 60 | 8 | Padrão — modulação progressiva |
| F1 / Open Wheel | 2.0 | 100 | 5 | Freio mais difícil, resposta rápida |
| Rally | 1.2 | 40 | 12 | Mais linear, suaviza vibrações |
| Oval / NASCAR | 1.8 | 60 | 8 | Similar ao GT |
| Drift | 0.8 | 100 | 5 | Muito sensível no início, resposta rápida |

Salve cada configuração como um perfil `.json` na aba **Perfis**.
