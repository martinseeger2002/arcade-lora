# Arcade LoRa protocol, version 1

The wire format between an arcade T-Deck ("device"), an arcade gateway
("gateway"), and other arcade T-Decks ("peer"). It is carried inside
ordinary Meshtastic packets, so every stock Meshtastic node relays it.

## Transport

- Meshtastic `PRIVATE_APP` (port number 256), `decoded.payload` = one frame.
- Device↔gateway and device↔peer traffic is a **direct message** to the other
  node. Stock firmware encrypts DMs end to end with the two radios' X25519
  keys (`pki_encrypted`), so relays see nothing.
- Beacons (`GW_BEACON`, `PRESENCE`) are broadcasts on the primary channel and
  carry only public facts.
- A gateway reaches its radio over USB serial, or over **Bluetooth** to the
  T-Deck itself. The Bluetooth gateway is the **DogecoinArcade PWA** on a
  phone (Web Bluetooth, Android Chrome; iOS Safari has none), speaking the
  standard Meshtastic BLE service and relaying frames to the arcade that
  served it. A PC can do the same with the Python gateway's `--ble`. Over
  Bluetooth the device addresses frames to its own node number; nothing goes
  on air.
- `want_ack` is set on every DM; Meshtastic retries each packet itself.

## Frame

```
offset size
0      1    magic 0xA7 (protocol version 1)
1      1    type
2      2    id, u16 big-endian. A request picks it; the reply echoes it.
4      1    part: high nibble = index, low nibble = count-1 (single frame = 0x00)
5      ..   body (≤ 195 bytes)
```

- `MAX_FRAME` = 200 bytes. A PKC-encrypted DM must fit 255 − 16 (header) −
  12 (PKC) = 227 bytes of *encoded* Data, and the protobuf wrapper (port
  number, payload length, bitfield) takes a few of those; 220 was refused by
  the radio with TOO_LARGE.
- A body over 195 bytes is split into up to 16 parts (max 3120 bytes). Parts share
  type and id; the receiver joins them when all have arrived and drops a
  partial message after 120 s. `RESEND` asks for missing parts.
- All integers are big-endian. `str` = u8 length + UTF-8. `bytes` = u16
  length + data. `amount` = u64 base units (1e-8 coin).
- A `chain` byte is an index into the chain list from `WELCOME`.

## Types

### Discovery and session (device ↔ gateway)

