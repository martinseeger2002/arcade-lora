# Builds the T-Deck arcade core for the host, so tests can hold it to the Python reference.
UI := ../device-ui
V := $(UI)/source/arcade/vendor
CFLAGS := -O1 -g -Wall -I$(V)/trezor -DuECC_SUPPORTS_secp160r1=0 -DuECC_SUPPORTS_secp192r1=0 -DuECC_SUPPORTS_secp224r1=0 -DuECC_SUPPORTS_secp256r1=0 -DuECC_SUPPORTS_secp256k1=1
CXXFLAGS := -O1 -g -Wall -std=c++17 -I$(UI)/include -I$(UI)/source/arcade
CSRC := $(V)/trezor/sha2.c $(V)/trezor/ripemd160.c $(V)/trezor/hmac.c $(V)/trezor/pbkdf2.c $(V)/trezor/memzero.c $(V)/trezor/blake2b.c $(V)/uecc/uECC.c $(V)/tweetnacl/tweetnacl.c
CORE := $(UI)/source/arcade/Crypto.cpp $(UI)/source/arcade/Keys.cpp $(UI)/source/arcade/Frames.cpp $(UI)/source/arcade/Tx.cpp $(UI)/source/arcade/ArcadeClient.cpp $(UI)/source/arcade/Mailbox.cpp $(UI)/source/arcade/Snapshot.cpp $(UI)/source/arcade/Envelope.cpp
CXXSRC := $(CORE) vectors.cpp
COBJ := $(patsubst %.c,build/%.o,$(notdir $(CSRC)))

LVGL := $(HOME)/arcade-lora/firmware/.pio/libdeps/t-deck-tft/lvgl
LVSRC := $(shell find $(LVGL)/src -name '*.c' -not -path '*/drivers/*' -not -path '*/thorvg/*' -not -path '*/libs/*') $(wildcard $(LVGL)/src/libs/bin_decoder/*.c)
LVOBJ := $(patsubst $(LVGL)/src/%.c,build/lvgl/%.o,$(LVSRC))
FONTS := $(wildcard $(UI)/source/arcade/fonts/*.c)
LVFLAGS := -O1 -DLV_CONF_INCLUDE_SIMPLE -DLV_LVGL_H_INCLUDE_SIMPLE -I. -I$(LVGL) -I$(LVGL)/src

all: vectors client render

build/lvgl/%.o: $(LVGL)/src/%.c lv_conf.h
	@mkdir -p $(dir $@)
	@$(CC) $(LVFLAGS) -c -o $@ $<

render: CXXFLAGS += -fsanitize=address -fno-omit-frame-pointer
render: $(COBJ) $(LVOBJ) $(CORE) $(UI)/source/arcade/ArcadeScreens.cpp render.cpp $(FONTS) $(wildcard $(UI)/include/arcade/*.h)
	$(CXX) $(CXXFLAGS) $(LVFLAGS) -o $@ $(CORE) $(UI)/source/arcade/ArcadeScreens.cpp render.cpp $(FONTS) $(COBJ) $(LVOBJ)

client: $(COBJ) $(CORE) client.cpp $(wildcard $(UI)/include/arcade/*.h)
	$(CXX) $(CXXFLAGS) -o $@ $(CORE) client.cpp $(COBJ)

vectors: $(COBJ) $(CXXSRC) $(wildcard $(UI)/include/arcade/*.h)
	$(CXX) $(CXXFLAGS) -o $@ $(CXXSRC) $(COBJ)

build/%.o: $(CSRC) $(V)/arcade_rename.h
	@mkdir -p build
	$(CC) $(CFLAGS) -c -o $@ $(filter %/$*.c,$(CSRC))

clean:
	rm -rf build vectors client render
