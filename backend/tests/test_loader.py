import duckdb
import pandas as pd

from app.ingestion.loader import discover_files, load_all, write_outputs


def test_discover_skips_lock_files(raw_dir):
    names = [p.name for _, p in discover_files(raw_dir)]
    assert "~$25_SOA.xlsx" not in names
    assert [n for n, _ in discover_files(raw_dir)] == [1, 2, 3, 6, 7, 14]


def test_load_all(raw_dir, tmp_path):
    txns, accounts = load_all(raw_dir)
    assert set(accounts["account_id"]) == {"SOA1", "SOA2", "SOA3", "SOA6", "SOA7", "SOA14"}
    assert accounts.set_index("account_id")["n_rows"].to_dict()["SOA3"] == 2
    assert txns.groupby("account_id")["time_reliable"].first().to_dict() == {
        "SOA1": False, "SOA14": True, "SOA2": False, "SOA3": False, "SOA6": False, "SOA7": True}
    db = tmp_path / "t.duckdb"
    write_outputs({"transactions": txns, "accounts": accounts}, tmp_path / "out", db)
    assert pd.read_parquet(tmp_path / "out" / "transactions.parquet").shape[0] == len(txns)
    with duckdb.connect(str(db), read_only=True) as con:
        assert con.execute("select count(*) from transactions").fetchone()[0] == len(txns)
