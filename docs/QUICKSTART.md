# Início Rápido — SIM Pedals Blue Pill

> Tempo estimado: **10 minutos** do zero até os pedais funcionando.

---

## Antes de começar

Você vai precisar de:
- Blue Pill (STM32F103C8) já conectada via USB ao PC
- Python 3.8+ instalado
- Firmware gravado na placa (veja o README principal)

---

## 1. Instalar a GUI

Abra um terminal e execute:

```bash
pip install pyserial
python gui/pedals_gui.py
```

A janela do SIM Pedals abrirá com o tema escuro.

---

## 2. Conectar à placa

1. Na seção **Conexão** (topo), clique em **↻** para atualizar as portas disponíveis
2. A Blue Pill aparece como `COM?  ★` no Windows (ou `/dev/ttyACM0` no Linux) — a estrela ★ indica auto-detecção
3. Selecione a porta e clique **Conectar**
4. A GUI envia `?` e `getcurve` automaticamente — você verá `CFG,...` no log
5. Clique **Monitor OFF** → vira **Monitor ON** para iniciar a telemetria em tempo real

---

## 3. Calibrar o freio (mais importante!)

O freio usa uma **load cell** (célula de carga). Antes de usar, é preciso dizer ao firmware o que é "solto" e o que é "fundo".

### Por que o freio parece supersensível logo de início?

O bMin e bMax padrão são `0` e `1.000.000`. Como a load cell raramente chega a esses extremos, qualquer pressão vira um valor alto. **A calibração resolve isso.**

### Procedimento

1. **Solte completamente** o pedal de freio (não toque nele)
2. Clique em **⊘ Tara/Zero (bMin)** — o firmware captura o valor atual como zero
3. **Pise o freio até o fim** com a força máxima que usará normalmente
4. Clique em **⛂ Pisar fundo (bMax)** — confirme na caixa de diálogo
5. **Agora** pressione o freio suavemente: a barra HID deve subir progressivamente

> **Dica:** Use o osciloscópio (aba Osciloscópio, Monitor ON) para observar a linha amarela (Xrot freio) enquanto calibra. Ela deve subir quando você pisa e cair ao soltar.

### O freio está indo na direção errada?

Se a barra **cai** ao pisar (em vez de subir):

1. Marque a caixa **invb** na seção "Inversões de eixo"
2. A GUI envia o comando automaticamente
3. Teste novamente — agora deve subir

### Salvar a calibração

Clique **Salvar EEPROM** (seção Configuração). A calibração persiste mesmo após desligar.

---

## 4. Calibrar acelerador e embreagem

1. Clique em **▶ Iniciar auto-cal**
2. Mova o acelerador do fim de curso ao máximo e de volta
3. Faça o mesmo com a embreagem
4. Clique **■ Parar e aplicar** — os limites são aplicados com margem de 2%
5. Clique **Salvar EEPROM**

---

## 5. Verificar no jogo

Abra o Painel de Controle do Windows → **Controladores de jogo** → **SIM Pedals** → Propriedades.

Você deve ver:
- **Eixo X** → Acelerador
- **Eixo Y** → Embreagem
- **Eixo Xrotate** → Freio

No simulador (Assetto Corsa, iRacing, etc.), mapeie cada eixo normalmente.

---

## 6. Ajuste fino do freio (opcional)

O freio usa curva **gamma 1.6** por padrão — progressivo, exige mais força no final. Isso é ideal para load cells.

| Você quer... | O que fazer |
|---|---|
| Freio menos sensível no início | Aumentar `ga` (ex: 2.0–2.5) |
| Freio mais linear | Diminuir `ga` para 1.0 |
| Curva personalizada | Aba **Curva do Freio** → arraste os pontos → marque "Ativar curva" |
| Menos tremor/ruído | Diminuir `ema` (ex: 30–40) — mais filtragem |

---

## 7. Salvar perfil

Na aba **Perfis** → clique **💾 Salvar perfil...** → salve como `.json`.

Você pode carregar este perfil depois sem precisar recalibrar.

---

## Solução de problemas rápida

| Sintoma | Solução |
|---------|---------|
| Porta não aparece na lista | Instale o driver STM32 Virtual COM Port ou Maple driver |
| `SIM Pedals OK` não aparece no log | Reconecte o USB, tente outra porta COM |
| Freio não responde / sempre zero | Verifique fiação HX711 · DT=PB4 · SCK=PB3 |
| Freio oscila sozinho em repouso | Aumente `dz` para 15–20 · verifique GND do HX711 |
| Acelerador começa em ~50% | Recalibre · mova o pedal (ímã do Hall) no range completo |
| Barra do freio não vai a 100% | Repita `⛂ Pisar fundo` com força maior |

Para problemas mais complexos, consulte [`docs/CALIBRATION.md`](./CALIBRATION.md) e [`docs/TUNING.md`](./TUNING.md).
