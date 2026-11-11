# Hardware Characterisation

Two measurements that replace most of the simulated figures in this project
with data. Neither needs an oscilloscope.

| Part | Needs | Gives |
|---|---|---|
| A. DC rails | multimeter | regulator operating point, which regime the HV clamp is in |
| B. Electrical sweep through a dummy capsule | audio interface with a line output and a phantom-powered mic input, multimeter, one capacitor | gain, frequency response, transformer inductance, self-noise |

Written for a board at default gain (R6 = 5.6 kΩ). For a hi-gain board
(R6 = 47 kΩ) pass `--hi-gain` to both scripts. Tell `analyze.py` about the
other options too: `--presence` with R_PRES1 and C_PRES1 fitted,
`--full-winding` with the transformer on its full winding. A board up to v3.6
needs `--no-cg` (no C_G1, #123) and `--rfi-ohms 100` (100 Ω RFI resistors; 47 Ω
since #113).

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
- The same goes for R_OSC1, C10 and U4 pins 2 and 6, the oscillator's timing
  node. A little leakage there stops the oscillator, and with it the
  polarisation voltage (#120).

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
| `SIG_OUT` | R7, lower pad (toward the XLR end), or U1 pin 6 | half of `V_OPA`, within about 0.3 V | the amplifier's operating point; see below |

Derived:

- Z_REG1 current = (`V_OPA_RAW` − `V_BASE_REG`) / 2.2 kΩ. Expected about 1.5 mA.
  Below about 0.3 mA the regulator is close to dropping out.
- Phantom draw = (open-circuit phantom voltage − voltage at J3 pad 2) / 3.4 kΩ.
  Expected about 4.6 mA. To get the open-circuit voltage, measure an empty XLR
  input of the same interface.
- `VBOOST` within about 0.3 V of `V_OPA` + 3 × `V_OSC` − 0.6 V means DZ1 is not
  clamping. Lower means DZ1 is setting the rail. Both are normal.
- `VBOOST` close to `V_OPA` − 0.7 V (about 23 V) means the pump is not running.
  Measure U3 pin 2 and pin 4 to GND on DC volts: about half of `V_OSC` each
  while the oscillator runs (the meter averages the square wave), 0 V or
  `V_OSC` when it is stopped. If it is stopped, check U4 pin 3 (OUT, also
  about half of `V_OSC` while running) and U4 pins 2 and 6: stuck at 0 V there
  usually means leakage to GND around R_OSC1 and C10 (#120).
- `V_OSC` should sit at 15 V ±5%. Below about 14.2 V Z_OSC1 is out of
  regulation: the clock is drawing too much (#121; the v3.5 RC oscillator
  drew about 1.5 mA and held it at 13.8 V).

The amplifier's operating point:

- Read it at `SIG_OUT` only. `SIG_OUT` is the op-amp's output, so the meter
  does not load it.
- Do not judge it from `V_MID` (C4, C5, the BP pad). `V_MID` comes from a
  470 kΩ + 470 kΩ divider, 235 kΩ at DC. A 10 MΩ meter reads it about 0.3 V
  low, and `SIG_OUT` follows it down for as long as the meter is connected.
- Do not probe `VINV` (U1 pin 2, R3, the upper pad of R6). It shows nothing
  that `SIG_OUT` does not, and the probe adds its capacitance to the
  inverting input.
- `SIG_OUT` sits at `V_MID` plus the DC error at the input: the op-amp's
  offset, and bias current and board leakage into `VPLUS` times 200 MΩ.
  100 pA is 20 mV. More than about 0.3 V from half of `V_OPA` means leakage:
  clean around C8, R_IN1, R_BIAS1 and U1 pin 3.
- Boards without C_G1 (v3.5.x, v3.6) multiply that error: R3 returns it to
  `V_MID` as a current, which moves `V_MID` by about 107 times the error, and
  `SIG_OUT` sits a further 1 + R6 / R3 times the error above `V_MID` (#123).
  At `SIG_OUT` that is about 111 times at default gain and 129 times on a
  hi-gain board: 10 mV of error moves `SIG_OUT` by 1.1 to 1.3 V. A reading
  1 V or more from half of `V_OPA` is possible on a board that records
  normally (13.2 V measured on one hi-gain v3.6 board). The error drifts as
  leakage changes, so readings taken minutes apart can differ by tenths of a
  volt. Cleaning the same area brings it closer.

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

**S1 without a low AC range.** Many meters have nothing below 200 V AC and read
0 here. The interface can stand in, as long as the preamp gain is the one used
for S3 and the noise recordings (the loopback is recorded at the very end, see
below):

1. Take `v-source` from the interface's output spec: the level of 0 dBFS at the
   line output with its volume at maximum (SSL 2: +12.5 dBu), less 20 dB for
   the tone. Expect an error of about ±0.5 dB. The spec is tip to ring. The
   capacitor is driven tip to sleeve with the ring unconnected, which on a
   truly balanced output is half of it: subtract another 6 dB. The SSL 2 and
   SSL 2+ outputs are truly balanced ([SSL's MK I FAQ](https://support.solidstatelogic.com/hc/en-gb/articles/4416629685009-SSL-2-2-MK-I-General-FAQ):
   "true, fully balanced outputs"), so `v-source` is 0.163 V for the −20 dBFS tone, not 0.327 V.
2. After N2, with phantom off, connect the line output straight to the same mic
   input, **wired the way it drove the capacitor**: tip to pin 2, sleeve to
   pins 1 and 3, with the same plug (TS or TRS) in the line output. Do not use
   a balanced TRS to XLR lead. On a truly differential output, tip to sleeve
   is half of tip to ring, so a balanced loopback reads 6 dB more than the
   capacitor was driven with, and the gain comes out 6 dB low. Play
   `cal_tone_400Hz_-60dBFS.wav` and record a few seconds.
3. The 400 Hz level of `rec_tone_small.wav` less the level of this loopback
   recording is the gain from the injection point to the XLR pins. `v-xlr` is
   `v-source` times that ratio.

If the gain knob may have been moved in between, compare the N2 recording with
a fresh one through the 150 Ω termination: at high gain the interface noise
follows the gain dB for dB. Turn the knob back until the 1 to 10 kHz band
matches within about 0.2 dB, or correct by the difference.

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
| Gain at 1 kHz | about −1.0 dB into 4 kΩ with a 56 pF dummy (sensitivity about −39 dBV/Pa with a 13 mV/Pa capsule); about 0.2 dB lower on boards up to v3.6 (100 Ω RFI resistors) | more than ±1.5 dB off: check R3, R6, the load value and the meter readings |
| Low-frequency −3 dB corner | about 30 Hz on the full winding (set by the input network); on the 3-turn section anywhere from about 25 to 80 Hz, depending on `Lp` | on the 3-turn section the fitted `Lp` is the useful result: `sim/models/passives.lib` uses its lower bound, 1 H (#114) |
| Fit error | below about 1 dB | larger: the low end is not behaving like the model. Compare with the hot sweep for saturation |
| Self-noise | about 20 dB(A) equivalent with a 47 to 56 pF dummy (19.1 with a 55 pF capsule); about 45 nV/√Hz at 1 kHz, 12 nV/√Hz at 10 kHz | higher at low frequency only: leakage or hum. Higher everywhere: supply or interface noise. Check the interface margin line |
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
  SIG_OUT ______
  J3 pad 2 ______   J3 pad 3 ______    open-circuit phantom ______

B. S1  v-source ______ V   v-xlr ______ V   (400 Hz, AC rms)
```
