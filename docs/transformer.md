# NTE10/3 transformer measured on its own

Issue #137. One unit, taken off the board, 2026-11-24.

## Result

| | Data sheet | Measured |
|---|---|---|
| Turns, output : tap : full | 1 : 3 : 10 | 1 : 3.58 : 10.03 |
| DC resistance, red–blue (tap) | — | 527 Ω |
| DC resistance, red–black (full) | — | 1658 Ω |
| DC resistance, white–yellow (output) | — | 41.8 Ω |
| Loss beyond turns and winding resistance | — | none that the levels show (0.03 dB on the full winding) |
| Inductance of the tap section, small level | — | about 22 H (see below) |

The tap section's ratio explains two things that the model carried as a provisional 3 kΩ core loss:

- the tap wiring sits 1.5 dB below what 3:1 gives;
- the whole microphone measures the tap wiring 8.8 dB above the full winding (#132). 10:3 gives 10.0 dB, 10.03:3.58 gives 8.9 dB.

## Method

- SSL 2 at 96 kHz. Line output 1, tip to sleeve (ring open), through 1.2 kΩ into the driven winding
  (red–blue or red–black; the other end to ground).
- Output side (white–yellow), yellow grounded:
  - into the instrument input (LINE + HI-Z, about 1 MΩ), which leaves it open: turns ratio and inductance;
  - into the microphone input (1.2 kΩ, 48 V off, pin 3 grounded): the loaded level, as a check.
- Reference for each input: the transformer taken out and the 1.2 kΩ resistor connected straight to the
  input, everything else as it was. Every figure below is relative to that.
- Tones at 1 kHz for the level, log sweeps from 5 Hz to 45 kHz for the response, tones at 30, 50 and 100 Hz
  for distortion. In a grounded steel box; hum at 60 Hz was below −105 dBFS.
- The output voltage was not measured. From the interface's ratings and the levels seen, 0 dBFS is about
  1.6 V rms tip to sleeve; the levels below are given in dBFS played.

## Levels at 1 kHz

| Driven winding | Input | Measured | Ideal 1:3:10 with these resistances | With 3.58 and 10.03 |
|---|---|---|---|---|
| tap | open (1 MΩ) | −11.07 dB | −9.54 dB | −11.07 dB (defines 3.58) |
| full | open (1 MΩ) | −20.03 dB | −20.0 dB | −20.03 dB (defines 10.03) |
| tap | 1.2 kΩ | −6.13 dB | −5.07 dB | −6.24 dB |
| full | 1.2 kΩ | −14.35 dB | −14.47 dB | −14.50 dB |

The open-output levels were the same at every level tried (played −27, −17 and −7 dBFS) and flat within
0.2 dB from 500 Hz to 40 kHz. The two loaded levels are not fitted; they come out 0.1 dB above the
prediction, both by the same amount, which the input's real impedance against its nominal 1.2 kΩ can account for.

## Low end

Tap section, output open, 1.2 kΩ in series, relative to 1 kHz:

| Played | 10 Hz | 15 Hz | 20 Hz | 30 Hz | 50 Hz | 100 Hz |
|---|---|---|---|---|---|---|
| −27 dBFS | −3.5 dB | −2.3 dB | −1.6 dB | −1.1 dB | −0.6 dB | −0.3 dB |
| −7 dBFS | −5.4 dB | −3.0 dB | −1.9 dB | −0.8 dB | −0.6 dB | −0.3 dB |

- −3 dB at about 11 Hz at the small level: about 22 H behind 1.2 kΩ + 527 Ω.
- One inductance does not fit the shape (0.2 dB rms); the response falls more slowly than one pole below
  100 Hz. An inductance of 17.9 H in series with 8.5 H parallel 2.23 kΩ fits within 0.06 dB from 10 Hz to
  5 kHz. With the same values the response into 1.2 kΩ and of the full winding (scaled by the turns
  squared) comes out within 0.2 dB, without fitting them.
- The full winding, open, is 0.5 dB down at 10 Hz.

**Not settled.** In the whole microphone the tap section behaves as about 8 H (#128: C_DC and the
inductance give a small bump near 32 Hz). On its own it measures about 22 H. Here no winding carried
direct current; in the microphone the output winding sits between the two phantom feed resistors. Whether
that is the reason has not been tested. `sim/models/passives.lib` therefore keeps the 7.4 H derived from
the data sheet.

## Distortion

Third harmonic relative to the fundamental, 1.2 kΩ in series, into 1.2 kΩ. The second harmonic is at
least 10 dB lower in every row. The path without the transformer is below −90 dB at these levels.

| Driven winding | Frequency | −27 dBFS | −17 dBFS | −7 dBFS | −1 dBFS |
|---|---|---|---|---|---|
| tap | 30 Hz | −45 dB | −42 dB | −31 dB | −19 dB |
| tap | 50 Hz | −52 dB | −51 dB | −43 dB | −33 dB |
| tap | 100 Hz | −61 dB | −61 dB | −56 dB | −49 dB |
| tap | 1 kHz | −86 dB | −84 dB | −83 dB | −82 dB |
| full | 30 Hz | −59 dB | −58 dB | −53 dB | −46 dB |
| full | 50 Hz | −65 dB | −64 dB | −62 dB | −57 dB |
| full | 100 Hz | −75 dB | −74 dB | −74 dB | −71 dB |
| full | 1 kHz | −93 dB | −90 dB | −95 dB | −95 dB |

The 1.2 kΩ source raises these: in the microphone the op-amp drives the winding through 100 Ω.

## Limits

- One unit. The ratio of another has not been measured.
- The output voltage was inferred, not measured, so the distortion table is not yet tied to sound levels.
- On the instrument input the path itself dropped by 6 dB for a second or two at the highest levels
  (1 kHz played at −1 dBFS, once 30 Hz at −7 dBFS), with the transformer taken out too. The cause is not
  known. The figures above use levels at which every run was steady.
