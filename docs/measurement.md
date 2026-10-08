# Hardware Characterisation

Two measurements that replace most of the simulated figures in this project
with data. Neither needs an oscilloscope.

| Part | Needs | Gives |
|---|---|---|
| A. DC rails | multimeter | regulator operating point, which regime the HV clamp is in |
| B. Electrical sweep through a dummy capsule | audio interface with a line output and a phantom-powered mic input, multimeter, one capacitor | gain, frequency response, transformer inductance, self-noise |

Written for a v3.5 board at default gain (R6 = 5.6 kΩ). For a hi-gain board
(R6 = 47 kΩ) pass `--hi-gain` to both scripts.

Tracking issue: #114. Related: #82 (hum), #99 (transformer inductance).

## Safety and handling

- `VBOOST`, `HV_FILT` and `CAP_FP` sit at about 67 V DC. The energy is small,
  but do not short them to other nodes.
- Switch phantom power off and wait 30 s before soldering, plugging or
  unplugging anything.
- Do not probe `CAP_FP`, `VPLUS` or `HV_FILT` with the multimeter. Their source
  impedance is 1 MΩ to 200 MΩ and a 10 MΩ meter will read wrong and disturb them.
- After soldering near C8, R_IN1, R_BIAS1 or the FP/BP pads, clean the flux off
  and let the board dry. Residue there shows up as noise and pops.

## Part A: DC rails

Board powered from 48 V phantom, capsule connected or not. Wait one minute
after power-up. Meter on DC volts, black lead on GND: J3 pad 1 (the left of the
three pads marked 1 2 3 at the XLR end) or a mounting-hole pad at that end.

| Node | Probe point | Expected | Meaning if different |
|---|---|---|---|
| `V_OPA_RAW` | C1, left pad | about 27.5 V | sets regulator headroom |
| `V_BASE_REG` | Z_REG1, right pad (cathode, band end) | about 24.0 V (22.8 to 25.2) | zener tolerance |
| `V_OPA` | C6, right pad (the + side) | about 23.4 V | about 0.65 V below `V_BASE_REG` |
| `V_OSC` | Z_OSC1, left pad (cathode, band end) | about 15.0 V | below about 14.7 V: Z_OSC1 is starved, by U3's supply current or by DZ1 clamping |
| `VBOOST` | DZ1, lower pad (cathode, toward the XLR end) | 64.6 to 68.2 V | this is the capsule polarisation rail |
| Phantom at the mic | J3 pad 2 and pad 3 | about 32 V each | lower: the supply is below 48 V or the mic draws more than expected |

Derived:

- Z_REG1 current = (`V_OPA_RAW` − `V_BASE_REG`) / 2.2 kΩ. Expected about 1.5 mA.
  Below about 0.3 mA the regulator is close to dropping out.
- Phantom draw = (open-circuit phantom voltage − voltage at J3 pad 2) / 3.4 kΩ.
  Expected about 4.6 mA. To get the open-circuit voltage, measure an empty XLR
  input of the same interface.
- `VBOOST` within about 0.3 V of `V_OPA` + 3 × `V_OSC` − 0.6 V means DZ1 is not
  clamping. Lower means DZ1 is setting the rail. Both are normal.

## Part B: electrical sweep through a dummy capsule

The capsule is a voltage source in series with its own capacitance. Replacing
it with a capacitor fed from the interface's line output drives the electronics
exactly as the capsule would, with a known voltage.

### Parts and settings

- Dummy capacitor: 56 pF C0G/NP0, rated 100 V or more. 47 to 68 pF is fine;
  pass the value with `--cdummy`.
- A shielded lead from the interface line output: signal to the capacitor,
  shield to mic GND.
- Interface at 48 kHz, 24 bit. Use a line output whose level is not changed by
  a monitor knob, or leave that knob untouched for the whole session.
- Record in a DAW or recorder that adds no processing. Export mono WAV.

Generate the test signals:

```bash
python3 tools/measure/gen_signals.py          # writes tools/measure/signals/*.wav
```

### Configuration S (signal)

```
line out (tip) ──||── FP pad          BP pad: left open
              56 pF
line out (sleeve) ──── mic GND (J3 pad 1)
mic XLR out ──── interface mic input, phantom on
```

Solder the capacitor directly at the FP pad with short leads. The housing
stays open. Hum pickup does not matter here because the test signal is large.

**S1. Gain, with the multimeter.** Play `cal_tone_400Hz_-20dBFS.wav` on loop.
Meter on AC volts.

