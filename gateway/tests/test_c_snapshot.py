"""WiFi sync's account and coins answers, read the way the T-Deck reads them."""
import json, os, subprocess
import pytest

BIN = os.path.join(os.path.dirname(__file__), "..", "..", "hosttest", "vectors")
pytestmark = pytest.mark.skipif(not os.path.exists(BIN), reason="build hosttest first")


def run(tmp_path, cmd, obj):
    f = tmp_path / "j.json"
    f.write_text(json.dumps(obj))
    return subprocess.run([BIN, cmd, str(f)], capture_output=True, text=True, check=True).stdout.splitlines()


def test_account_like_the_arcade_sends_it(tmp_path):
    acct = {"pubkey": "ab" * 32, "tag": "apple", "mail_from": 1001140, "profile": {"pfp": None, "bio": "hi \"x\"", "url": ""},
            "quota": {"send": [1, 2]}, "chains": [
                {"network": "main", "label": "Mainnet", "coin": "PEP", "version": 56, "p2sh": 22, "mainnet": True,
                 "address": "Pjy1S2Qn26PTzysPHxL2Ut3fMzSZhvWpne", "balance": 291589749118800, "incoming": 0, "watching": 5,
                 "tags": False, "backed_up": True, "held": {"x": [1]}, "inscribed": []},
                {"network": "test", "label": "Testnet", "version": 113, "p2sh": 196, "mainnet": False,
                 "address": "nZNQpQuok8MhKsNznMQMv64QEFv68UuCCe", "balance": 7917579629000, "incoming": 1000000, "leaving": 2000000, "inscribed": 3000000,
                 "arriving": 500, "tags": True}]}
    out = run(tmp_path, "account", acct)
    assert out[0] == "1 apple 2"
    assert out[1] == "test|Testnet|1|0|113|196|7917575629000|500"         # the tag chain first; spendable, arriving
    assert out[2] == "main|Mainnet|0|1|56|22|291589749118800|0"             # 2.9M PEP, exact


def test_coins_biggest_first(tmp_path):
    coins = {"chain": "test", "address": "n", "coins": [
        {"txid": "%064x" % i, "vout": i, "value": v, "address": "n"} for i, v in enumerate([5, 900, 70, 3])]}
    out = run(tmp_path, "coins", coins)
    assert out[0] == "1 4"
    assert out[1] == "%064x:1 900" % 1 and out[2].endswith(" 70")
