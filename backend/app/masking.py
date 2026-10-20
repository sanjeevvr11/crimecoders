"""Masking for anything that leaves the API: names, account numbers, PAN, VPAs.

Rule: show only the last 4 characters of an identifier. Counterparty node ids
(which embed VPAs/phone numbers) are replaced by stable hashed references.
"""
from __future__ import annotations

import hashlib
import re

PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
WORD_RE = re.compile(r"[A-Za-z0-9@._-]+")
# banking vocabulary that is safe to show verbatim in narrations
SAFE_WORDS = {
    "UPI", "MMT", "IMPS", "INF", "INFT", "NEFT", "RTGS", "BIL", "CLG", "ATM", "CAM", "ACH", "NA", "REV", "RVSL",
    "CHRG", "CHG", "RTN", "FUNDS", "INSUFFICIENT", "BY", "INST", "TO", "FROM", "PAYMENT", "FRO", "SENT", "RECEIVED",
    "REF", "CASH", "WITHDRAWAL", "WITHDRA", "DEBIT", "CREDIT", "CARD", "ANNUAL", "FEE", "FOR", "BANK", "OF", "LTD",
    "STATE", "INDIA", "TRANSFER", "FUND", "REMARKS", "NO", "USER", "TRF", "TRFR", "CHQ", "MOB", "ALRT", "DBT",
    "SGST", "CGST", "IGST", "REVERSAL", "CASA", "IP", "ONETIME", "SETU", "ZONE", "SERIAL", "AT", "PAY",
}


def mask(value: object, keep: int = 4) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() == "nan":
        return None
    if len(s) <= keep:
        return "*" * len(s)
    return "*" * (len(s) - keep) + s[-keep:]


def _mask_word(m: re.Match) -> str:
    w = m.group(0)
    if w.upper() in SAFE_WORDS or len(w) <= 4:
        return w
    return mask(w)


def mask_text(text: object) -> str | None:
    """Mask a free-text narration word by word, keeping banking vocabulary.

    Anything longer than 4 characters that is not a known banking term (names,
    VPAs, account/reference numbers) is cut to its last 4 characters.
    """
    if text is None:
        return None
    s = str(text)
    if s.lower() in ("nan", "<na>"):
        return None
    if re.fullmatch(r"TXN-[A-Z0-9]{10}", s):
        return s  # opaque token, nothing personal
    s = PAN_RE.sub(lambda m: mask(m.group(0)), s)
    return WORD_RE.sub(_mask_word, s)


def node_ref(node_id: str, is_subject: bool) -> str:
    if is_subject:
        return node_id
    return "CP-" + hashlib.sha1(node_id.encode()).hexdigest()[:10]


def node_label(node_id: str, is_subject: bool) -> str:
    if is_subject:
        return node_id
    kind, _, ident = node_id.partition(":")
    if kind == "ifsc":
        ifsc, _, name = ident.partition(":")
        return f"ifsc:{ifsc[:4]}…{mask(name) or ''}"
    return f"{kind}:{mask(ident)}"
