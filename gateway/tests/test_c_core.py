"""The T-Deck's C++ core (hosttest/vectors) must agree with the Python reference."""
import os, subprocess
import coincurve, nacl.signing, nacl.secret
import pytest
from arcade_lora import device_keys as K, txcheck as T, frames as F

BIN = os.path.join(os.path.dirname(__file__), "..", "..", "hosttest", "vectors")
pytestmark = pytest.mark.skipif(not os.path.exists(BIN), reason="build hosttest first (make -C hosttest)")
PHRASES = ["abandon " * 11 + "about", "zoo " * 11 + "wrong",
           "legal winner thank year wave sausage worth useful legal winner thank yellow"]


def run(*args):
    return subprocess.run([BIN, *args], capture_output=True, text=True, check=True).stdout.splitlines()


@pytest.mark.parametrize("phrase", PHRASES)
def test_keys_and_login_signature(phrase):
    a = K.Account(phrase)
    login, mail, coin, t_addr, m_addr, d_addr, sig = run("keys", phrase)
    assert login == a.login_pubkey.hex()
    assert mail == a.mail_pubkey.hex()
    assert coin == a.coin_pubkey("test").hex()
    assert t_addr == a.address("test", 113) and m_addr == a.address("main", 56) and d_addr == a.address("doge", 30)
    assert bytes.fromhex(sig) == a.sign_login("http://127.0.0.1:8420", "n0nce")   # Ed25519 is deterministic


def test_phrase_checks():
    assert run("valid", PHRASES[0]) == ["1"]
    assert run("valid", "abandon " * 12) == ["0"]          # bad checksum
    assert run("valid", "abandon " * 11 + "abound") == ["0"]
    fresh = run("newphrase")[0]
    assert len(fresh.split()) == 12 and run("valid", fresh) == ["1"]


def test_signature_low_s_and_valid():
    a = K.Account(PHRASES[0])
    pub = coincurve.PublicKey(a.coin_pubkey("test"))
    for i in range(20):
        d = bytes([i]) * 32
        der = bytes.fromhex(run("sign", PHRASES[0], "test", d.hex())[0])
        assert der[-1] == 1 and pub.verify(der[:-1], d, hasher=None)
        # libsecp256k1 refuses high-S, so verify() passing also proves low S. The
        # nonce is micro-ecc's deterministic HMAC-DRBG, not byte-for-byte RFC 6979,
        # so the bytes differ from Python's; both are deterministic per digest.
        assert run("sign", PHRASES[0], "test", d.hex())[0] == der.hex()


def _offer(phrase, pay_script, amount, change):
    acct = K.Account(phrase)
    tx = T.Tx(1)
    tx.ins = [T.TxIn(bytes.fromhex("11" * 32), 0, b"", 0xFFFFFFFF), T.TxIn(bytes.fromhex("22" * 32), 3, b"", 0xFFFFFFFF)]
    tx.outs = [T.TxOut(amount, pay_script), T.TxOut(change, T.p2pkh(K.hash160(acct.coin_pubkey("test"))))]
    return acct, tx.serialize()


def test_offer_check_matches_python():
    pay = T.p2pkh(b"\x05" * 20)
    acct, raw = _offer(PHRASES[1], pay, 5000, 1000)
    out = run("check", PHRASES[1], "test", raw.hex(), "4000,3000", pay.hex(), "5000", "1500")
    py = T.check_offer(raw, [4000, 3000], acct.coin_pubkey("test"), pay_script=pay, amount=5000, fee_cap=1500)
    assert out[0] == "1" and out[2] == "5000 1000 1000"
    assert [bytes.fromhex(d) for d in out[3:]] == py.digests


@pytest.mark.parametrize("why,amount,payee,cap", [
    ("different amount", 6000, b"\x05", 1500), ("did not name", 5000, b"\x09", 1500), ("cap", 5000, b"\x05", 500)])
def test_offer_refusals(why, amount, payee, cap):
    asked = T.p2pkh(b"\x05" * 20)
    acct, raw = _offer(PHRASES[1], T.p2pkh(payee * 20), amount, 1000 if amount == 5000 else 0)
    out = run("check", PHRASES[1], "test", raw.hex(), "4000,3000", asked.hex(), "5000", str(cap))
    assert out[0] == "0" and why in out[1]


@pytest.mark.parametrize("n", [0, 5, 195, 196, 1000])
def test_frames_match_python(n):
    body = bytes(range(256))[:n] if n <= 256 else bytes(range(256)) * 4
    out = run("frames", "49", "300", body.hex())
    py = F.split(F.Message(0x31, 300, body))
    assert [bytes.fromhex(x) for x in out[:-1]] == list(reversed(py))
    assert out[-1] == (body.hex() if body else "")


def test_secretbox_is_nacl():
    key, nonce, msg = b"k" * 32, b"n" * 24, b"twelve words go here"
    out = run("box", key.hex(), nonce.hex(), msg.hex())
    assert out[1] == "1"
    assert nacl.secret.SecretBox(key).decrypt(bytes.fromhex(out[0]), nonce) == msg