1. Measure between the line-out signal and sleeve, on the interface side of the
   capacitor. This is `v-source`. It should be between 0.2 and 0.7 V. If not,
   change the output level and keep it there.
2. Measure between J3 pads 2 and 3 with the mic still connected to the
   interface. This is `v-xlr`. Expect roughly the same value as `v-source`.

Both readings are taken at the same frequency with the same meter, so the
meter's own frequency error cancels in the ratio.

**S2. Frequency response.** Set the preamp gain so the tone peaks around
−12 dBFS. Play `sweep_-46dBFS.wav` once and record the mic input for its whole
length. Save as `rec_sweep.wav`.

Optional: repeat with `sweep_-26dBFS.wav` (lower the preamp gain by 20 dB) and
save as `rec_sweep_hot.wav`. Comparing the two shows where the transformer
starts to saturate at low frequency.

**S3. Calibration for the noise measurement.** Play
`cal_tone_400Hz_-60dBFS.wav` and turn the preamp gain up until the tone peaks
around −10 dBFS, or to maximum gain if it does not get that far. Do not touch
the gain again until Part B is finished. Record 20 s of the tone. Save as
`rec_tone_small.wav`.

### Configuration N (noise)

Phantom off, wait, then move the capacitor so it sits between the FP and BP
pads, with no external lead. Close the housing with the grille on: the node is
200 MΩ and will pick up hum otherwise.

```
FP pad ──||── BP pad
       56 pF
```

**N1.** Phantom on, wait three minutes. Record 30 s of silence at the gain set
in S3. Save as `rec_noise.wav`. Keep the room quiet and the mic still: the
board and its ceramic capacitors are slightly microphonic.

**N2.** Unplug the mic. Plug a 150 Ω resistor across pins 2 and 3 of the same
input (a shorted XLR also works). Record 30 s at the same gain. Save as
`rec_iface_noise.wav`.

### Analysis

```bash
python3 tools/measure/analyze.py \
    --sweep-ref tools/measure/signals/sweep_-46dBFS.wav --sweep-rec rec_sweep.wav \
    --v-source 0.412 --v-xlr 0.390 \
    --tone-rec rec_tone_small.wav --noise-rec rec_noise.wav \
    --iface-noise-rec rec_iface_noise.wav \
    --rload 4000 --cdummy 56e-12 --plot response.png
```

`--rload` is the mic input impedance of the interface, from its manual. Each
group of inputs is optional, so a partial session still gives a partial report.
`--self-test` runs the analysis on synthetic data and is part of CI.

### Reading the results

| Result | Simulation | What a difference means |
|---|---|---|
| Gain at 1 kHz | about −0.5 dB into 4 kΩ (sensitivity about −38 dBV/Pa with a 13 mV/Pa capsule) | more than ±1.5 dB off: check R3, R6, the load value and the meter readings |
| Low-frequency −3 dB corner | 150 Hz if `Lp` = 0.5 H; 20 to 50 Hz if `Lp` is several henries | this is the main unknown (#99). The fitted `Lp` goes into `sim/models/passives.lib` |
| Fit error | below about 1 dB | larger: the low end is not behaving like the model. Compare with the hot sweep for saturation |
| Self-noise | 18.4 dB(A) equivalent; 39 nV/√Hz at 1 kHz, 9 nV/√Hz at 10 kHz | higher at low frequency only: leakage or hum. Higher everywhere: supply or interface noise. Check the interface margin line |
| Interface margin | 10 dB or more | less: raise the preamp gain and repeat S3, N1, N2 |

Limits of the method:

- The dummy capacitor's tolerance moves the absolute gain by a fraction of a dB
  and the input corner in proportion.
- Below about 10 Hz the interface's own response is part of the result. Record
  the sweep through the interface alone (line out to a line input) and pass it
  with `--loopback-rec` if that range matters.
- The noise figure is for the electronics. It does not include the capsule's
  own acoustic noise.

### Record sheet

Post this, the printed report and `response.png` in #114.

```
Board version:            Gain variant:           Date:
Interface:                Mic input impedance:
Dummy capacitor:          pF

A. DC rails (V)
  V_OPA_RAW ______  V_BASE_REG ______  V_OPA ______  V_OSC ______  VBOOST ______
  J3 pad 2 ______   J3 pad 3 ______    open-circuit phantom ______

B. S1  v-source ______ V   v-xlr ______ V   (400 Hz, AC rms)
```
