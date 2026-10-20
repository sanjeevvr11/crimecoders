import pytest

from app import config
from app.ingestion.narration_parser import normalise_vpa, parse_narration


@pytest.mark.parametrize("text,channel,key,ctype", [
    # layout A: UPI/<vpa-or-name, truncated>/<rrn>/<note>
    ("UPI/testpayer01/530000000004/UPI", "UPI", "upi:testpayer01", "upi"),
    ("UPI/1112223334@/430000000003/Payment fro", "UPI", "upi:1112223334", "upi"),
    ("UPI/merchant.pa/830000000008/PE000000001", "UPI", "upi:merchant.pa", "upi"),
    # ICORE / file 6: UPI/<rrn>/<note>/<vpa@handle>/<bank>
    ("UPI/800000000007/UPI/testpayer2@oks/State Bank Of", "UPI", "upi:testpayer2", "upi"),
    ("UPI/960000000011/UPI/testpayerlongid/State Bank Of", "UPI", "upi:testpayerlo", "upi"),
    ("UPI/210000000001/Payment from Ph/9000000001@ybl/St,ate Bank Of I", "UPI", "upi:9000000001", "upi"),
    # IMPS with name + IFSC, IFSC only, and comma-wrapped
    ("MMT/IMPS/940000000010/TestPayeeName/TEST0000005", "IMPS", "ifsc:TEST0000005:testpayeename", "ifsc"),
    ("MMT/IMPS/890000000009/TEST000X031,", "IMPS", "ifsc:TEST000X031", "ifsc"),
    ("MMT/IMPS/600000000006/7654321 by USER/TESTN     /K", "IMPS", "name:testn", "name"),
    ("IBIMPS Sent to 123456789012", "IMPS", "acct:123456789012", "account"),
    ("INF/50100234567890/", "OTHER", "acct:50100234567890", "account"),
    ("INF/NEFT/240000000002/TEST0000001/1234567 by USER/,TESTPAYEEB", "NEFT", "ifsc:TEST0000001:testpayeeb", "ifsc"),
    ("BIL/INFT/590000000005/MIB-testpayeec/", "OTHER", "name:mib testpayeec", "name"),
    ("CASA IP-5651/1-84000000001/TEST PAYEE", "OTHER", "acct:84000000001", "account"),
    ("BY CLG INST 37:HDFC AT TESTCITY", "CLG", None, "none"),
    ("O/W RTN:37:FUNDS INSUFFICIENT", "CLG", None, "none"),
    ("Chrg: Debit Card Annual Fee 1744 for 2020", "CHARGES", None, "none"),
    ("MB P Ref 12345", "IMPS", None, "none"),
    ("NEFT-HDFCR52020061612345-ACME LTD", "NEFT", None, "none"),
    ("RTGS/ICICR42020123456/ACME", "RTGS", None, "none"),
    ("ATL/12345/ATM WDL", "ATM", None, "none"),
    ("CASH WITHDRAWAL", "ATM", None, "none"),
    ("REV UPI/123/abc", "UPI", None, "none"),
])
def test_patterns(text, channel, key, ctype):
    p = parse_narration(text)
    assert p.channel == channel
    assert p.counterparty_key == key
    assert p.counterparty_type == ctype
    assert p.parsed


def test_truncated_vpas_match_across_layouts():
    # CRN layout cuts to 11 chars, ICORE to 15: both must produce the same key
    crn = parse_narration("UPI/ramesh.kuma/100000000000/Payment fro").counterparty_key
    icore = parse_narration("UPI/200000000000/NA/ramesh.kumar@o/HDFC BANK").counterparty_key
    assert crn == icore == "upi:ramesh.kuma"


def test_imps_bank_prefix_from_ifsc():
    assert parse_narration("MMT/IMPS/123456789012/x/TEST0000004").counterparty_bank == "TEST"


def test_rmks_reference():
    p = parse_narration("TXN-ABCDEFGHIJ", "500000000001//4000000000000002")
    assert p.rrn == "500000000001" and p.counterparty_key is None


def test_tokens_are_unknown_by_default():
    p = parse_narration("TXN-AB12CDUPI9")
    assert p.channel == "UNKNOWN" and not p.parsed


def test_token_channel_recovery_switch(monkeypatch):
    monkeypatch.setattr(config, "RECOVER_CHANNEL_FROM_TOKENS", True)
    assert parse_narration("TXN-AB12CDUPI9").channel == "UPI"


@pytest.mark.parametrize("value", [None, float("nan"), "", "   "])
def test_empty(value):
    assert parse_narration(value).channel == "UNKNOWN"


def test_normalise_vpa():
    assert normalise_vpa("Sample.Payee9@OKAXIS") == "sample.paye"
    assert normalise_vpa("ab@x") is None
