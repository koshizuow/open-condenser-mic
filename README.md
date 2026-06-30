# Op-Amp Transformer Condenser Microphone

A compact, phantom-powered true condenser microphone with all SMD/THT components available from standard distributors.

![Prototype](img/prototype.jpeg)

## Overview

This design uses a Dickson charge pump oscillator to generate ~68 V capsule polarization from 48 V phantom power, and feeds a transformer-coupled output stage built around a low-noise op-amp. The reference implementation uses the **OPA1641** (2.5 nV/√Hz, JFET input), chosen for its low voltage noise and LCSC availability. The circuit fits on a 36 × 93 mm 2-layer PCB.

**Key design points:**
- Op-amp output stage; reference design uses OPA1641 (2.5 nV/√Hz voltage noise)
- NTE10/3 audio transformer, 3:1 step-down, transformer-coupled output
- CD40106B Schmitt-trigger oscillator + 3-stage active Dickson charge pump
- 68 V capsule polarization (BZT52C68 zener clamp)
- HV rail LC filter: 10 mH + 470 nF, corner ~2.3 kHz
- Phantom power draw: ~2.4–3 mA typical (IEC 61938 limit: 14 mA)
- All SMD/THT components available from standard distributors (LCSC, Mouser, Digi-Key); capsule and transformer are customer-supplied

## Simulated Performance

