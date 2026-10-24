# arcade-lora

DogecoinArcade over Meshtastic LoRa: the gateway an arcade runs next to a
Meshtastic radio, the wire protocol, and the tests that hold the T-Deck
firmware to it.

- `PROTOCOL.md`: the frames (PRIVATE_APP DMs, 200-byte frames, up to 16 parts),
  sign-in, wallet, contacts, mail with signed receipts, peer to peer.
- `gateway/arcade_lora`: the gateway (`python -m arcade_lora --port /dev/ttyUSB0
  --arcade http://127.0.0.1:8420`) and a Python reference T-Deck (`devcli`).
- `hosttest`: builds the T-Deck's C++ core and screens on a PC, for the
  cross-checks in `gateway/tests` and for screenshots.
- `mockup`: the interactive UI mockup.

The firmware itself: https://github.com/martinseeger2002/firmware (branch
`arcade`, target `t-deck-arcade`) with https://github.com/martinseeger2002/device-ui
(branch `arcade`). Releases carry the flashable binaries.

Tests: `make -C hosttest` (needs a firmware checkout for LVGL), then
`cd gateway && python -m pytest -q tests`.
