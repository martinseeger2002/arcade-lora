"""The T-Deck opens the arcade mailbox exactly as messaging_js.js seals it."""
import base64, hashlib, json, os, subprocess
import nacl.secret, nacl.utils
import pytest
from arcade_lora import device_keys as K

BIN = os.path.join(os.path.dirname(__file__), "..", "..", "hosttest", "vectors")
pytestmark = pytest.mark.skipif(not os.path.exists(BIN), reason="build hosttest first")
PHRASE = "abandon " * 11 + "about"


def seal(phrase, history):
    """sealHistory(): base64(nonce24 || secretbox(JSON)), key blake2b-256(secret || context)."""
    secret = K.Account(phrase).mail_secret
    key = hashlib.blake2b(secret + b"arcade-mailbox/1", digest_size=32).digest()
    nonce = nacl.utils.random(24)
    box = nacl.secret.SecretBox(key).encrypt(json.dumps(history, ensure_ascii=False).encode(), nonce).ciphertext
    return base64.b64encode(nonce + box).decode()


def run_book(tmp_path, blob, phrase=PHRASE):
    f = tmp_path / "blob"
    f.write_text(blob)
    out = subprocess.run([BIN, "book", phrase, str(f)], capture_output=True, text=True, check=True).stdout.splitlines()
    head = out[0].split(" ", 3)
    return int(head[0]), int(head[1]), int(head[2]), [l.split("|") for l in out[1:]]


def entry(tag, added, name="", key="ab" * 32):
    return {"tag": tag, "address": "n" + tag.upper() + "addr", "key": key, "fingerprint": "x", "added": added,
            "name": name, "face": None, "fav": True, "note": "met at \"the lake\" \\ ok"}


def test_book_comes_out_and_letters_are_skipped(tmp_path):
    letters = [{"id": i, "text": "héllo ☃   " * 50, "nested": {"a": [1, 2, {"b": None}]}} for i in range(400)]
    history = {"letters": letters, "groups": [{"id": "g", "members": ["a", "b"]}],
               "book": [entry("robin", 100, "Robin \U0001F600"), entry("pip", 200), entry("gone", 50)],
               "bookGone": {"gone": 60, "pip": 150}, "blocked": [], "blockedGone": {}}
    blob = seal(PHRASE, history)
    assert len(blob) > 100_000                     # about the size of @apple's
    ok, n, removed, rows = run_book(tmp_path, blob)
    assert (ok, n, removed) == (1, 2, 1)           # "gone" deleted after it was added; pip re-added after
    assert rows[0] == ["robin", "nROBINaddr", "Robin \U0001F600", "ab" * 32]
    assert rows[1][0] == "pip"


def test_wrong_account_cannot_open(tmp_path):
    blob = seal(PHRASE, {"book": [entry("robin", 1)]})
    ok, n, _, _ = run_book(tmp_path, blob, "zoo " * 11 + "wrong")
    assert ok == 0 and n == 0


def test_empty_mailbox_is_an_empty_book(tmp_path):
    assert run_book(tmp_path, "")[:2] == (1, 0)
