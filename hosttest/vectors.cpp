// Host test driver: one command per run, answers on stdout, one value per line.
#include "arcade/Crypto.h"
#include "arcade/Frames.h"
#include "arcade/Keys.h"
#include "arcade/Mailbox.h"
#include "arcade/Snapshot.h"
#include "arcade/Envelope.h"
#include "arcade/Tx.h"
#include <cstdio>
#include <fstream>
#include <cstdlib>
#include <string>

using namespace arcade;

static Bytes unhex(const std::string &h)
{
    Bytes b;
    for (size_t i = 0; i + 1 < h.size(); i += 2)
        b.push_back((uint8_t)strtol(h.substr(i, 2).c_str(), nullptr, 16));
    return b;
}
static void hexln(const uint8_t *p, size_t n) { printf("%s\n", toHex(p, n).c_str()); }

int main(int argc, char **argv)
{
    std::string cmd = argc > 1 ? argv[1] : "";
    if (cmd == "keys") { // phrase
        Account a(argv[2]);
        hexln(a.loginPublic(), 32);
        hexln(a.mailPublic(), 32);
        uint8_t pub[33];
        a.coinPublic("test", pub);
        hexln(pub, 33);
        printf("%s\n%s\n%s\n", a.address("test", 113).c_str(), a.address("main", 56).c_str(), a.address("doge", 30).c_str());
        uint8_t sig[64];
        a.signLogin("http://127.0.0.1:8420", "n0nce", sig);
        hexln(sig, 64);
    } else if (cmd == "valid") {
        printf("%d\n", phraseValid(argv[2]) ? 1 : 0);
    } else if (cmd == "newphrase") {
        printf("%s\n", newPhrase().c_str());
    } else if (cmd == "sign") { // phrase network digesthex
        Account a(argv[2]);
        Bytes d = unhex(argv[4]);
        uint8_t out[73];
        size_t n = a.signDigest(argv[3], d.data(), out);
        hexln(out, n);
    } else if (cmd == "check") { // phrase network raw values(csv) payscript amount feecap
        Account a(argv[2]);
        uint8_t pub[33];
        a.coinPublic(argv[3], pub);
        std::vector<uint64_t> vals;
        std::string csv = argv[5];
        for (size_t at = 0; at < csv.size();) {
            size_t c = csv.find(',', at);
            if (c == std::string::npos) c = csv.size();
            vals.push_back(strtoull(csv.substr(at, c - at).c_str(), nullptr, 10));
            at = c + 1;
        }
        Checked c = checkOffer(unhex(argv[4]), vals, pub, unhex(argv[6]), strtoull(argv[7], nullptr, 10),
                               strtoull(argv[8], nullptr, 10));
        printf("%d\n%s\n%llu %llu %llu\n", c.ok, c.why.c_str(), (unsigned long long)c.paid,
               (unsigned long long)c.change, (unsigned long long)c.fee);
        for (auto &d : c.digests) hexln(d.data(), 32);
    } else if (cmd == "frames") { // type id bodyhex -> frames hex, then rejoined body
        Bytes body = unhex(argc > 4 ? argv[4] : "");
        auto fs = split((uint8_t)atoi(argv[2]), (uint16_t)atoi(argv[3]), body);
        Joiner j;
        Message m;
        bool done = false;
        for (auto it = fs.rbegin(); it != fs.rend(); ++it) {
            hexln(it->data(), it->size());
            done = j.add(7, it->data(), it->size(), 0, m);
        }
        printf("%s\n", done ? toHex(m.body.data(), m.body.size()).c_str() : "-");
    } else if (cmd == "box") { // keyhex noncehex msghex
        Bytes k = unhex(argv[2]), n = unhex(argv[3]), m = unhex(argc > 4 ? argv[4] : ""), out, back;
        secretboxSeal(k.data(), n.data(), m.data(), m.size(), out);
        hexln(out.data(), out.size());
        printf("%d\n", secretboxOpen(k.data(), n.data(), out.data(), out.size(), back) && back == m);
    } else if (cmd == "book") { // phrase blob-file
        Account a(argv[2]);
        std::ifstream f(argv[3]);
        std::string blob((std::istreambuf_iterator<char>(f)), {});
        Book b = openMailboxBook(a.mailSecret(), blob);
        printf("%d %zu %zu %s\n", b.ok, b.contacts.size(), b.removed, b.why.c_str());
        for (auto &c : b.contacts)
            printf("%s|%s|%s|%s\n", c.tag.c_str(), c.address.c_str(), c.name.c_str(), toHex(c.key, 32).c_str());
    } else if (cmd == "account" || cmd == "coins") { // json-file
        std::ifstream f(argv[2]);
        std::string js((std::istreambuf_iterator<char>(f)), {});
        if (cmd == "account") {
            Snapshot sn;
            bool ok = readAccount(js.data(), js.size(), sn);
            printf("%d %s %zu\n", ok, sn.tag.c_str(), sn.chains.size());
            for (auto &c : sn.chains)
                printf("%s|%s|%d|%d|%u|%u|%llu|%llu\n", c.network.c_str(), c.label.c_str(), c.tags, c.mainnet, c.p2pkh, c.p2sh,
                       (unsigned long long)c.confirmed, (unsigned long long)c.pending);
        } else {
            std::vector<Coin> cs;
            bool ok = readCoins(js.data(), js.size(), cs);
            printf("%d %zu\n", ok, cs.size());
            for (size_t i = 0; i < cs.size() && i < 3; i++)
                printf("%s:%u %llu\n", toHex(cs[i].txid, 32).c_str(), cs[i].vout, (unsigned long long)cs[i].value);
        }
    } else if (cmd == "seal") { // phrase theirKeyHex text
        Account a(argv[2]);
        Bytes k = unhex(argv[3]);
        Bytes sealed = sealMessage(a, k.data(), argv[4]);
        hexln(sealed.data(), sealed.size());
    } else if (cmd == "open") { // phrase sealedHex
        Account a(argv[2]);
        Opened o = openMessage(a, unhex(argv[3]));
        printf("%d %s %d\n%s\n", o.ok, toHex(o.sender, 32).c_str(), o.hadFile, o.text.c_str());
    } else {
        fprintf(stderr, "unknown command\n");
        return 2;
    }
    return 0;
}
