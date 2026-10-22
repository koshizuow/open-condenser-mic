* Clock chain current with an ICM7555 clock (#121)
* ────────────────────────────────────────────────────────────────────────────
* Proposed: ICM7555 astable (OUT -> R_OSC1 68k -> THR/TRIG, C10 100p to GND,
* f = 1/(1.386 R C) ~ 105 kHz, 50 % duty) driving U3A, U3A driving U3B as
* before. The CD40106B gates use the CMOS model calibrated in
* clock_rc_calib.sp. The ICM7555 is behavioural: thresholds at 1/3 and 2/3 of
* VDD, output with ~50 ns edges (Cf 25p) or slower (75p). U3 has its own
* supply source so that its current is measured alone.
*
* Results (four calibrated size sets, VDD 14.25 / 15 / 16 V, both edge rates):
*   I(U3) 203 to 264 uA (the RC oscillator: 1.24 to 1.68 mA), f 102 to 105 kHz,
*   duty 49 to 51 %, CLKB lags CLKA by 23 to 34 ns per edge.
* Whole clock: U3 ~0.23 mA + ICM7555 0.06 typ / 0.30 max + C10 charging via
* R_OSC1 ~0.11 mA + U3A input ~0.02 mA = ~0.42 mA typical, ~0.69 mA max,
* inside the 0.75 mA worst case of supply_dc_op.sp and pump_real_vosc.sp.
* ────────────────────────────────────────────────────────────────────────────
.param KS=0.7 WF5=25u WF6=10u VDD=15
.model NM NMOS (LEVEL=1 VTO=1.6 KP=40u LAMBDA=0.01 CGSO=2n CGDO=2n CJ=1e-4)
.model PM PMOS (LEVEL=1 VTO=-1.6 KP=16u LAMBDA=0.01 CGSO=2n CGDO=2n CJ=1e-4)
.subckt SCH in out vdd gnd
M1 a  in vdd vdd PM W={30u*KS} L=5u
M2 x  in a   vdd PM W={30u*KS} L=5u
M3 x  in b   gnd NM W={12u*KS} L=5u
M4 b  in gnd gnd NM W={12u*KS} L=5u
M5 a  x  gnd vdd PM W={WF5} L=5u
M6 b  x  vdd gnd NM W={WF6} L=5u
M7 out x gnd gnd NM W=60u L=5u
M8 out x vdd vdd PM W=150u L=5u
Cx x gnd 0.5p
Ca a gnd 0.2p
Cb b gnd 0.2p
.ends
.subckt SCHN in out vdd gnd
X1 in y vdd gnd SCH
M9  out y gnd gnd NM W=60u L=5u
M10 out y vdd vdd PM W=150u L=5u
Cy y gnd 0.5p
.ends
* supplies: U3 on its own source so that its current is measured alone
Vu3  vu3  0 DC {VDD}
V555 v555 0 DC {VDD}
* ICM7555 behavioral: comparator with 1/3, 2/3 thresholds (switch hysteresis), output with ~50 ns edges
.model SWH SW (VT={VDD/2} VH={VDD/6} RON=1 ROFF=1G)
Vlog vlog 0 DC 1
Rq vlog q 1k
S1 q 0 tim 0 SWH
Rf q qs 1k
Cf qs 0 25p
B555 out555 0 V = V(v555) * V(qs)
R_OSC1 out555 tim 68k
C10 tim 0 100p IC=0
* U3A, U3B as before
XA out555 clka vu3 0 SCHN
XB clka clkb vu3 0 SCHN
CLa clka 0 50p
CLb clkb 0 50p
.control
tran 10n 200u 0 10n uic
meas tran iu3 avg i(Vu3) from=50u to=200u
let iu3ua = -iu3*1e6
meas tran p1 trig v(clka) val={7.5} rise=3 targ v(clka) val=7.5 rise=13
let fr = 10/p1/1000
meas tran ha when v(clka)=7.5 rise=5
meas tran hb when v(clkb)=7.5 fall=5
meas tran la when v(clka)=7.5 fall=5
meas tran lb when v(clkb)=7.5 rise=6
let d1 = (hb-ha)*1e9
let d2 = (lb-la)*1e9
meas tran duty_a avg v(clka) from=50u to=200u
let dut = duty_a/15*100
echo "NEW: I(U3) = $&iu3ua uA   f = $&fr kHz   CLKA duty = $&dut %   CLKB edge after CLKA edge: $&d1 ns / $&d2 ns"
.endc
.end
