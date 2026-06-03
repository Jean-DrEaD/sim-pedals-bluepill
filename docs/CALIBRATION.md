# Calibração — SIM Pedals Blue Pill

## Visão geral

A calibração ensina ao firmware o **range físico** dos seus sensores.  
Sem calibração: a load cell parece super-sensível; os **sensores Hall 49E** podem não alcançar 0% ou 100%.

---

## Calibração do Freio (Load Cell)

### Conceito

A load cell gera um valor **raw** que pode variar de centenas de milhares a milhões de unidades. O firmware mapeia o range `[bMin..bMax]` para `[0..1023]`.

- `bMin` = valor raw quando **não há força** no pedal (tara)
- `bMax` = valor raw quando o pedal está na **força máxima que você usa**

### Procedimento

1. Conecte à GUI, ligue o **Monitor ON**
2. **Solte completamente** o pedal (não toque)
3. Clique **⊘ Tara/Zero (bMin)** → o firmware lê o valor atual como bMin
4. Agora **pise o pedal com a força máxima** que usará normalmente
5. Clique **⛂ Pisar fundo (bMax)** e confirme
6. Solte o pedal e verifique: a barra Xrot (freio) deve ir de 0 a ~100% no range desejado
7. Clique **Salvar EEPROM**

### O freio vai na direção errada

Se a barra **cai** ao pisar:
- Marque **invb** na seção Inversões de eixo
- A GUI envia o comando; verifique imediatamente se corrigiu

### Ajuste fino pós-calibração

Após calibrar, se o freio ainda parece super-sensível no início:

| Sintoma | Causa | Solução |
|---------|-------|---------|
| Freio muito fácil de ativar | gamma baixo | Aumentar `ga` para 2.0–2.5 |
| Freio não chega a 100% | bMax muito alto | Repita `bfull` pisando mais forte |
| Freio oscila em repouso | ruído do HX711 | Aumentar `dz` para 15–25 |

---

## Calibração do Acelerador e Embreagem (Hall 49E)

### O pedal começa em 50% ou não vai a 100%

- O **ímã do sensor Hall** não está percorrendo o range físico completo
- Abra o Monitor, mova o pedal e observe o RAW exibido no rodapé
- Ajuste `axMin` / `axMax` para os valores mínimo e máximo que você observou

### Auto-calibração (recomendado)

1. Conecte e ligue o Monitor ON
2. Clique **▶ Iniciar auto-cal**
3. Mova o **acelerador** do mínimo ao máximo e de volta, 2–3 vezes
4. Faça o mesmo com a **embreagem**
5. Clique **■ Parar e aplicar** — a GUI aplica os limites com margem de 2%
6. Clique **Salvar EEPROM**

### Manual

Se preferir ajustar manualmente, use os spinboxes `axMin / axMax / ayMin / ayMax` na seção Configuração e clique **Set** em cada um. Depois **Salvar EEPROM**.

---

## Tabela de parâmetros de calibração

| Parâmetro | Padrão | Descrição |
|-----------|--------|-----------|
| `axMin` | 410 | ADC mínimo do acelerador — Hall 49E @ 3.3V (0..4095) |
| `axMax` | 3685 | ADC máximo do acelerador — Hall 49E @ 3.3V |
| `ayMin` | 410 | ADC mínimo da embreagem — Hall 49E @ 3.3V |
| `ayMax` | 3685 | ADC máximo da embreagem — Hall 49E @ 3.3V |
| `bMin` | 0 | Raw mínimo da load cell (tara) |
| `bMax` | 1000000 | Raw máximo da load cell (fundo) |
| `dz` | 8 | Deadzone HID em repouso (0..200) |
| `invx` | 0 | Inverte acelerador |
| `invy` | 0 | Inverte embreagem |
| `invb` | 0 | Inverte freio |

---

## Resetar para padrões

Clique **Defaults** na GUI ou envie `def` pelo log serial.

> ⚠️ Isso apaga a calibração. Refaça o procedimento acima depois.

---

## Salvar perfil

Após calibrar: aba **Perfis** → **💾 Salvar perfil...** → salve como `.json`.

O arquivo contém toda a configuração (incluindo calibração) e pode ser carregado de volta a qualquer momento sem precisar recalibrar.
