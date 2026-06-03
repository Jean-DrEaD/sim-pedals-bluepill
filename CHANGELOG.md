# Changelog

Todos os formatos seguem [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/)
e [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [1.0.0] - 2026-06-02

### Added
- Parâmetro **`bscale`** do freio (-10 a 10) com inversão de sentido.
- Comando `diag` com medição **pico a pico (P2P)** do HX711.
- GUI: controle de `bscale` (slider -3 a +3, presets, spinbox), editor de curva
  arrastável e osciloscópio.
- Persistência de perfis em `.json`.

### Changed
- Calibração `bzero`/`bfull` agora usa **mediana de 9 leituras** (antes `read_average(4)`).
- GUI envia LUT/comandos em **thread separada** com **debounce de 150 ms**.
- `EE_MAGIC` atualizado para `0x5353`.

### Fixed
- **Saturação "no máximo"** (1023) com range curto — adicionada
  **proteção de range mínimo** (`bMax ≥ bMin + 20000`).

[1.0.0]: https://github.com/Jean-DrEaD/sim-pedals-bluepill/releases/tag/v1.0.0
