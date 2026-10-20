"""Tiny synthetic statements, one per layout, built in code (no real data).

SOA2 (CRN layout) and SOA7 (ICORE short) share three UPI payers, so they
should form a ring. VPAs are truncated in the CRN layout exactly like the
real data ('ramesh.kuma' vs 'ramesh.kumar@okaxis').
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

SHARED = ["ramesh.kumar@okaxis", "9876543210@ybl", "priya.sharma1@oksbi"]


def _pstd(ts: str) -> str:
    return pd.Timestamp(ts).strftime("%d%b%Y:%H:%M:%S").upper()


@pytest.fixture
def crn_df() -> pd.DataFrame:
    """Layout A: randomised person-name headers for CRN and D/C."""
    rows = []
    for i, vpa in enumerate(SHARED + ["testpayer03@ybl", "other.payer@ibl"]):
        rows.append(["1111222233", "Test Holder A", "100000001", "2018-06-13", "2019-10-03", "C", 2000.0 + i,
                     f"UPI/{vpa.split('@')[0][:11] if '@' in vpa else vpa}/{100000000000 + i}/Payment fro", None, None])
    rows.append(["1111222233", "Test Holder A", "100000001", "2018-06-13", "2020-01-01", "D", 9000.0,
                 "MMT/IMPS/123456789012/BotuNaveen/TEST0000005", None, None])
    rows.append(["1111222233", "Test Holder A", "100000001", "2018-06-13", "2020-01-02", "D", 500.0,
                 "O/W RTN:37:FUNDS INSUFFICIENT", None, "Zone Serial [ 319]"])
    return pd.DataFrame(rows, columns=["Account No", "Account Name", "Header Person A", "A/c Open Date", "TXN DATE",
                                       "Header Person B", "AMOUNT", "TXN PARTICULARS", "REF NUMBER", "TXN REMARKS"])


@pytest.fixture
def debit_credit_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Customer_Name": ["Test Holder C"] * 3,
        "Account_Number": ["888877776666"] * 3,
        "IFSC_Code": ["TEST0000003"] * 3,
        "Date_of_transaction": ["10-02-2020", "18-07-2019", "01-01-2021"],
        "Transaction_type": ["T", "T", "T"],
        "Instrument_Number": [None, None, None],
        "Narration": ["MMT/IMPS/890000000009/didde/TEST0000006,", "TXN-AAAAAAAAA5",
                      "UPI/210000000001/Payment from Ph/9000000001@ybl/St,ate Bank Of I"],
        "Debit_amount": [None, "75,000.25", None],
        "Credit_Amount": ["100000.50", None, "5000"],
        "Line_Balance": ["50000", "0", "1"],
    })


@pytest.fixture
def icore_short_df() -> pd.DataFrame:
    base = pd.Timestamp("2020-12-17 09:00:00")
    rows = []
    # credits from the shared payers, each followed by a fast debit
    for i, vpa in enumerate(SHARED):
        t = base + pd.Timedelta(hours=3 * i)
        rows.append(["999988887777", "Test Holder B", f"S{i}C", "44001", "0", "10000", "1", None,
                     f"UPI/{200000000000 + i}/Payment from Ph/{vpa}/State Bank Of", _pstd(t)])
        rows.append(["999988887777", "Test Holder B", f"S{i}D", "43001", "9500", "0", "1", f"{300000000000 + i}//4000000000000001",
                     f"MMT/IMPS/{400000000000 + i}/Mule Next/TEST0000002", _pstd(t + pd.Timedelta(minutes=30))])
    rows.append(["999988887777", "Test Holder B", "SX", "45001", "0", "1000", "1", None, "TXN-AAAAAAAAA6",
                 _pstd(base + pd.Timedelta(days=1, hours=-7))])  # 02:00 night txn
    return pd.DataFrame(rows, columns=["Ac_No", "AC_Name", "Tran_ID", "Tran_Date", "Dr_Amt", "Cr_Amt", "Balance", "Rmks", "Narration", "pstd_dt"])


@pytest.fixture
def icore_full_df() -> pd.DataFrame:
    base = pd.Timestamp("2020-09-19 09:29:30")
    rows = []
    for i in range(4):
        rows.append(["106", f"70000000{i}", f"20000000000{i}", "Test Holder F", f"T{i}", "44002", "T", "CI", None, None,
                     "0" if i % 2 == 0 else "1000", "1000" if i % 2 == 0 else "0", "5", "TXN-AAAAAAAAA7", "TXN-AAAAAAAAA8",
                     _pstd(base + pd.Timedelta(hours=i)), "INR", "x", "SYSTEM", "SYSTEM"])
    return pd.DataFrame(rows, columns=["Init_SOL", "Cust_ID", "Ac_No", "AC_Name", "Tran_ID", "Tran_Date", "Tran_Type", "Sub_Type",
                                       "Inst_Type", "Inst_Num", "Dr_Amt", "Cr_Amt", "Balance", "Rmks", "Narration", "pstd_dt",
                                       "Crncy", "value_dt", "mkr_emp_id", "chk_emp_id"])


@pytest.fixture
def ledger_df() -> pd.DataFrame:
    return pd.DataFrame({
        "CUSTOMER ID": ["1000000002", "1000000003"],
        "CUSTOMER NAME": ["Test Holder D"] * 2,
        "ACCOUNT NO": ["10000000000004", "10000000000005"],
        "TRANSACTION DATE": ["2025-04-20", "2027-08-19"],
        "NARRATION": ["TXN-AAAAAAAAA1", "TXN-AAAAAAAAA2"],
        "DEBIT AMOUNT": [None, "100"],
        "CREDIT AMOUNT": ["200000.75", None],
        "BALANCE": ["1", "2"],
    })


@pytest.fixture
def wide_df() -> pd.DataFrame:
    cols = ["Account No", "Account Name", "CRN CIF", "A/c Open Date", "A/c Closed Date", "TXN DATE", "VALUE DATE", "PSTD DATE",
            "TXN TYP", "TXN SUB TYP", "Dr Cr", "AMOUNT", "FX AMT", "TXN CCY", "EXCH RATE", "EOD Balance", "Available Balance",
            "Lien Amt", "TXN PARTICULARS", "REF NUMBER", "SCHEME DESCRIPTION", "TXN ID", "TXN SEQ NO", "MOP", "A/C Status", "PAN DETAILS"]
    r1 = ["1000000006", "Test Holder E", "100000007", "2021-11-29", None, "2024-07-15", "2023-12-05", "2019-12-05", "T", "CI", "C",
          "2500.10", "1", "INR", "1", "1", "1", "0", "TXN-AAAAAAAAA3", "REF1", None, "TXN-AAAAAAAAA4", "S7", "SINGLY",
          "Dormant & Total Freeze", "ABCDE1234F"]
    r2 = list(r1)
    r2[0], r2[10], r2[11] = "1000000008", "D", "500"
    blank = [None] * len(cols)
    return pd.DataFrame([r1, blank, r2], columns=cols)


@pytest.fixture
def raw_dir(tmp_path: Path, crn_df, debit_credit_df, icore_short_df, icore_full_df, ledger_df, wide_df) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    crn_df.to_excel(raw / "2_SOA.xlsx", sheet_name="Account Statement - CRN", index=False)
    debit_credit_df.to_excel(raw / "6_SOA.xlsx", sheet_name="Main Sheet", index=False)
    icore_short_df.to_excel(raw / "7_SOA.xlsx", sheet_name="ICORE_STMT_000000000001", index=False)
    icore_full_df.to_excel(raw / "14_SOA.xlsx", sheet_name="ICORE_STMT_000000000002", index=False)
    ledger_df.to_excel(raw / "1_SOA.xlsx", sheet_name="Sheet1", index=False)
    wide_df.to_excel(raw / "3_SOA.xlsx", sheet_name="main file", index=False)
    (raw / "~$25_SOA.xlsx").write_bytes(b"lock file, not a workbook")
    return raw


@pytest.fixture
def pipeline_dirs(tmp_path: Path, raw_dir: Path) -> dict:
    return {
        "raw_dir": raw_dir,
        "processed_dir": tmp_path / "processed",
        "db_path": tmp_path / "trace360.duckdb",
        "synthetic_dir": tmp_path / "synthetic",
    }