| type | name | dir | body |
|---|---|---|---|
| 0x01 | GW_BEACON | gw → broadcast | `str name`, `str arcade` (host), `u8 flags` (bit0 accepting logins) |
| 0x02 | HELLO | dev → gw | `login_pubkey[32]` (Ed25519, account id) |
| 0x03 | CHALLENGE | gw → dev | `str origin`, `str nonce` |
| 0x04 | LOGIN | dev → gw | `sig[64]` over `"DogecoinArcade login\n" + origin + "\n" + nonce`, `u8 join` |
| 0x05 | WELCOME | gw → dev | `str tag` (empty = no @tag yet), `u8 n`, n × (`str network`, `str label`, `u8 flags`, `u8 p2pkh_version`, `u8 p2sh_version`); flags bit0 = tag chain, bit1 = real coins |
| 0x06 | ERR | gw/peer → dev | `u8 code`, `str text` (echoes the failed request's id) |
| 0x07 | RESEND | any | `u8 type`, `u16 missing-parts bitmap` (echoes the id) |
| 0x08 | PING | dev → broadcast/gw | empty. Broadcast to find gateways. |
| 0x09 | PONG | gw → dev | same body as GW_BEACON |

The gateway keeps the arcade session (`arcade_session` cookie) per login
pubkey; a `HELLO` after a gateway restart logs in again. The chain list is
whatever the gateway's operator lets T-Decks see.

### Wallet

| type | name | dir | body |
|---|---|---|---|
| 0x10 | BAL_REQ | dev → gw | empty |
| 0x11 | BAL | gw → dev | `u8 n`, n × (`u8 chain`, `amount spendable`, `amount arriving`); spendable is the web wallet's big number (`balance − leaving − held − inscribed + incoming`) |
| 0x12 | COINS_REQ | dev → gw | `u8 chain` |
| 0x13 | COINS | gw → dev | `u8 chain`, `u8 n`, n × (`txid[32]`, `u16 vout`, `amount value`, `u32 height`); cached for offline sends |
| 0x14 | SEND_REQ | dev → gw | `u8 chain`, `amount`, `str to` (@tag or address) |
| 0x15 | OFFER | gw → dev | `u8 chain`, `str to_tag`, `str to_address`, `amount fee`, `amount change`, `bytes raw` (unsigned tx), `u8 n`, n × `amount input_value` |
| 0x16 | SIGN | dev → gw | `u8 n`, n × (`u8 len`, DER sig + sighash byte), `coin_pubkey[33]` |
| 0x17 | SENT | gw → dev | `txid[32]` |
| 0x19 | ADDR | dev → gw | `u8 chain`, `coin_pubkey[33]`; the gateway registers the address it makes with the arcade (sign-up from a T-Deck) |
| 0x1A | ADDR_OK | gw → dev | `str address` |
| 0x18 | BROADCAST | dev → gw | `u8 chain`, `bytes raw` (a fully signed tx, e.g. a carried offline payment) |

The device **never signs a hash it was given**. It parses `raw`, checks every
output against what it asked for (payee, amount, change back to its own
address, fee ≤ its cap), recomputes each SIGHASH_ALL digest itself, and only
then signs (RFC 6979, low-S). The offer expires on the arcade after 300 s.

### Contacts

| type | name | dir | body |
|---|---|---|---|
| 0x20 | WHO_REQ | dev → gw | `str tag` |
| 0x21 | WHO | gw → dev | `str tag`, `str address`, `key[32]` (X25519), `str name` |
| 0x22 | WATCH | dev → gw | `u8 n`, n × `hash160[20]` of contacts' tag-chain addresses |
| 0x23 | WATCH_OK | gw → dev | `u8 n` |

The contact book itself lives on the device (synced over WiFi from the
encrypted arcade mailbox, plus `WHO` adds). `WATCH` only tells the gateway
whose mail to carry.

### Arcade messages (on-chain, through a gateway)

| type | name | dir | body |
|---|---|---|---|
| 0x30 | MAIL_POST | dev → gw | `str to_address`, `bytes sealed` (arcade envelope, sealed by the device) → answered with OFFER/SIGN/SENT |
| 0x31 | MAIL_IN | gw → dev | `txid[32]`, `u32 when`, `str from_address`, `bytes sealed`, `str from_tag` |
| 0x32 | MAIL_TOO_LONG | gw → dev | `txid[32]`, `u32 when`, `str from_address`, `u16 size`, `str from_tag` |
| 0x33 | MAIL_ACK | dev → gw | `txid[32]`, `sig[64]`: Ed25519 by the login key over `"arcade-lora receipt\n" + hex(txid)` |
| 0x34 | MAIL_POLL | dev → gw | empty |

Rules at the gateway:

- A letter is listed before the notice coin it pays the recipient is
  indexed; a contact's letter without its notice is re-checked on every poll
  for 30 minutes, and the saved read position never moves past it.
- Only mail whose sender address is in the device's `WATCH` list is carried.
  Anything else never goes on air.
- `sealed` larger than `MAIL_MAX` (default 645 bytes = 3 frames) is not sent;
  the device gets `MAIL_TOO_LONG` instead and shows "Message too long".
- **Delivery is the device's signed receipt, never the radio's ack.** Mail
  waits in the gateway's outbox (kept on disk, with the read position and the
  session, so a restart loses nothing) until a valid `MAIL_ACK` arrives. The
  device sends it only after the whole letter is stored.
- **Mail goes only to a T-Deck that is on.** A device is online when the
  gateway has heard *any* packet from its node in the last 20 minutes (a
  HELLO, its node info at power-on, a position). The moment a silent device
  is heard again, its whole outbox goes at once; while online, unconfirmed
  mail is tried again every 3 minutes; once it falls silent, nothing more is
  sent into the air.
- Receipts are kept per device, so the arcade can later tell a sender
  "delivered to @x's T-Deck".

### Peer to peer (device ↔ device, no gateway needed)

| type | name | dir | body |
|---|---|---|---|
| 0x40 | PRESENCE | dev → broadcast/peer | `str tag`, `login_pubkey[32]`, `x25519[32]`, `u32 node`, `u32 time`, `sig[64]` |
| 0x41 | P2P_MSG | dev → peer | `bytes sealed` (same envelope as arcade mail) |
| 0x42 | P2P_PAY | dev → peer | `u8 chain`, `u8 flags`, `str network`, `bytes raw` (signed tx) |
| 0x43 | P2P_ACK | peer → dev | `u8 type acked` |

- A `P2P_MSG` to a contact whose T-Deck is silent stays in the sender's
  outbox and is tried again when that contact's node is heard (or posted on
  chain through a gateway instead, where it waits for them safely).
- `PRESENCE` binds a Meshtastic node to an @tag. `sig` is Ed25519 by the
  login key over `"arcade-lora presence\n" + tag + "\n" + hex(x25519) + "\n" +
  node + "\n" + time`. A peer trusts it only if the login pubkey matches the
  one its contact book holds for that tag (learned from a gateway or WiFi sync).
- `P2P_PAY` flags: bit0 = **offline / unconfirmed** (no gateway was reachable
  when it was signed), bit1 = already broadcast. The sender broadcasts through
  a gateway first when one answers; otherwise it hands over the signed tx and
  both devices keep it in an outbox until either reaches a gateway
  (`BROADCAST`). The receiver shows "OFFLINE, unconfirmed" until a gateway
  confirms the txid.

## Error codes (ERR)

| code | meaning |
|---|---|
| 1 | not logged in |
| 2 | bad request |
| 3 | arcade refused (text = arcade's own reason) |
| 4 | busy, try later |
| 5 | too long |
| 6 | unknown tag |
| 7 | offer expired |
