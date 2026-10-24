// Draws the arcade screens into a 320x240 framebuffer and writes PPM files,
// so the screens can be looked at (and shown) before anything is flashed.
#include "arcade/ArcadeScreens.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sys/stat.h>

using namespace arcade;

static uint16_t fb[320 * 240];
static std::vector<uint32_t> keys;     // a virtual T-Deck keyboard
struct Tap { int x, y; };
static Tap tapAt = {-1, -1};           // a virtual finger on the touchscreen

static void readTouch(lv_indev_t *, lv_indev_data_t *d)
{
    if (tapAt.x < 0) {
        d->state = LV_INDEV_STATE_RELEASED;
        return;
    }
    d->point.x = tapAt.x;
    d->point.y = tapAt.y;
    d->state = LV_INDEV_STATE_PRESSED;
}
static bool keyDown = false;

static void readKeys(lv_indev_t *, lv_indev_data_t *d)
{
    // each key: one read pressed, one read released
    if (keys.empty()) {
        d->state = LV_INDEV_STATE_RELEASED;
        return;
    }
    d->key = keys.front();
    if (!keyDown) {
        d->state = LV_INDEV_STATE_PRESSED;
        keyDown = true;
    } else {
        d->state = LV_INDEV_STATE_RELEASED;
        keyDown = false;
        keys.erase(keys.begin());
    }
}
static uint32_t fakeMs = 0;

static void flush(lv_display_t *d, const lv_area_t *a, uint8_t *px)
{
    int w = a->x2 - a->x1 + 1;
    for (int y = a->y1; y <= a->y2; y++)
        memcpy(&fb[y * 320 + a->x1], px + (y - a->y1) * w * 2, w * 2);
    lv_display_flush_ready(d);
}

static void save(const std::string &path)
{
    FILE *f = fopen(path.c_str(), "wb");
    fprintf(f, "P6 320 240 255\n");
    for (int i = 0; i < 320 * 240; i++) {
        uint16_t c = fb[i];
        uint8_t rgb[3] = {(uint8_t)((c >> 11) << 3 | (c >> 13)), (uint8_t)(((c >> 5) & 63) << 2 | ((c >> 9) & 3)),
                          (uint8_t)((c & 31) << 3 | ((c >> 2) & 7))};
        fwrite(rgb, 1, 3, f);
    }
    fclose(f);
}

class MemStorage : public Storage
{
  public:
    std::map<std::string, Bytes> files;
    bool load(const std::string &n, Bytes &o) override
    {
        auto it = files.find(n);
        if (it == files.end())
            return false;
        o = it->second;
        return true;
    }
    bool save(const std::string &n, const Bytes &d) override { files[n] = d; return true; }
    void remove(const std::string &n) override { files.erase(n); }
};

static void settle(int rounds = 6)
{
    for (int i = 0; i < rounds; i++) {
        fakeMs += 40;
        lv_timer_handler();
    }
}

