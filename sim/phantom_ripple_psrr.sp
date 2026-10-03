* Phantom Ripple PSRR — supply noise coupling to XLR output
* ────────────────────────────────────────────────────────────────────────────
* Models the path: phantom supply ripple → V_OPA_RAW → Z_REG1/Q1 regulator
* → V_OPA → R_ZEN1/Z_OSC1 → V_OSC → Dickson pump (×3) → HV RC filter
* → R_GBIAS1/Cc/C8 capsule divider → op-amp IN+ → closed-loop gain → output.
*
* Addresses issue #73: no existing simulation covered this path.
* Validates fixes from #71 (C1 100nF→4.7µF) and #72 (R_REG1 2.2k→1.2k).
*
* Assumptions:
*   - Phantom supply: 100 mVpp open-circuit ripple (AC=100m).
*   - R1||R2 source impedance: 3.405 kΩ (both 6.81 kΩ in parallel).
*   - HV filter: RC mode only (production PCB), R_HV=1MΩ, C9=470nF, fc=0.34Hz.
*   - Z_REG1 rz: parametric per-case (see .control block).
*   - Closed-loop gain: flat/hi-SPL mode (R3=2.2k, R6=5.6k → ×3.55).
*   - Pump small-signal gain: δVBOOST ≈ 3 × δV_OSC (3-stage, quasi-static at 50Hz).
*   - DZ1 (68V) rz << R_HV (1MΩ): pump drives HV filter nearly ideally; DZ1 omitted.
* ────────────────────────────────────────────────────────────────────────────
.title Phantom Ripple PSRR

.options TEMP=27
.include params.inc
.include models/passives.lib

* ────────────────────────────────────────────────────────────────────────────
* PARAMETERS — swept via .control alterparam for before/after comparison
* ────────────────────────────────────────────────────────────────────────────
.param C1_val     = 100n   ; V_OPA_RAW bypass (before fix: 100nF; after: 4.7µF)
.param R_REG1_val = 2.2k   ; Z_REG1 bias resistor (before: 2.2k; after: 1.2k)
.param rz_reg     = 150    ; Z_REG1 dynamic impedance (Ohm): nominal 150, worst 350
.param rz_osc     = 100    ; Z_OSC1 dynamic impedance (Ohm): nominal 100

* ────────────────────────────────────────────────────────────────────────────
* PHANTOM SUPPLY: 100 mVpp open-circuit ripple; R1||R2 series source impedance
* ────────────────────────────────────────────────────────────────────────────
V_ph   PH_SRC      0         DC 25.8  AC 100m
R_src  PH_SRC      V_OPA_RAW 3.405k

