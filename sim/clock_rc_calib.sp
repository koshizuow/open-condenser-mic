* Clock chain current, calibration step (#121): the v3.5 RC Schmitt oscillator
* ────────────────────────────────────────────────────────────────────────────
* No vendor model of the CD40106B is at hand, so its gates are a hand-built
* CMOS Schmitt inverter (input stack M1-M4, feedback M5/M6, output inverter).
* The sizes are set so that this circuit (U3A with R_OSC1 47k and C10 100p,
* U3B after it) draws what the v3.5 board drew: 1.54 mA at 14.0 V (#121,
* step C). Several size sets reproduce it (1.24 to 1.68 mA); clock_icm7555.sp
* runs the proposed clock with each of them. The clock loads are 50 pF each
* (diodes and traces; the pump itself draws next to nothing, #121 step B).
* ────────────────────────────────────────────────────────────────────────────
.param KS=0.7
.model NM NMOS (LEVEL=1 VTO=1.6 KP=40u LAMBDA=0.01 CGSO=2n CGDO=2n CJ=1e-4)
.model PM PMOS (LEVEL=1 VTO=-1.6 KP=16u LAMBDA=0.01 CGSO=2n CGDO=2n CJ=1e-4)
* CMOS Schmitt inverter: input stack (M1-M4) with feedback (M5, M6), output inverter (M7, M8)
.subckt SCH in out vdd gnd
M1 a  in vdd vdd PM W={30u*KS} L=5u
M2 x  in a   vdd PM W={30u*KS} L=5u
M3 x  in b   gnd NM W={12u*KS} L=5u
M4 b  in gnd gnd NM W={12u*KS} L=5u
M5 a  x  gnd vdd PM W=25u L=5u
M6 b  x  vdd gnd NM W=10u L=5u
M7 out x gnd gnd NM W=60u L=5u
Cx x gnd 0.5p
Ca a gnd 0.2p
Cb b gnd 0.2p
M8 out x vdd vdd PM W=150u L=5u
.ends
.subckt SCHN in out vdd gnd
X1 in y vdd gnd SCH
M9  out y gnd gnd NM W=60u L=5u
M10 out y vdd vdd PM W=150u L=5u
Cy y gnd 0.5p
.ends
Vosc vdd 0 DC 14.0
* U3A: Schmitt inverter (input stage + inverting output). SCH output 'out' is inverted? x = inverted input; out = buffered x' -> non-inverting. Use SCHN for inverting.
XA clkin clka vdd 0 SCHN
R_OSC1 clka clkin 47k
C10 clkin 0 100p IC=0
XB clka clkb vdd 0 SCHN
CLa clka 0 50p
CLb clkb 0 50p
.control
tran 20n 300u 0 20n uic
meas tran iavg avg i(Vosc) from=100u to=300u
let ima = -iavg*1000
meas tran f0 trig v(clka) val=7 rise=5 targ v(clka) val=7 rise=15
let fr = 10/f0
meas tran vin_avg avg v(clkin) from=100u to=300u
echo "OLD RC: I(V_OSC) = $&ima mA   f = $&fr Hz   CLKA_IN avg = $&vin_avg V"
.endc
.end
