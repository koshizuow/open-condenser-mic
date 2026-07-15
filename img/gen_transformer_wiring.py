#!/usr/bin/env python3
"""Generate img/transformer_wiring.png.

Run from the project root:
    python img/gen_transformer_wiring.py
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

W, H = 13.5, 6.66          # figure size in inches (matches original 1350×666 @ 100 dpi)

fig, ax = plt.subplots(figsize=(W, H))
fig.patch.set_facecolor('white')
ax.set_facecolor('white')
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.set_aspect('equal')
ax.axis('off')

# ── colours ─────────────────────────────────────────────────────────────────
RED  = '#cc0000'
BLUE = '#1155cc'
GOLD = '#997700'
GRAY = '#888888'
DARK = '#333333'

# ── core ────────────────────────────────────────────────────────────────────
CL   = 5.50   # left bar left edge
CLW  = 0.40   # bar width
GAP  = 0.40   # gap between bars
CR   = CL + CLW + GAP          # right bar left edge  = 6.30
CRR  = CR + CLW                # right bar right edge = 6.70
CTOP = 5.45
CBOT = 0.65

for x0 in (CL, CR):
    ax.fill([x0, x0+CLW, x0+CLW, x0], [CBOT, CBOT, CTOP, CTOP],
            color='#555555', zorder=2)

ax.text((CL+CLW + CR) / 2, (CTOP+CBOT) / 2, '3:1',
        ha='center', va='center', fontsize=13, color=DARK, zorder=4,
        bbox=dict(boxstyle='square,pad=0.3', fc='white', ec='#aaaaaa', lw=1.5))

# ── coil semicircles ─────────────────────────────────────────────────────────
# Each turn is a semicircular bump + a spine line connecting them.
# Secondary: bumps face LEFT,  spine at x=CL   (touches left core bar)
# Primary:   bumps face RIGHT, spine at x=CRR  (touches right core bar)

R = 0.64
LW_COIL = 2.2

# Secondary: 3 turns; S1=top, S2=centre tap (after 1st turn), S3=bottom
S1_Y = 4.83
sec_yc = [S1_Y - R - i*2*R for i in range(3)]   # arc centres y: [4.19, 2.91, 1.63]
S2_Y   = sec_yc[0] - R                           # 3.55 — junction between turns 1 & 2
S3_Y   = sec_yc[2] - R                           # 0.99 — bottom of turn 3

# Primary: 2 turns; P1=top, P2=bottom — aligned to wire positions
P1_Y = 4.19
pri_yc = [P1_Y - R - i*2*R for i in range(2)]   # arc centres y: [3.55, 2.27]
P2_Y   = pri_yc[1] - R                           # 1.63

# Spine lines (vertical, behind the arcs)
ax.plot([CL,  CL],  [S3_Y, S1_Y], color=DARK, lw=LW_COIL, zorder=2)
ax.plot([CRR, CRR], [P2_Y, P1_Y], color=DARK, lw=LW_COIL, zorder=2)

# Semicircular arcs (drawn on top of spine)
# Secondary: left-facing → arc from 90° to 270° counterclockwise (through 180°)
for yc in sec_yc:
    ax.add_patch(mpatches.Arc((CL, yc), 2*R, 2*R,
                              theta1=90, theta2=270,
                              edgecolor=DARK, linewidth=LW_COIL, zorder=3))

# Primary: right-facing → arc from 270° to 90° counterclockwise (through 0°)
for yc in pri_yc:
    ax.add_patch(mpatches.Arc((CRR, yc), 2*R, 2*R,
                              theta1=270, theta2=90,
                              edgecolor=DARK, linewidth=LW_COIL, zorder=3))

# ── wires ────────────────────────────────────────────────────────────────────
LW_WIRE = 2.5

def hw(y, x0, x1, color, lw=LW_WIRE, ls='-'):
    ax.plot([x0, x1], [y, y], color=color, lw=lw, ls=ls,
            solid_capstyle='butt', zorder=5)

XL = 0.75    # left label end
XR = 12.20   # right label end

# Wires connect at the spine (CL for secondary, CRR for primary)
hw(S1_Y, XL, CL,  RED)
hw(S2_Y, XL, CL,  BLUE)
hw(S3_Y, XL + 0.30, CL, DARK, ls='--')
hw(P1_Y, CRR, XR, GRAY)
hw(P2_Y, CRR, XR, GOLD)

# ── text labels ───────────────────────────────────────────────────────────────
FS_MAIN  = 11.0
FS_COLOR = 10.0
DY_COLOR = -0.37   # colour name sits this far below the wire label

def label_l(y, main, cname, ccolor):
    ax.text(XL - 0.12, y, main, ha='right', va='center',
            fontsize=FS_MAIN, color=DARK)
    ax.text(XL - 0.12, y + DY_COLOR, cname, ha='right', va='center',
            fontsize=FS_COLOR, color=ccolor, fontstyle='italic', fontweight='bold')

def label_r(y, main, cname, ccolor):
    ax.text(XR + 0.12, y, main, ha='left', va='center',
            fontsize=FS_MAIN, color=DARK)
    ax.text(XR + 0.12, y + DY_COLOR, cname, ha='left', va='center',
            fontsize=FS_COLOR, color=ccolor, fontstyle='italic', fontweight='bold')

label_l(S1_Y, 'TX_DRV · S1',             'Red',   RED)
label_l(S2_Y, 'GND · S2 (centre tap)',   'Blue',  BLUE)
label_l(S3_Y, '— · S3 (leave floating)', 'Black', DARK)

label_r(P1_Y, 'XLR_HOT · pin 2 · P1',  'White',  GRAY)
label_r(P2_Y, 'XLR_COLD · pin 3 · P2', 'Yellow', GOLD)

# ── section titles ────────────────────────────────────────────────────────────
SEC_TITLE_X = (XL + CL) / 2
PRI_TITLE_X = (CRR + XR) / 2
TITLE_Y     = CTOP + 0.52
SUB_Y       = TITLE_Y - 0.42

ax.text(SEC_TITLE_X, TITLE_Y, 'Secondary',
        ha='center', va='center', fontsize=13, color=DARK)
ax.text(SEC_TITLE_X, SUB_Y,   '(3-turn, driven)',
        ha='center', va='center', fontsize=11, color=DARK)

ax.text(PRI_TITLE_X, TITLE_Y, 'Primary',
        ha='center', va='center', fontsize=13, color=DARK)
ax.text(PRI_TITLE_X, SUB_Y,   '(XLR output)',
        ha='center', va='center', fontsize=11, color=DARK)

# ── caption ───────────────────────────────────────────────────────────────────
ax.text(W / 2, 0.18,
        'Neutrik NTE10/3 — secondary driven (OPA1641), primary is XLR output'
        ' — 3:1 step-down',
        ha='center', va='center', fontsize=10, color='#555555', fontstyle='italic')

# ── save ─────────────────────────────────────────────────────────────────────
out = 'img/transformer_wiring.png'
fig.savefig(out, dpi=100, bbox_inches='tight', facecolor='white')
print(f'Saved {out}')