Run with ngspice from `sim/` (see [Running Simulations](#running-simulations)):

| Parameter | Simulated | Notes |
|---|---|---|
| V_BOOST steady-state | 67.97 V | target 68.2 V, DZ1-clamped |
| HV_FILT ripple | 10.7 µV p-p | L1=10 mH, C9=470 nF, 10–15 ms window |
| LC filter corner | ~2.3 kHz | startup resonance; dissipates in seconds |
| Capsule voltage | ~68 V | polarization at steady state |

### HV Rail Startup (`boost_dickson.sp`)

![HV startup](img/hv_startup.png)

Charge pump settles to 67.97 V within ~1 ms. HV_FILT (LC-filtered polarization rail) ripple is 10.7 µV p-p at steady state.

### AC Frequency Response (`amp_ac.sp`)

![Frequency response](img/freq_response.png)

Behavioral model, gain normalized to 1 kHz. Flat within ±1 dB from ~200 Hz to ~20 kHz. High-pass rolloff from output coupling (C6 = 10 µF); high-frequency rolloff from op-amp GBW. Response above 20 kHz is outside the audio band.

### Input-Referred Noise Spectrum (`amp_noise_opa1641.sp`)

![Noise spectrum](img/noise_spectrum.png)

SPICE input-referred noise, computed by dividing total output noise by the signal transfer function at each frequency. The slope reflects the signal path's high-pass characteristic (coupling caps attenuate low-frequency signal more than noise), not a real frequency-dependent noise source. Midband (1–10 kHz) noise floor is dominated by R_GBIAS Johnson noise (~28 nV/√Hz at 94 MΩ) and OPA1641 voltage noise (2.5 nV/√Hz).

## Measured Performance

Tested in a 2.77-hour vocal live stream (singing + speech), signal chain:  
Microphone → SSL SiX (gain ~1 o'clock, compressor) → Yamaha AG06 (XLR in, −29 dB pad) → streaming software.

| Parameter | Measured |
|---|---|
| Integrated loudness (EBU R128) | −19.5 LUFS |
| Loudness range (LRA) | 14.3 LU |
| True peak | −0.45 dBFS |
| Noise floor (quiet passages) | −∞ (digital silence) |
| RF interference / hum | None observed |
| Session duration | 2.77 h, no anomalies |

**Reference comparison:** Same signal chain, gain one notch higher (~2 o'clock), Sound Skulptor SK-49 (K47-style, transformer-coupled): −20.9 LUFS integrated. The OPA1641 mic achieves higher output sensitivity with less preamp gain.

## Hardware Requirements

### Customer-supplied (not in PCBA BOM)
| Item | Spec | Notes |
|---|---|---|
| Capsule | Single-diaphragm, 55–70 V polarization | Most standard large/small-diaphragm capsules in this voltage range are compatible. K47-style capsules typically require ~45 V — change DZ1 from BZT52C68 to BZT52C47 if using one. |
| Transformer | **Neutrik NTE10/3** (3:1, audio) | Mouser / Newark. No other transformer is currently supported; the PCB cutout and solder pads are sized for this specific part. |

### Transformer wiring

The NTE10/3 connects to two sets of bare solder pads on the PCB (5 mm pitch):

| Pad group | Location | Nets | NTE10/3 winding |
|---|---|---|---|
| TP1 (3 pads) | Above transformer cutout | TX_DRV · GND · GND | Primary (signal in, return/centre-tap) |
| TS1 (2 pads) | Below transformer cutout | XLR_HOT · XLR_COLD | Secondary (XLR pin 2 · XLR pin 3) |

Refer to the NTE10/3 datasheet for wire colour identification before soldering.

### PCB
- 2-layer, 36 × 93 mm, ENIG or HASL
- All other components sourced from standard distributors; LCSC part numbers included in BOM
- 4 × M2.5 mounting holes with GND pads for chassis bonding

## Software Requirements

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.8+ | PCB / schematic / BOM generation |
| KiCad | 7.0.x | PCB editor; provides `pcbnew` Python module |
| kicad-cli | 7.0.x | Gerber / drill export (bundled with KiCad) |
| ngspice | any recent | SPICE simulation (optional) |
| numpy | any recent | Simulation plot generation (`sim/plot_all.py`) |
| matplotlib | any recent | Simulation plot generation (`sim/plot_all.py`) |

The `pcbnew` Python module ships with KiCad. On Linux it is typically available after installing KiCad 7 and may require sourcing the KiCad Python environment:

```bash
# Ubuntu / Debian (KiCad 7 PPA)
export PYTHONPATH=/usr/lib/kicad/lib/python3/dist-packages:$PYTHONPATH
```

## Generating Outputs

Run from the **project root** (the directory containing this README).

### 1. Generate KiCad files

```bash
python pcb/gen_project.py    # writes pcb/open-condenser-mic.kicad_pro
python pcb/gen_pcb.py        # writes pcb/open-condenser-mic.kicad_pcb
python pcb/gen_schematic.py  # writes pcb/open-condenser-mic.kicad_sch
```

All three scripts accept `--name PROJECT_NAME` to change the output filename (default: `open-condenser-mic`). After generating, open the project in KiCad via **File → Open Project** and select `pcb/open-condenser-mic.kicad_pro`.

### 2. Fill copper zones and export gerbers

After opening the project in KiCad, fill all copper zones (**Edit → Fill All Zones**, or press **B**), then export gerbers and drill files via **File → Fabrication Outputs**. Alternatively use `kicad-cli pcb export gerbers` and `kicad-cli pcb export drill` for scripted export.

> **Important:** Zone fill must be performed after `gen_pcb.py` runs and before exporting gerbers. The Python script creates the board without filled zones.

### 3. Generate BOM and CPL

```bash
python pcb/gen_bom.py        # reads pcb/open-condenser-mic.kicad_pcb; --name to match custom project name
# → pcb/bom.csv   (grouped BOM with LCSC part numbers)
# → pcb/cpl.csv   (pick-and-place: Designator, X, Y, Layer, Rotation)
```

## Running Simulations

All simulations use ngspice. Run from the `sim/` directory.

```bash
cd sim
ngspice boost_dickson.sp      # HV rail: VBOOST steady-state + ripple
ngspice amp_noise_opa1641.sp  # Input-referred noise, OPA1641 model
ngspice amp_ac.sp             # Closed-loop AC frequency response
ngspice amp_bias_compare.sp   # R_BIAS1 100 MΩ vs 500 MΩ low-freq rolloff comparison
```

### Regenerating plots

`sim/plot_all.py` runs the three main simulations and writes the plots embedded in this README to `img/`. Run from the project root:

```bash
pip install numpy matplotlib   # if not already installed
python sim/plot_all.py
```

## License

[CERN Open Hardware Licence Version 2 – Permissive (CERN-OHL-P)](https://ohwr.org/cern_ohl_p_v2.txt)
