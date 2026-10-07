"""BOM LCSC part-number sanity checks.

Catches the most common regression: editing gen_bom.py and accidentally
introducing an empty, duplicate, or known-wrong LCSC number.

Run: pytest pcb/test_bom.py -v
"""

import re

import pytest

import gen_bom

VALID_LCSC = re.compile(r"^C\d+$")

# LCSC numbers documented in gen_bom.py comments as mapping to wrong parts
# in JLCPCB. Checked here so they can never be silently reintroduced.
KNOWN_WRONG = {
    "C328784",  # OPA1641 slot → wrong part
    "C8541",    # BAT54S slot → SS8550 PNP TH
    "C460671",  # 15V zener slot → wrong part
    "C7427990", # 68V zener slot → no 3D model in JLCPCB viewer
    "C26022",   # 6.8k 0402 slot → 4.7kΩ 0805
    "C25900",   # 47k 0402 slot → 4.7kΩ
    "C1554",    # 100p C0G slot → 20pF
    "C25905",   # 470k 0402 slot → 5.1kΩ
    "C111566",  # ESD9B5.0ST5G 5V TVS → clamps the phantom-fed XLR lines (#93)
}


def test_all_lcsc_valid_format():
    """Every LCSC value must be a non-empty 'C' followed by digits."""
    bad = {k: v for k, v in gen_bom.LCSC.items() if not VALID_LCSC.match(v)}
    assert not bad, f"Invalid LCSC# format: {bad}"


def test_no_duplicate_lcsc_numbers():
    """No two (value, footprint) keys may share the same LCSC number."""
    seen: dict[str, tuple] = {}
    dupes = {}
    for key, part_no in gen_bom.LCSC.items():
        if part_no in seen:
            dupes[part_no] = (seen[part_no], key)
        else:
            seen[part_no] = key
    assert not dupes, f"Duplicate LCSC numbers: {dupes}"


def test_no_empty_key_fields():
    """No key should have an empty value or footprint string."""
    bad = [(v, fp) for (v, fp) in gen_bom.LCSC if not v.strip() or not fp.strip()]
    assert not bad, f"Empty value or footprint in LCSC key: {bad}"


def test_known_wrong_numbers_not_used():
    """Numbers documented as wrong/bad in JLCPCB must not appear in the BOM."""
    used = KNOWN_WRONG & set(gen_bom.LCSC.values())
    assert not used, f"Known-wrong LCSC number(s) in BOM: {sorted(used)}"


def test_r6_variants_valid_format():
    """R6_DEFAULT and R6_HI_GAIN LCSC numbers must also be valid."""
    for name, info in [("R6_DEFAULT", gen_bom.R6_DEFAULT), ("R6_HI_GAIN", gen_bom.R6_HI_GAIN)]:
        assert VALID_LCSC.match(info["lcsc"]), (
            f"Invalid LCSC# for {name}: {info['lcsc']!r}"
        )