* C1: V_OPA_RAW bypass — the primary fix (#71)
C1     V_OPA_RAW   0         {C1_val}

* ────────────────────────────────────────────────────────────────────────────
* Z_REG1 + R_REG1 → V_OPA  (shunt-zener + emitter-follower regulator)
*
* Behavioral model: zener = ideal 24V DC source (AC short) in series with rz.
* Q1 emitter follower = unity-gain VCVS (E_q1) + 25Ω output impedance.
* ────────────────────────────────────────────────────────────────────────────
R_REG1   V_OPA_RAW   VZBASE      {R_REG1_val}
V_zdc    VZBASE_DC   0           DC 24
R_rz1    VZBASE      VZBASE_DC   {rz_reg}

E_q1     V_OPA_SRC   0  VZBASE   VZBASE_DC   1
R_q1out  V_OPA_SRC   V_OPA       25

* V_OPA decoupling (C2=100nF + C6=10µF on V_OPA rail)
C2_dec   V_OPA       0           100n
C6_dec   V_OPA       0           10u

* ────────────────────────────────────────────────────────────────────────────
* R_ZEN1 + Z_OSC1 → V_OSC  (15V oscillator supply)
* ────────────────────────────────────────────────────────────────────────────
R_ZEN1     V_OPA       VZOSC_NODE   6.8k
V_zosc_dc  VZOSC_DC    0            DC 15
R_rz2      VZOSC_NODE  VZOSC_DC     {rz_osc}

* U3 supply decoupling (~100nF typical bypass near CD40106B)
C_voscbyp  VZOSC_NODE  0            100n

* ────────────────────────────────────────────────────────────────────────────
* DICKSON PUMP: behavioral small-signal gain
*
* δVBOOST = 3 × δV_OSC  (3-stage pump; quasi-static at 50Hz << 100kHz clock).
* V_OSC AC component = V(VZOSC_NODE) - V(VZOSC_DC); VZOSC_DC is AC short.
* ────────────────────────────────────────────────────────────────────────────
E_pump   VBOOST   0   VZOSC_NODE   VZOSC_DC   3

* ────────────────────────────────────────────────────────────────────────────
* HV RC FILTER (production PCB: R_HV=1MΩ, C9=470nF, fc=0.34Hz)
* ────────────────────────────────────────────────────────────────────────────
R_HV   VBOOST   HVFILT   1Meg
C9     HVFILT   0        470n

* ────────────────────────────────────────────────────────────────────────────
* CAPSULE BIAS / INPUT COUPLING
*
* Topology: HVFILT → R_GBIAS1 (100MΩ) → CAP_FP (IN+) → Cc (55pF) → CAP_BP
*           CAP_BP → C8 (1nF) → GND  (sets backplate AC ground reference)
*
* HV ripple at HVFILT couples to IN+ through this network. The op-amp
* closed-loop gain then amplifies the IN+ ripple to the output.
* ────────────────────────────────────────────────────────────────────────────
R_GBIAS1   HVFILT    IN_PLUS   {R_GBIAS}
Cc_cap     IN_PLUS   CAP_BP    {Cc}
C8_cap     CAP_BP    0         {C8}
* R_BIAS1 (100MΩ): DC path for CAP_BP (prevents singular matrix); models the
* bootstrapped bias resistor in the real circuit. At 50Hz, 100MΩ >> Xc(C8)=3.18MΩ
* so its effect on the AC transfer function is negligible (<0.15dB).
R_BIAS1    CAP_BP    0         {R_BIAS1}

* ────────────────────────────────────────────────────────────────────────────
* BEHAVIORAL OPA1641 (closed-loop, non-inverting)
* Same model as amp_ac.sp: OL gain 100k, dominant pole 110Hz → GBW 11MHz.
* Feedback: flat/hi-SPL mode (R3=2.2k, R6_default=5.6k → CLG ≈ 3.55).
* ────────────────────────────────────────────────────────────────────────────
Vmid    MIDPT       0           DC 12

Ediff   VDIFF       0   IN_PLUS   IN_MINUS   1
R_gbw   VDIFF       VPOLE        1k
C_gbw   VPOLE       0            1.447u
Eamp    OPA_IDEAL   MIDPT        VPOLE  0    {OPA_OL_GAIN}
R_oout  OPA_IDEAL   OPA_OUT      50

* Feedback network (non-inverting: IN- between R3 to MIDPT and R6 to output)
R3_fb   MIDPT       IN_MINUS     {R3}
R6_fb   OPA_OUT     IN_MINUS     {R6_default}

* Output load (600Ω differential referred to single-ended OPA_OUT)
R_load  OPA_OUT     0            600

* ────────────────────────────────────────────────────────────────────────────
* ANALYSIS
* ────────────────────────────────────────────────────────────────────────────
.ac dec 100 1 1k

.print ac db(V(OPA_OUT)) db(V(IN_PLUS)) db(V(HVFILT)) db(V(V_OPA)) db(V(VZOSC_NODE))

* ────────────────────────────────────────────────────────────────────────────
* CONTROL: 4 cases — before/after fix × nominal/worst-case rz
*
* Reference: 0 dBu = 775 mVrms. Output-referred hum in dBu.
* Phantom ripple: 100 mVpp = 50 mVpeak (AC=100m → V(OPA_OUT) is peak).
* ────────────────────────────────────────────────────────────────────────────
.control
set filetype=ascii

let dbu_ref = 775m

echo "========================================================"
echo "  phantom_ripple_psrr: XLR output hum from phantom"
echo "  supply ripple.  Conditions: 100mVpp phantom ripple,"
echo "  RC HV filter (R=1MΩ, C9=470nF), flat/hi-SPL mode."
echo "========================================================"

* ── Case 1: BEFORE fix — C1=100nF, R_REG1=2.2k, rz=150Ω (nominal Vz) ────
echo ""
echo "--- BEFORE fix: C1=100nF, R_REG1=2.2k, rz=150Ω (nominal) ---"
alterparam C1_val     = 100n
alterparam R_REG1_val = 2.2k
alterparam rz_reg     = 150
reset
ac dec 100 1 1k
meas ac OUT1 find v(OPA_OUT) at=50
let hum1_dbu = 20*log10(abs(OUT1)/dbu_ref)
echo "  Output hum = $&hum1_dbu dBu"

* ── Case 2: BEFORE fix — C1=100nF, R_REG1=2.2k, rz=350Ω (worst +5% Vz) ──
echo ""
echo "--- BEFORE fix, WORST CASE: C1=100nF, R_REG1=2.2k, rz=350Ω (+5% Vz) ---"
alterparam rz_reg     = 350
reset
ac dec 100 1 1k
meas ac OUT2 find v(OPA_OUT) at=50
let hum2_dbu = 20*log10(abs(OUT2)/dbu_ref)
echo "  Output hum = $&hum2_dbu dBu"

* ── Case 3: AFTER fix — C1=4.7µF, R_REG1=1.2k, rz=100Ω (nominal at 1.5mA) ─
echo ""
echo "--- AFTER fix: C1=4.7uF, R_REG1=1.2k, rz=100Ω (nominal at 1.5mA) ---"
alterparam C1_val     = 4.7u
alterparam R_REG1_val = 1.2k
alterparam rz_reg     = 100
reset
ac dec 100 1 1k
meas ac OUT3 find v(OPA_OUT) at=50
let hum3_dbu = 20*log10(abs(OUT3)/dbu_ref)
echo "  Output hum = $&hum3_dbu dBu"

* ── Case 4: AFTER fix, conservative — rz=200Ω (±5% Vz at 1.2k operating point) ─
echo ""
echo "--- AFTER fix, CONSERVATIVE: C1=4.7uF, R_REG1=1.2k, rz=200Ω ---"
alterparam rz_reg     = 200
reset
ac dec 100 1 1k
meas ac OUT4 find v(OPA_OUT) at=50
let hum4_dbu = 20*log10(abs(OUT4)/dbu_ref)
echo "  Output hum = $&hum4_dbu dBu"

* ── Write transfer function from last run for plotting ──────────────────────
wrdata _psrr_sweep.dat v(OPA_OUT) v(IN_PLUS) v(HVFILT) v(V_OPA) v(VZOSC_NODE)

* ── Summary: re-measure from archived plots (ac1..ac4) to compute improvement ─
* Each alterparam+reset creates a new numbered plot; setplot navigates back to
* them and meas extracts the 50Hz value without relying on let-vectors that
* reset clears.
setplot ac1
meas ac S1 find v(opa_out) at=50
setplot ac2
meas ac S2 find v(opa_out) at=50
setplot ac3
meas ac S3 find v(opa_out) at=50
setplot ac4
meas ac S4 find v(opa_out) at=50

let H1 = 20*log10(abs(ac1.S1)/dbu_ref)
let H2 = 20*log10(abs(ac2.S2)/dbu_ref)
let H3 = 20*log10(abs(ac3.S3)/dbu_ref)
let H4 = 20*log10(abs(ac4.S4)/dbu_ref)
let improvement_nom = H1 - H3
let improvement_wc  = H2 - H4

echo ""
echo "========================================================"
echo "  Summary (100mVpp phantom ripple at 50Hz):"
echo "  BEFORE nominal:     $&H1 dBu"
echo "  BEFORE worst:       $&H2 dBu"
echo "  AFTER nominal:      $&H3 dBu"
echo "  AFTER conservative: $&H4 dBu"
echo "  Improvement (nom):  $&improvement_nom dB"
echo "  Improvement (WC):   $&improvement_wc dB"
echo "========================================================"

.endc

.end
