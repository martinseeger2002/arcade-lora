"""T-Deck messages against the arcade's own envelope code (arcade/messaging/envelope.py)."""
import json, os, subprocess, sys
import pytest
from arcade_lora import device_keys as K

BIN = os.path.join(os.path.dirname(__file__), "..", "..", "hosttest", "vectors")
ARCADE = os.path.expanduser("~/arcade-localtest")
pytestmark = pytest.mark.skipif(not (os.path.exists(BIN) and os.path.isdir(ARCADE)), reason="needs hosttest + arcade")
sys.path.insert(0, ARCADE)
from arcade.messaging import envelope as E          # noqa: E402
from arcade.messaging.keys import Identity          # noqa: E402

ME, ROBIN = "abandon " * 11 + "about", "zoo " * 11 + "wrong"
me, robin = K.Account(ME), K.Account(ROBIN)


def ident(acct):
    return Identity.from_secret_bytes(acct.mail_secret)


def run(*a):
    return subprocess.run([BIN, *a], capture_output=True, text=True, check=True).stdout.splitlines()


@pytest.mark.parametrize("text", ["see you at the lake", "héllo ☃ 😀", "x" * 500])
def test_tdeck_seals_arcade_opens(text):
    sealed = bytes.fromhex(run("seal", ME, robin.mail_pubkey.hex(), text)[0])
    assert len(sealed) == len(text.encode()) + 126
    payload = E.Header(type=E.TYPE_SINGLE, clen=len(sealed)).encode() + sealed + b"\0" * 17   # as on chain, padded
    sender, message, _ = E.open_message(ident(robin), payload)
    assert sender == me.mail_pubkey and message.decode() == text


def test_arcade_seals_tdeck_opens():
    payload = E.seal_message(ident(robin), me.mail_pubkey, E.Header(type=E.TYPE_SINGLE), "hi from the web".encode())
    sealed = payload[8:]                                     # what the gateway hands the T-Deck
    ok, rest = run("open", ME, sealed.hex())
    flag, sender, had_file = ok.split()
    assert flag == "1" and sender == robin.mail_pubkey.hex() and had_file == "0" and rest == "hi from the web"


def test_rich_body_shows_its_text():
    meta = json.dumps({"text": "a picture for you", "file": {"name": "frog.png", "size": 3}}).encode()
    body = b"\x01ARCB\x01" + len(meta).to_bytes(2, "big") + meta + b"PNG"
    payload = E.seal_message(ident(robin), me.mail_pubkey, E.Header(type=E.TYPE_SINGLE), body)
    ok, rest = run("open", ME, payload[8:].hex())
    assert ok.split()[0] == "1" and ok.split()[2] == "1" and rest == "a picture for you"


def test_not_for_me():
    payload = E.seal_message(ident(me), robin.mail_pubkey, E.Header(type=E.TYPE_SINGLE), b"secret")
    assert run("open", ME, payload[8:].hex())[0].startswith("0 ")
