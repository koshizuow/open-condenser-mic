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

The data sheet gives only the turns and a response figure, so these values are what `sim/models/passives.lib` uses.

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

Relative to the reference with the same series resistor and input.

| Driven winding | Series resistor | Input | Measured | With 1 : 3 : 10 | With 1 : 3.58 : 10.03 |
|---|---|---|---|---|---|
| tap | 1.2 kΩ | open (1 MΩ) | −11.07 dB | −9.54 dB | −11.07 dB (defines 3.58) |
| full | 1.2 kΩ | open (1 MΩ) | −20.03 dB | −20.0 dB | −20.03 dB (defines 10.03) |
| tap | 1.2 kΩ | 1.2 kΩ | −6.13 dB | −5.07 dB | −6.24 dB |
| full | 1.2 kΩ | 1.2 kΩ | −14.35 dB | −14.47 dB | −14.50 dB |
| tap | 4.7 kΩ | 1.2 kΩ | −0.17 dB | +0.7 dB | 0.0 dB |
| full | 4.7 kΩ | 1.2 kΩ | −6.76 dB | −6.78 dB | −6.81 dB |

None of the last four rows is fitted. Levels were the same at every level tried (played −27, −17 and −7 dBFS).

### A ratio, not a core loss

With one series resistor the open-output level cannot tell a ratio of 3.58 from a ratio of 3 with a core
loss of about 9 kΩ across the tap section. A loss depends on the series resistor, a ratio does not, so the
tap section was measured again behind 4.7 kΩ:

| | 1 kHz, tap, 4.7 kΩ, into 1.2 kΩ |
|---|---|
| measured | −0.17 dB |
| ratio 3.58, no loss | 0.0 dB |
| ratio 3, core loss 9 kΩ | −2.2 dB |

From 20 Hz to 20 kHz the measured response follows the first within 0.25 dB rms (with the magnetising
branch below, fitted earlier behind 1.2 kΩ) and is 2.2 dB or more above the second everywhere. A small loss
remains that changes with frequency: 0.2 to 0.4 dB between 200 Hz and 1 kHz.

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

In the whole microphone the low end is different from what this branch gives: −5.0 dB at 20 Hz and
−0.6 dB at 30 Hz relative to 1 kHz on the tap wiring (#128), where the model gives −1.9 and −1.8 dB; from
50 Hz up they agree within 0.2 dB. The next section finds the reason.

## In the microphone's output network

The output side (white, yellow) was soldered to a spare v3.6 board (no capsule), and the board's XLR output
taken to the microphone input with a plain cable.

**Phantom on or off makes no difference.** Tap section driven from the fixture through 1.2 kΩ, the board's
own primary pads left open. Response relative to 1 kHz, played −37 dBFS: 20 Hz −1.85 dB off, −1.83 dB on;
30 Hz −1.07 and −1.06 dB. The two sweeps differ by 0.07 dB at most from 10 Hz to 40 kHz. On the board the
windings sit at 31 V; the voltage across the output winding is too small for a meter. So the phantom
supply's direct current is not what changes the low end.

**The resonance with C_DC moves with level.** Red to the board's primary signal pad, blue straight to the
interface's output, no series resistor, phantom on. The powered op-amp's output is an AC ground, so the
loop is source, winding, C_DC with its 12 V bias, 100 Ω: the microphone's own output network.

| Played | Peak | 20 Hz | 30 Hz | 50 Hz | 100 Hz |
|---|---|---|---|---|---|
| −47 dBFS | +5.1 dB near 25 Hz | +3.7 dB | +4.3 dB | +1.5 dB | +0.35 dB |
| −37 dBFS | +4.4 dB near 22 Hz | +4.0 dB | +3.4 dB | +1.3 dB | +0.30 dB |
| −27 dBFS | +3.1 dB near 22 Hz | +3.0 dB | +2.4 dB | +1.0 dB | +0.25 dB |
| −17 dBFS | +2.5 dB near 18 Hz | +2.2 dB | +1.3 dB | +0.6 dB | +0.17 dB |

Relative to 1 kHz, where the level is the same at all four (−11.90 dB re played).

- The resonance rises from 18 Hz to 25 Hz as the level falls by 30 dB: the inductance at the small level is
  about half of that at the large one. With C_DC at its nominal 4.7 µF that is 17 H and 8.5 H.
- The whole-microphone measurement (#128) was made near the lowest of these levels, which is why it looks
  like about 8 H, while the part behind 1.2 kΩ at a larger level looks like 22 H.
- Only the product of inductance and capacitance comes out of this. C_DC under its 12 V bias has not been
  measured on its own.
- The model's branch is one fixed set of values, fitted at a larger level. It describes loud signals; for
  quiet ones the real low end has less at 20 Hz and a higher, taller bump.

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

- One unit. The ratio of another has not been measured. The whole-microphone figures (#128) are from a
  different unit and board than the measurements here.
- The output voltage was inferred, not measured, so the distortion table is not yet tied to sound levels.
- On the instrument input the path itself moved between two levels 6 dB apart, slowly and at no fixed
  level or frequency, with the transformer taken out too. The cause is not known. The open-output figures
  above are from runs that were steady throughout; the microphone input showed none of it, and the
  4.7 kΩ measurements were made there.
