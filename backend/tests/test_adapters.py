import pandas as pd
import pytest

from app.ingestion.adapters.base import SourceContext
from app.ingestion.adapters.crn_statement import CrnStatementAdapter
from app.ingestion.adapters.debit_credit import DebitCreditAdapter
from app.ingestion.adapters.icore_full import IcoreFullAdapter
from app.ingestion.adapters.icore_short import IcoreShortAdapter
from app.ingestion.adapters.misc import CustomerLedgerAdapter, WideExtractAdapter
from app.ingestion.layout_detector import UnknownLayoutError, detect_layout
from app.ingestion.schema import TRANSACTION_COLUMNS, validate


def _as_str(df):
    return df.astype(object).where(df.notna(), None).astype(str).where(df.notna(), None)


@pytest.mark.parametrize("fixture,adapter", [
    ("crn_df", CrnStatementAdapter),
    ("debit_credit_df", DebitCreditAdapter),
    ("icore_short_df", IcoreShortAdapter),
    ("icore_full_df", IcoreFullAdapter),
    ("ledger_df", CustomerLedgerAdapter),
    ("wide_df", WideExtractAdapter),
])
def test_detect_layout(request, fixture, adapter):
    assert detect_layout(request.getfixturevalue(fixture)) is adapter


def test_unknown_layout():
    with pytest.raises(UnknownLayoutError):
        detect_layout(pd.DataFrame({"foo": [1]}))


def _canon(adapter, df, n=2):
    res = adapter().to_canonical(_as_str(df), SourceContext(n, f"{n}_SOA.xlsx", "Sheet1"))
    validate(res.transactions)
    assert list(res.transactions.columns) == list(TRANSACTION_COLUMNS)
    return res


def test_crn_maps_columns_by_content(crn_df):
    # header names of the CRN and D/C columns are random; rename them again
    df = crn_df.rename(columns={"Header Person A": "Priya Nair", "Header Person B": "Rahul Verma"})
    res = _canon(CrnStatementAdapter, df)
    t = res.transactions
    assert len(t) == len(crn_df)
    assert t["direction"].tolist()[:5] == ["CR"] * 5 and t["direction"].iloc[-1] == "DR"
    assert t["amount"].iloc[0] == 2000.0
    assert not t["time_reliable"].any() and t["txn_ts"].isna().all()
    assert t["raw_date"].notna().all()
    assert res.account["account_number"] == "1111222233"
    assert (t["account_id"] == "SOA2").all()
    assert t["txn_uid"].iloc[0] == "SOA2-000000"


def test_debit_credit(debit_credit_df):
    t = _canon(DebitCreditAdapter, debit_credit_df, 6).transactions
    assert t["direction"].tolist() == ["CR", "DR", "CR"]
    assert t["amount"].tolist() == [100000.50, 75000.25, 5000.0]
    assert t["channel"].tolist() == ["IMPS", "UNKNOWN", "UPI"]
    assert not t["time_reliable"].any()


def test_icore_short_uses_pstd_dt(icore_short_df):
    res = _canon(IcoreShortAdapter, icore_short_df, 7)
    t = res.transactions
    assert t["time_reliable"].all()
    assert t["txn_ts"].iloc[0] == pd.Timestamp("2020-12-17 09:00:00")
    assert t["txn_ts"].is_monotonic_increasing
    assert t["raw_date"].iloc[0] == "44001"  # Tran_Date kept raw only
    assert res.account["account_number"] == "999988887777"


def test_icore_full_anonymised_account_numbers(icore_full_df):
    res = _canon(IcoreFullAdapter, icore_full_df, 14)
    assert res.account["account_number"] is None  # changes every row -> not used
    assert res.account["account_id"] == "SOA14"
    assert res.transactions["direction"].tolist() == ["CR", "DR", "CR", "DR"]


def test_ledger(ledger_df):
    t = _canon(CustomerLedgerAdapter, ledger_df, 1).transactions
    assert t["direction"].tolist() == ["CR", "DR"]


def test_wide_drops_blank_rows_and_pan(wide_df):
    t = _canon(WideExtractAdapter, wide_df, 3).transactions
    assert len(t) == 2
    assert t["direction"].tolist() == ["CR", "DR"]
    assert "PAN DETAILS" not in t.columns
