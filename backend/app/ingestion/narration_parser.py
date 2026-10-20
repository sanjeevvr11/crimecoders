"""Parse bank narrations into channel + counterparty.

Only the channel and a counterparty key are extracted; free-text notes are
discarded. Counterparty keys are prefixed by type so they never collide:

    upi:<vpa local part, lowercased, cut to UPI_KEY_LEN>
    acct:<digits>
    ifsc:<IFSC>[:<name>]
    name:<normalised name>
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app import config

IFSC_RE = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
TOKEN_RE = re.compile(r"^TXN-[A-Z0-9]{10}$")
TOKEN_CHANNEL_RE = re.compile(r"(UPI|IMPS|NEFT|RTGS|ATM|CHQ|CLG|CASH)")
RRN_RE = re.compile(r"^\d{12}$")
ACCT_RE = re.compile(r"\d{9,18}")
RMKS_REF_RE = re.compile(r"^(\d{12})//(\d{16})$")

# segments that are boilerplate, never a counterparty name
_NOISE_SEGMENTS = {
    "", "upi", "na", "nil", "remark", "remarks", "others", "payment", "pay", "fund transfer",
    "payment from ph", "payment fro", "no remarks", "sent", "received",
}


@dataclass
class ParsedNarration:
    channel: str = "UNKNOWN"
    counterparty_key: str | None = None
    counterparty_type: str = "none"
    counterparty_bank: str | None = None
    rrn: str | None = None
    parsed: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def normalise_vpa(value: str) -> str | None:
    """'Sample.Payee9@okaxis' -> 'sample.paye' (local part, lowercased, cut)."""
    v = value.strip().lower()
    local = v.split("@", 1)[0]
    local = re.sub(r"[^a-z0-9._-]", "", local).strip("._-")
    if len(local) < 3:
        return None
    return local[: config.UPI_KEY_LEN]


def normalise_name(value: str) -> str | None:
    v = re.sub(r"[^a-z ]", " ", value.lower())
    v = re.sub(r"\s+", " ", v).strip()
    if len(v) < 3 or v in _NOISE_SEGMENTS or "by user" in value.lower():
        return None
    return v


def _bank_from_ifsc(ifsc: str | None) -> str | None:
    return ifsc[:4] if ifsc else None


def _upi(p: ParsedNarration, vpa_or_name: str, bank: str | None = None) -> ParsedNarration:
    p.channel = "UPI"
    p.parsed = True
    key = normalise_vpa(vpa_or_name)
    if key:
        p.counterparty_key = f"upi:{key}"
        p.counterparty_type = "upi"
    if bank:
        p.counterparty_bank = bank.strip() or None
    return p


def _imps_like(p: ParsedNarration, channel: str, segments: list[str]) -> ParsedNarration:
    """MMT/IMPS/<rrn>/<name?>/<IFSC or bank> and similar slash-separated payloads."""
    p.channel = channel
    p.parsed = True
    ifsc = None
    name = None
    acct = None
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if RRN_RE.match(seg):
            p.rrn = p.rrn or seg
            continue
        m = IFSC_RE.search(seg.upper())
        if m and len(seg) <= 12:
            ifsc = m.group(1)
            continue
        if seg.isdigit() and 9 <= len(seg) <= 18:
            acct = seg
            continue
        if name is None:
            name = normalise_name(seg)
    if acct:
        p.counterparty_key, p.counterparty_type = f"acct:{acct}", "account"
    elif ifsc:
        p.counterparty_key = f"ifsc:{ifsc}" + (f":{name}" if name else "")
        p.counterparty_type = "ifsc"
    elif name:
        p.counterparty_key, p.counterparty_type = f"name:{name}", "name"
    p.counterparty_bank = _bank_from_ifsc(ifsc)
    return p


def parse_narration(narration: object, remarks: object = None) -> ParsedNarration:
    p = ParsedNarration()
    if narration is None or (isinstance(narration, float)) or str(narration).strip() == "":
        return p
    raw = str(narration).strip()
    # file 6 wraps long narrations by inserting a comma; drop them before parsing
    text = raw.replace(",", "")
    up = text.upper()

    if TOKEN_RE.match(up):
        if config.RECOVER_CHANNEL_FROM_TOKENS:
            m = TOKEN_CHANNEL_RE.search(up[4:])
            if m:
                p.channel = m.group(1)
        return _with_remarks(p, remarks)

    segs = text.split("/")

    # ---- UPI -------------------------------------------------------------
    if up.startswith(("REV UPI/", "UPI/RVSL")):
        p.channel, p.parsed = "UPI", True
        return p
    if up.startswith("UPI/") and len(segs) >= 3:
        if RRN_RE.match(segs[1].strip()):
            # ICORE / file 6: UPI/<rrn>/<note>/<vpa>/<bank>
            p.rrn = segs[1].strip()
            vpa = segs[3] if len(segs) > 3 else ""
            bank = segs[4] if len(segs) > 4 else None
            if not vpa.strip():
                p.channel, p.parsed = "UPI", True
                return p
            return _upi(p, vpa, bank)
        if RRN_RE.match(segs[2].strip()):
            # CRN statement: UPI/<vpa-or-name, truncated>/<rrn>/<note>
            p.rrn = segs[2].strip()
            return _upi(p, segs[1])
    if up.startswith("UPI"):
        p.channel, p.parsed = "UPI", True
        return p

    # ---- IMPS ------------------------------------------------------------
    if up.startswith("MMT/IMPS/"):
        return _imps_like(p, "IMPS", segs[2:])
    m = re.match(r"^IB\s*IMPS\s+(?:SENT\s+)?TO\s+(\S+)", up)
    if m:
        p.channel, p.parsed = "IMPS", True
        tgt = m.group(1).strip("/")
        if tgt.isdigit():
            p.counterparty_key, p.counterparty_type = f"acct:{tgt}", "account"
        else:
            key = normalise_vpa(tgt)
            if key:
                p.counterparty_key, p.counterparty_type = f"upi:{key}", "upi"
        return p
    if "IMPS" in up and ("CHRG" in up or "CHG" in up):
        p.channel, p.parsed = "CHARGES", True
        return p
    if up.startswith(("MMT IMPS", "IMPS")):
        p.channel, p.parsed = "IMPS", True
        return p

    # ---- internal / NEFT / RTGS -------------------------------------------
    if up.startswith("INF/NEFT/"):
        return _imps_like(p, "NEFT", segs[2:])
    if up.startswith(("INF/INFT/", "BIL/INFT/")):
        return _imps_like(p, "OTHER", segs[2:])
    if up.startswith("INF/"):
        return _imps_like(p, "OTHER", segs[1:])
    if up.startswith("BIL/"):
        p.channel, p.parsed = "OTHER", True
        return p
    if up.startswith(("NEFT", "MB:SENT NEFT", "MB:RECEIVED NEFT")) or "NEFT" in up[:20]:
        p.channel, p.parsed = "NEFT", True
        m = IFSC_RE.search(up)
        if m:
            p.counterparty_key, p.counterparty_type = f"ifsc:{m.group(1)}", "ifsc"
            p.counterparty_bank = _bank_from_ifsc(m.group(1))
        return p
    if up.startswith("RTGS") or "RTGS" in up[:20]:
        p.channel, p.parsed = "RTGS", True
        return p
    if up.startswith(("MB:", "MB ", "IB:", "IB ", "RECEIVED FRO")):
        p.channel, p.parsed = "IMPS", True
        m = re.search(r"(\d{9,18})", up)
        if m and "REF" not in up:
            p.counterparty_key, p.counterparty_type = f"acct:{m.group(1)}", "account"
        return p

    # ---- cheques / clearing ---------------------------------------------------
    if up.startswith(("BY CLG", "TO CLG", "CLG/", "O/W RTN", "I/W RTN", "CLG")):
        p.channel, p.parsed = "CLG", True
        return p
    if up.startswith("CASA IP-"):
        p.channel, p.parsed = "OTHER", True
        m = re.search(r"-(\d{9,18})(?:/|$)", text)
        if m:
            p.counterparty_key, p.counterparty_type = f"acct:{m.group(1)}", "account"
        return p

    # ---- cash / ATM / charges ------------------------------------------------
    if up.startswith(("ATM", "ATL/", "CAM/", "NFS/", "CASH WITHDRA")) or "ATM" in up[:10]:
        p.channel, p.parsed = "ATM", True
        return p
    if up.startswith(("CASH", "BY CASH", "TO CASH")):
        p.channel, p.parsed = "CASH", True
        return p
    if up.startswith(("CHRG", "MOB ALRT", "DBT CARD CHG", "SGST", "CGST", "IGST")) or " CHG" in up or "CHRG" in up:
        p.channel, p.parsed = "CHARGES", True
        return p
    if up.startswith("ACH/"):
        p.channel, p.parsed = "ACH", True
        return p
    if up.startswith(("IIN/", "ONETIME")):
        p.channel, p.parsed = "OTHER", True
        return p
    return _with_remarks(p, remarks)


def _with_remarks(p: ParsedNarration, remarks: object) -> ParsedNarration:
    """ICORE Rmks like '<rrn>//<16-digit card or account>' add a reference only."""
    if remarks is None or isinstance(remarks, float):
        return p
    m = RMKS_REF_RE.match(str(remarks).strip())
    if m:
        p.rrn = p.rrn or m.group(1)
    return p
