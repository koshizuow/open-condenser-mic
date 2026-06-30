* OPA1641 Mic — Low-Frequency Response: R_BIAS1 = 100M vs 500M
* Full signal path: capsule Cc (55pF) → R_GBIAS (47M+47M) at CAP_FP
*                   → C8 (10nF) → VPLUS (IN+) → R_BIAS1 → V_MID
* Shows effect of R_BIAS1 on bass -3dB frequency.
* ---------------------------------------------------------------------------
.title OPA1641 Bias Resistor Comparison

.options TEMP=27
.include models/passives.lib

* ---------------------------------------------------------------------------
* POWER / DC RAILS
* ---------------------------------------------------------------------------
Vreg  NET_24V  0  DC 24
R5    NET_24V  NET_VMID  470k
R6    NET_VMID  0         470k     ; V_MID = 12V
C3    NET_VMID  0         10u      ; V_MID stiff (AC ground)

* HV supply (phantom regulated ≈ 56V), AC grounded via C9
Vhv   NET_HV  0  DC 56
* C9 is implicit via Vhv being ideal voltage source

* V_OPA (24V supply rail), AC ground reference for closed-loop
V_OPA NET_VOPA  0  DC 24

* ---------------------------------------------------------------------------
* CAPSULE SOURCE
* Vcap = 1 AC (normalized), in series with capsule capacitance Cc = 55pF
* ---------------------------------------------------------------------------
Vcap  CAP_HOT  CAP_BOT  AC 1  DC 0
Cc    CAP_BOT  0         55p

* Capsule hot connects to CAP_FP node
Rconn  CAP_HOT  CAP_FP  1    ; 1Ω wire resistance

* ---------------------------------------------------------------------------
* HV POLARIZATION BIAS: R_GBIAS1 + R_GBIAS2 in series (47M each = 94M total)
* HV_FILT is AC-grounded (C9 decouples HV)
* ---------------------------------------------------------------------------
R_GBIAS1  NET_HV  HV_MID  47Meg
R_GBIAS2  HV_MID  CAP_FP  47Meg

* ---------------------------------------------------------------------------
* INPUT COUPLING: C8 = 10nF (CAP_FP → VPLUS = OPA1641 IN+)
* ---------------------------------------------------------------------------
C8  CAP_FP  VPLUS  10n

* ---------------------------------------------------------------------------
* R_BIAS1: VPLUS → V_MID  (DC bias for IN+)
* COMPARE: 100M (current) vs 500M (proposed)
* Change RBIAS value here:
* ---------------------------------------------------------------------------
.param RBIAS = 100Meg
R_BIAS1  VPLUS  NET_VMID  {RBIAS}

* ---------------------------------------------------------------------------
* BEHAVIORAL OPA1641
* Open-loop gain 100k, single pole at 110 Hz (GBW = 11 MHz)
* IN+ = VPLUS, IN- = VINV
* ---------------------------------------------------------------------------
Ediff   VDIFF     0        VPLUS   VINV   1
R_gbw   VDIFF     VPOLE    1k
C_gbw   VPOLE     0        1.447u   ; f_pole = 1/(2π*1k*1.447µ) ≈ 110 Hz
Eamp    NET_OPA_IDEAL  0          VPOLE   0   100k
R_oout  NET_OPA_IDEAL  SIG_OUT    50

* Feedback: 130k (R7) from output to IN-; 2.2k (R3) from V_MID to IN-
R_fb    SIG_OUT   VINV    130k
R_in_m  NET_VMID  VINV    2.2k

* ---------------------------------------------------------------------------
* OUTPUT
* ---------------------------------------------------------------------------
R8   SIG_OUT     OPA_R8     100
C6   OPA_R8      XFMR_IN    10u

X_XFMR  XFMR_IN  0  XLR_P2  XLR_P3  NTE10_3
R_load   XLR_P2   XLR_P3  600
R_cm1    XLR_P2   0        10Meg
R_cm2    XLR_P3   0        10Meg

Ediff_out  XLR_DIFF  0  XLR_P2  XLR_P3  1

* ---------------------------------------------------------------------------
* SWEEP: AC dec 100 pts/decade from 5 Hz to 20 kHz
* Run once with RBIAS=100M, once with RBIAS=500M (edit .param above)
* ---------------------------------------------------------------------------
.ac dec 100 5 20k

.print ac db(V(XLR_DIFF)) db(V(VPLUS)) db(V(SIG_OUT))

* Convenience: also print phase
.print ac phase(V(XLR_DIFF))

.end
