"""The T-Deck's C++ client (hosttest/client) against the real Python gateway."""
import os, subprocess
import pytest
from arcade_lora import txcheck as T
from arcade_lora.gateway import Gateway
from test_gateway import FakeArcade, PHRASE, ROBIN_ADDR

BIN = os.path.join(os.path.dirname(__file__), "..", "..", "hosttest", "client")
pytestmark = pytest.mark.skipif(not os.path.exists(BIN), reason="build hosttest first (make -C hosttest)")
DEV, GW = 0x970046A4, 0x433C8154


class Harness:
    def __init__(self, tmp):
        self.p = subprocess.Popen([BIN, str(tmp)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        FakeArcade.register = lambda self, net, addr, pub: {"address": addr}
        self.gw = Gateway("http://127.0.0.1:8420", self._to_device, session_factory=FakeArcade, flush_delay=0)
        self.airtime = 0

    def _to_device(self, node, frame):
        assert node == DEV
        self.p.stdin.write(f"rx {GW:08x} {frame.hex()}\n")

    def cmd(self, line):
        self.p.stdin.write(line + "\n")
        return self.settle()

    def settle(self):
        seen = []
        while True:
            self.p.stdin.write("state\n")
            out, moved = [], False
            while True:
                line = self.p.stdout.readline().strip()
                if line == "state end":
                    break
                if line.startswith("tx "):
                    _, to, hexf = line.split()
                    assert int(to, 16) in (GW, 0xFFFFFFFF)
                    self.airtime += 1
                    self.gw.receive(DEV, bytes.fromhex(hexf))
                    moved = True
                else:
                    out.append(line)
            if not moved:
                return seen + out           # this round's lines once, earlier rounds' events before them
            seen += [l for l in out if not l.startswith("state ")]

    def state(self, prefix):
        return [l for l in self.settle() if l.startswith(prefix)]

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=5)


@pytest.fixture
def h(tmp_path):
    x = Harness(tmp_path)
    yield x
    x.close()


def test_create_find_gateway_sign_in_and_balances(h):
    out = h.cmd("create 482916 " + PHRASE)
    assert "created 1" in out
    link = h.state("state link")[0]
    assert "link=online" in link and "tag=tester" in link and f"gw={GW:08x}" in link
    chains = h.state("state chain")
    assert chains == ["state chain test 7000 9 reg=1", "state chain main 1 0 reg=1"]   # spendable, arriving


def test_wrong_pin_and_relock(h):
    h.cmd("create 482916 " + PHRASE)
    h.cmd("lock")
    assert "unlocked 0" in h.cmd("unlock 000000")
    out = h.cmd("unlock 482916")
    assert "unlocked 1" in out
    assert "link=online" in h.state("state link")[0]         # straight back to the saved gateway


def test_bad_phrase_refused(h):
    assert "created 0" in h.cmd("create 482916 " + "abandon " * 12)


def test_add_contact_and_send(h):
    h.cmd("create 482916 " + PHRASE)
    h.cmd("who @robin")
    assert h.state("state contact") == [f"state contact robin {ROBIN_ADDR}"]
    h.cmd("send 0 3500 @robin")
    send = h.state("state send")[0]
    assert send.startswith("state send 2 ") and "fee=500" in send and "change=3000" in send   # Review
    h.cmd("confirm")
    send = h.state("state send")[0]
    assert send.startswith("state send 4 ")                                                    # Sent
    signed = FakeArcade.last.sent[-1]
    assert T.Tx.parse(signed).txid().hex() in send


def test_lying_gateway_refused_by_the_c_client(h, monkeypatch):
    h.cmd("create 482916 " + PHRASE)
    real = FakeArcade.send
    def greedy(self, network, to, amount):
        said = real(self, network, to, amount)
        tx = T.Tx.parse(bytes.fromhex(said["raw"]))
        tx.outs[1].script = T.p2pkh(b"\x66" * 20)
        said["raw"] = tx.serialize().hex()
        return said
    monkeypatch.setattr(FakeArcade, "send", greedy)
    h.cmd("send 0 3500 @robin")
    send = h.state("state send")[0]
    assert send.startswith("state send 5 ") and "did not name" in send                        # Failed
    assert FakeArcade.last.sent == []


# ---- messages -----------------------------------------------------------------

import sys as _sys
_ARCADE = os.path.expanduser("~/arcade-localtest")
_sys.path.insert(0, _ARCADE)
from arcade.messaging import envelope as E           # noqa: E402
from arcade.messaging.keys import Identity           # noqa: E402
from arcade_lora import device_keys as K             # noqa: E402
from test_gateway import ACCT, ROBIN, NOTICE_VALUE   # noqa: E402


def _mail_offer(self, to, sealed):
    """The shape /account/write answers with: marker, packets in 1-of-3 multisig, the notice, change."""
    packets = (len(sealed) + 12 + 59) // 60
    own = T.p2pkh(K.hash160(ACCT.coin_pubkey("test")))
    outs = [T.TxOut(1_000_000, T.p2pkh(b"\x01" * 20))]
    outs += [T.TxOut(1_000_000, b"\x51" + b"\x21" + b"\x02" * 33 + b"\x52\xae") for _ in range(packets)]
    outs += [T.TxOut(1_000_000, T.script_for(to, 113, 196)), T.TxOut(7000 * 10**6, own)]
    tx = T.Tx(1)
    tx.ins = [T.TxIn(bytes.fromhex("11" * 32), 0, b"", 0xFFFFFFFF)]
    tx.outs = outs
    raw = tx.serialize()
    self.offers["m1"] = raw
    self.mail.append((to, sealed))
    total = sum(o.value for o in outs) + 30000
    return {"offer": "m1", "bytes": len(sealed), "chain": "test", "raw": raw.hex(), "fee": 30000, "change": 7000 * 10**6,
            "inputs": [{"value": total}]}


def test_message_a_contact_and_get_a_reply(h, monkeypatch):
    FakeArcade.mail = []
    monkeypatch.setattr(FakeArcade, "write", _mail_offer, raising=False)
    h.cmd("create 482916 " + PHRASE)
    h.cmd("who @robin")
    out = h.cmd("msg robin see you at the lake")
    assert "msg 1" in out
    letters = [l for l in h.state("letter") if True] or [l for l in h.cmd("thread robin") if l.startswith("letter")]
    letters = [l for l in h.cmd("thread robin") if l.startswith("letter")]
    assert letters[0].startswith("letter 1 1 ")                      # mine, Sent, with a txid
    to, sealed = FakeArcade.mail[-1]
    assert to == ROBIN_ADDR
    who, text, _ = E.open_message(Identity.from_secret_bytes(ROBIN.mail_secret),
                                  E.Header(type=E.TYPE_SINGLE, clen=len(sealed)).encode() + sealed)
    assert who == ACCT.mail_pubkey and text == b"see you at the lake"

    # robin answers on chain; the gateway carries it because robin is a contact
    reply = E.seal_message(Identity.from_secret_bytes(ROBIN.mail_secret), ACCT.mail_pubkey,
                           E.Header(type=E.TYPE_SINGLE), "bring the canoe".encode())
    monkeypatch.setattr(FakeArcade, "messages", lambda self, after, limit=200: {"cursor": 9, "more": False, "candidates": [
        {"cursor": 9, "txid": "55" * 32, "when": 1700000100, "from_address": ROBIN_ADDR, "type": 1,
         "payload": (reply + b"\0" * 13).hex()}]})
    monkeypatch.setattr(FakeArcade, "coins", lambda self, net: [{"txid": "55" * 32, "vout": 2, "value": NOTICE_VALUE}])
    h.gw.devices[DEV].mail_cursor = 0
    h.gw.poll()
    h.settle()
    letters = [l for l in h.cmd("thread robin") if l.startswith(("letter", "unread"))]
    assert letters[1] == "letter 0 3 " + "55" * 32 + "|bring the canoe|"
    assert letters[2] == "unread 1"
    assert h.gw.store.pending(DEV) == [] and h.gw.store.receipt(DEV, "55" * 32)   # the signed receipt landed


def test_message_too_long_is_refused_on_the_tdeck(h):
    h.cmd("create 482916 " + PHRASE)
    h.cmd("who @robin")
    out = h.cmd("msg robin " + "x" * 600)
    assert any(l.startswith("msg 0 Too long for LoRa") for l in out)


def test_unknown_contact_cannot_be_messaged(h):
    h.cmd("create 482916 " + PHRASE)
    assert any("No mail key" in l for l in h.cmd("msg nobody hello"))


def test_everything_survives_a_restart(tmp_path, monkeypatch):
    FakeArcade.mail = []
    monkeypatch.setattr(FakeArcade, "write", _mail_offer, raising=False)
    a = Harness(tmp_path)
    a.cmd("create 482916 " + PHRASE)
    a.cmd("who @robin")
    a.cmd("msg robin first letter")
    a.close()
    b = Harness(tmp_path)                                    # same flash, fresh boot, no gateway answering
    b.gw = Gateway("http://x", lambda n, f: None, session_factory=FakeArcade, flush_delay=0)
    assert "unlocked 1" in b.cmd("unlock 482916")
    link = b.state("state link")[0]
    assert "tag=tester" in link                              # the @tag from the saved account
    assert b.state("state contact") == [f"state contact robin {ROBIN_ADDR}"]
    assert b.state("state chain")[0].startswith("state chain test 7000 9")   # saved balances
    letters = [l for l in b.cmd("thread robin") if l.startswith("letter")]
    assert letters and letters[0].startswith("letter 1 1 ") and "first letter" in letters[0]
    b.close()


def test_a_message_that_failed_can_be_sent_again(h, monkeypatch):
    FakeArcade.mail = []
    calls = {"n": 0}
    def flaky(self, to, sealed):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ArcadeErrorForTest("the node is busy")
        return _mail_offer(self, to, sealed)
    monkeypatch.setattr(FakeArcade, "write", flaky, raising=False)
    h.cmd("create 482916 " + PHRASE)
    h.cmd("who @robin")
    h.cmd("msg robin hello again")
    first = [l for l in h.cmd("thread robin") if l.startswith("letter")][0]
    assert first.startswith("letter 1 2 ") and "the node is busy" in first        # Failed, with why
    assert "resend 1" in " ".join(h.cmd("resend robin 0"))
    again = [l for l in h.cmd("thread robin") if l.startswith("letter")]
    assert len(again) == 1 and again[0].startswith("letter 1 1 ")                 # the same letter, now Sent
    assert len(FakeArcade.mail) == 1


from arcade_lora.arcade_api import ArcadeError as ArcadeErrorForTest   # noqa: E402


# ---- no gateway, and a lossy radio --------------------------------------------

import random as _random


class LossyHarness(Harness):
    """The same pipe, but frames get lost both ways, and time can pass."""

    def __init__(self, tmp, loss, seed=1, up=None):
        super().__init__(tmp)
        self.rng = _random.Random(seed)
        self.loss = loss                            # gateway -> T-Deck
        self.up_loss = loss if up is None else up   # T-Deck -> gateway
        self.now = 1000
        self.dropped = 0
        self.up = True                       # False: no gateway in range at all
        real_gw_receive = self.gw.receive

        def lossy_gw_receive(node, frame):
            if not self.up or self.rng.random() < self.up_loss:
                self.dropped += 1
                return
            real_gw_receive(node, frame)
        self.gw_receive = lossy_gw_receive

    def _to_device(self, node, frame):
        if not self.up or self.rng.random() < self.loss:
            self.dropped += 1
            return
        super()._to_device(node, frame)

    def settle(self):
        seen = []
        while True:
            self.p.stdin.write("state\n")
            out, moved = [], False
            while True:
                line = self.p.stdout.readline().strip()
                if line == "state end":
                    break
                if line.startswith("tx "):
                    _, to, hexf = line.split()
                    self.gw_receive(DEV, bytes.fromhex(hexf))
                    moved = True
                else:
                    out.append(line)
            if not moved:
                return seen + out
            seen += [l for l in out if not l.startswith("state ")]

    def wait(self, ms):
        self.now += ms
        return self.cmd(f"tick {self.now}")

    def until(self, prefix, want, rounds=40):
        for _ in range(rounds):
            got = [l for l in self.settle() if l.startswith(prefix)]
            if any(want in l for l in got):
                return got
            self.wait(46000)                 # past the request timeout: the T-Deck asks again
        raise AssertionError(f"never saw {want!r} in {prefix}: {got}")


@pytest.fixture(params=range(1, 13))
def lossy(tmp_path, request):
    """30% of frames lost toward the T-Deck and 10% from it, as on the real link
    after Meshtastic's own retries, under twelve different patterns of loss."""
    x = LossyHarness(tmp_path, loss=0.3, up=0.1, seed=request.param)
    yield x
    x.close()


def test_sign_in_send_and_message_survive_a_lossy_radio(lossy, monkeypatch):
    FakeArcade.mail = []
    monkeypatch.setattr(FakeArcade, "write", _mail_offer, raising=False)
    h = lossy
    h.cmd("create 482916 " + PHRASE)
    h.until("state link", "link=online")
    h.cmd("who @robin")
    h.until("state contact", "robin")
    h.cmd("send 0 3500 @robin")
    h.until("state send", "state send 2 ")                     # Review, despite lost frames
    h.cmd("confirm")
    h.until("state send", "state send 4 ")                     # Sent
    assert len(FakeArcade.last.sent) == 1                       # retries never paid twice
    h.cmd("msg robin through the noise")
    for _ in range(40):
        letters = [l for l in h.cmd("thread robin") if l.startswith("letter")]
        if letters and letters[-1].startswith("letter 1 1 "):
            break
        h.wait(46000)
    assert letters[-1].startswith("letter 1 1 ")
    assert h.dropped > 0


def test_a_payment_waits_for_a_gateway_then_goes_by_itself(tmp_path):
    h = LossyHarness(tmp_path, loss=0.0)
    h.cmd("create 482916 " + PHRASE)
    h.until("state link", "link=online")
    h.cmd("who @robin")
    h.until("state contact", "robin")
    h.up = False                                                # walk out of range
    h.cmd("lock")
    h.cmd("unlock 482916")
    h.wait(46000)
    h.wait(46000)
    h.wait(46000)                                               # sign-in gives up: no gateway
    assert "link=online" not in h.state("state link")[0]
    h.cmd("send 0 3500 @robin")
    assert h.state("state send")[0].startswith("state send 6 ")  # Queued, kept on flash
    h.close()
    h2 = LossyHarness(tmp_path, loss=0.0)                       # a restart while it waits
    h2.cmd("unlock 482916")
    h2.until("state link", "link=online")                       # a gateway answers
    h2.until("state send", "state send 4 ")                     # paid without asking: @robin is a contact
    assert len(FakeArcade.last.sent) == 1
    h2.close()


def test_a_waiting_payment_comes_off_the_balance(tmp_path):
    h = LossyHarness(tmp_path, loss=0.0)
    h.cmd("create 482916 " + PHRASE)
    h.until("state link", "link=online")
    h.up = False
    h.cmd("lock")
    h.cmd("unlock 482916")
    for _ in range(3):
        h.wait(46000)
    h.cmd("send 0 3500 @robin")
    assert h.state("state send")[0].startswith("state send 6 ")
    assert h.state("state avail")[0] == "state avail test 3500"        # 7000 less the 3500 waiting
    h.cmd("send 0 4000 @robin")                                        # more than is left
    assert "counting payments still waiting" in h.state("state send")[0]
    assert "cancelled 1" in " ".join(h.cmd("cancelq 0"))               # taken back: the balance is whole again
    assert h.state("state avail")[0] == "state avail test 7000"
    h.close()
