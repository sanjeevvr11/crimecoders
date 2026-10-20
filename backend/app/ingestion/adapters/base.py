"""Adapter base class: one subclass per statement layout."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from app.ingestion import normalizer
from app.ingestion.narration_parser import parse_narration
from app.ingestion.schema import conform


@dataclass
class SourceContext:
    file_no: int
    source_file: str
    source_sheet: str

    @property
    def account_id(self) -> str:
        # Each statement file is one subject account. Account numbers are
        # anonymised per row in most files, so the file number is the identity.
        return f"SOA{self.file_no}"


@dataclass
class AdapterResult:
    transactions: pd.DataFrame
    account: dict


class BaseAdapter(ABC):
    name: str = "base"
    time_reliable: bool = False

    @classmethod
    @abstractmethod
    def matches(cls, df: pd.DataFrame) -> bool: ...

    @abstractmethod
    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a frame with direction, amount, raw_narration, raw_remarks,
        raw_date, txn_ts, holder_name, account_number (raw, per row)."""

    def to_canonical(self, df: pd.DataFrame, ctx: SourceContext) -> AdapterResult:
        df = df.loc[~normalizer.is_blank_row(df)].copy()
        df["__row_idx"] = range(len(df))
        ext = self.extract(df)
        ext["row_idx"] = df["__row_idx"].to_numpy()
        ext = ext.loc[ext["direction"].notna()].copy()

        parsed = [
            parse_narration(n, r)
            for n, r in zip(ext["raw_narration"].astype(object), ext.get("raw_remarks", pd.Series(None, index=ext.index)).astype(object))
        ]
        ext["channel"] = [p.channel for p in parsed]
        ext["counterparty_key"] = [p.counterparty_key for p in parsed]
        ext["counterparty_type"] = [p.counterparty_type for p in parsed]
        ext["counterparty_bank"] = [p.counterparty_bank for p in parsed]

        ext["account_id"] = ctx.account_id
        ext["source_file"] = ctx.source_file
        ext["source_sheet"] = ctx.source_sheet
        ext["time_reliable"] = self.time_reliable
        if not self.time_reliable:
            ext["txn_ts"] = pd.NaT
        ext["txn_uid"] = [f"{ctx.account_id}-{i:06d}" for i in ext["row_idx"]]

        acct_nums = ext["account_number"].dropna().astype(str).str.strip()
        constant_number = acct_nums.iloc[0] if len(acct_nums) and acct_nums.nunique() == 1 else None
        names = ext["holder_name"].dropna().astype(str).str.strip()
        account = {
            "account_id": ctx.account_id,
            "source_file": ctx.source_file,
            "source_sheet": ctx.source_sheet,
            "layout": self.name,
            "holder_name": names.mode().iloc[0] if len(names) else None,
            "account_number": constant_number,
            "time_reliable": self.time_reliable,
            "n_rows": int(len(ext)),
        }
        return AdapterResult(conform(ext), account)


def find_column(df: pd.DataFrame, *candidates: str) -> str | None:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def col_or_na(df: pd.DataFrame, *candidates: str) -> pd.Series:
    c = find_column(df, *candidates)
    return df[c] if c is not None else pd.Series(pd.NA, index=df.index, dtype="string")