int main(int argc, char **argv)
{
    std::string out = argc > 1 ? argv[1] : "shots";
    mkdir(out.c_str(), 0755);
    lv_init();
    lv_tick_set_cb([]() -> uint32_t { return fakeMs; });
    lv_display_t *disp = lv_display_create(320, 240);
    static uint8_t buf[320 * 240 * 2];
    lv_display_set_buffers(disp, buf, nullptr, sizeof(buf), LV_DISPLAY_RENDER_MODE_PARTIAL);
    lv_display_set_flush_cb(disp, flush);
    lv_group_t *g = lv_group_create();
    lv_indev_t *kb = lv_indev_create();
    lv_indev_set_type(kb, LV_INDEV_TYPE_KEYPAD);
    lv_indev_set_read_cb(kb, readKeys);
    lv_indev_set_group(kb, g);
    lv_indev_t *touch = lv_indev_create();
    lv_indev_set_type(touch, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(touch, readTouch);

    MemStorage st;
    ArcadeClient client(st, 0x970046A4);
    ArcadeScreens ui(client, st);
    client.changed = [&]() { ui.clientChanged(); };
    ui.setBattery(87);
    ui.setClock(1792808000);
    ui.setMyNode(0x970046A4);
    ui.begin(g);

    auto shot = [&](const std::string &name) {
        ui.tick(fakeMs);
        settle();
        save(out + "/" + name + ".ppm");
    };
    // the very first boot
    shot("01-welcome");
    ui.show(ArcadeScreens::Scr::Words);
    shot("02-words");
    // type the twelve words the way a person does on the T-Deck: a few
    // letters, Enter (the crash: Enter used to rebuild inside the key event)
    const char *typed[] = {"aban", "aband", "abando", "abandon", "abandon", "abandon", "abandon", "abandon", "abandon", "abandon", "abandon", "abou"};
    for (int w = 0; w < 12; w++) {
        for (const char *c = typed[w]; *c; c++)
            keys.push_back((uint32_t)*c);
        keys.push_back(LV_KEY_ENTER);
        for (int i = 0; i < 40 && !keys.empty(); i++) {
            ui.tick(fakeMs);
            settle(1);
        }
        ui.tick(fakeMs);
        settle(2);
    }
    shot("02b-words-done");
    keys.push_back(LV_KEY_BACKSPACE);   // empty box: takes back word 12
    for (int i = 0; i < 6; i++) { ui.tick(fakeMs); settle(1); }
    shot("02c-words-backspace");
    // then the PIN, twice, and the slow sealing step after its screen shows
    for (uint32_t k : std::vector<uint32_t>{LV_KEY_ENTER, '4', '8', '2', '9', '1', '6', LV_KEY_ENTER, '4', '8', '2', '9', '1', '6', LV_KEY_ENTER})
        keys.push_back(k);
    for (int i = 0; i < 200 && (!keys.empty() || ui.current() != ArcadeScreens::Scr::Wallet); i++) {
        ui.tick(fakeMs);
        settle(1);
    }
    printf("after setup: screen=%d account=%d unlocked=%d\n", (int)ui.current(), client.hasAccount(), client.unlocked());
    shot("02d-after-pin");
    client.lock();
    ui.show(ArcadeScreens::Scr::Welcome);
    st.files.clear();
    client.createAccount("abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about", "482916");
    client.lock();
    ui.show(ArcadeScreens::Scr::Lock);
    shot("03-lock");
    client.unlock("482916");

    // a signed-in account, as the gateway on .25 would leave it
    client.link = ArcadeClient::Link::Online;
    client.tag = "bigchief";
    client.gateway = 0x433C8154;
    client.gatewayName = "PBR test gateway";
    client.gatewayHost = "127.0.0.1:18420";
    client.status = "Online through PBR test gateway";
    Chain a; a.network = "test"; a.label = "Pepecoin"; a.tags = true; a.p2pkh = 113; a.p2sh = 196; a.confirmed = 128450000000ULL; a.pending = 1000000;
    Chain b; b.network = "doge"; b.label = "Dogecoin"; b.mainnet = true; b.p2pkh = 30; b.p2sh = 22; b.confirmed = 4218000000ULL;
    Chain c; c.network = "ltc"; c.label = "Litecoin"; c.mainnet = true; c.p2pkh = 48; c.p2sh = 50; c.confirmed = 3150000;
    client.chains = {a, b, c};
    Contact r; r.tag = "robin"; r.name = "Robin"; r.address = "nKh3VqPZx7bT1mWcYfQe8sRgD2hJT8pR2a";
    Contact s; s.tag = "strawberry"; s.name = "Strawberry"; s.address = "nWKJgSeAZSmfRCxZnwVgtYyPNowQT5X1Gk";
    Contact p; p.tag = "apple"; p.name = "Apple"; p.address = "nAp1eQ8x2LmZ7cVtB5sRkW3uYhJ9dF4gE6";
    client.contacts = {r, s, p};
    Activity x; x.who = "@robin"; x.symbol = "PEP"; x.amount = -125000000; x.txid = "4e5b";
    Activity y; y.who = "@strawberry"; y.symbol = "PEP"; y.amount = -10000000000LL; y.txid = "9a1c";
    client.activity = {x, y};

    client.payQueue = {{"test", "@robin", 2500000000ULL, 1792811000}, {"doge", "@strawberry", 150000000ULL, 1792811600}};
    ui.show(ArcadeScreens::Scr::Wallet);
    shot("15-wallet-waiting");
    client.payQueue.clear();
    for (size_t k = 0; k < 6; k++) {
        ui.setSkin(k);
        ui.show(ArcadeScreens::Scr::Wallet);
        char n[40];
        snprintf(n, sizeof(n), "10-wallet-skin%zu", k);
        shot(n);
    }
    ui.setSkin(1);
    ui.show(ArcadeScreens::Scr::Wallet);
    ui.sendTo = "@ro";
    ui.sendAmount = "";
    client.cancelSend();
    ui.show(ArcadeScreens::Scr::Send);
    shot("20-send-form");
    ui.sendTo = "";
    ui.show(ArcadeScreens::Scr::Send);
    shot("20b-send-empty");
    // a tap on the second wallet card's text (its layout box, not the card) must reach the card
    ui.show(ArcadeScreens::Scr::Wallet);
    ui.tick(fakeMs); settle(2);
    tapAt = {250, 108};
    for (int i = 0; i < 8; i++) { ui.tick(fakeMs); settle(1); }
    tapAt = {-1, -1};
    for (int i = 0; i < 8; i++) { ui.tick(fakeMs); settle(1); }
    printf("tap on wallet card: screen=%d\n", (int)ui.current());
    // a swipe left on a tab goes to the next tab
    ui.show(ArcadeScreens::Scr::Contacts);
    ui.tick(fakeMs); settle(2);
    for (int x = 260; x >= 40; x -= 20) { tapAt = {x, 150}; ui.tick(fakeMs); settle(1); }
    tapAt = {-1, -1};
    for (int i = 0; i < 8; i++) { ui.tick(fakeMs); settle(1); }
    printf("swipe left on Contacts: screen=%d\n", (int)ui.current());
    client.send.state = ArcadeClient::SendState::Review;
    client.send.chain = 0;
    client.send.toTag = "robin";
    client.send.toAddress = r.address;
    client.send.amount = 2500000000ULL;
    client.send.fee = 2260000;
    client.send.change = 125947740000ULL;
    ui.show(ArcadeScreens::Scr::Send);
    shot("21-send-review");
    client.send.state = ArcadeClient::SendState::Sent;
    client.send.txid = "4e5b31362cb02b8e36ac6613f7eb52991afea2b2ff7a6c170ae7db7d0a395ddb";
    ui.show(ArcadeScreens::Scr::Send);
    shot("22-send-sent");
    client.send.state = ArcadeClient::SendState::Failed;
    client.send.why = "Refused: an output pays somebody this T-Deck did not name";
    ui.show(ArcadeScreens::Scr::Send);
    shot("23-send-refused");
    client.cancelSend();
    ui.show(ArcadeScreens::Scr::Contacts);
    shot("30-contacts");
    ui.show(ArcadeScreens::Scr::Mesh);
    shot("40-mesh");
    ui.show(ArcadeScreens::Scr::Receive);
    shot("50-receive");
    ui.wifiSsid = "PBR-home";
    ui.wifiPass = "hunter22";
    client.wifiNets = {{"PBR-home", -48, true}, {"PBR-barn", -66, true}, {"xfinitywifi", -74, false}, {"NETGEAR42", -83, true}};
    ui.show(ArcadeScreens::Scr::Wifi);
    shot("60-wifi");
    client.wifi.ssid = "PBR-home";
    client.wifiProgress(ArcadeClient::WifiState::Downloading);
    ui.show(ArcadeScreens::Scr::Wifi);
    shot("61-wifi-downloading");
    client.wifi.imported = 14;
    client.wifi.removed = 2;
    client.wifiProgress(ArcadeClient::WifiState::Done);
    ui.show(ArcadeScreens::Scr::Wifi);
    shot("62-wifi-done");
    RadioState rs;
    rs.known = true; rs.gpsMode = 1; rs.sats = 9; rs.fix = true; rs.lat = 47.13636; rs.lon = -95.82867; rs.alt = 461;
    rs.btEnabled = true; rs.btPin = 861077; rs.btConnected = false; rs.powerSaving = false; rs.screenTimeout = 60;
    rs.longName = "@bigchief"; rs.firmware = "2.8.2.e039e34";
    ui.setRadioState(rs);
    ui.show(ArcadeScreens::Scr::Settings);
    shot("70-settings");
    {
        auto &t = client.thread("robin");
        Letter a; a.mine = false; a.state = Letter::Received; a.when = 1792807000; a.text = "are you at the cabin this weekend?";
        Letter b; b.mine = true; b.state = Letter::Sent; b.when = 1792807200; b.text = "yes, Saturday. bring the canoe"; b.txid = "ab";
        Letter c; c.mine = false; c.state = Letter::TooLong; c.when = 1792807400; c.text = "Message too long for LoRa (1204 bytes). Read it on the arcade.";
        Letter d; d.mine = true; d.state = Letter::Sending; d.when = 1792808000; d.text = "on my way";
        t = {a, b, c, d};
        client.unread["strawberry"] = 2;
        client.thread("strawberry").push_back(a);
    }
    ui.show(ArcadeScreens::Scr::Messages);
    shot("80-messages");
    ui.show(ArcadeScreens::Scr::Messages);
    ui.chatTag = "robin";
    ui.draft = "see you there";
    ui.show(ArcadeScreens::Scr::Chat);
    shot("81-chat");
    return 0;
}
