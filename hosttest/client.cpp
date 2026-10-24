// Runs ArcadeClient on stdin/stdout so a Python gateway can talk to it.
//   in:  "rx <from hex> <frame hex>" | "tick <ms>" | "create <pin> <phrase...>" | "unlock <pin>" | "lock"
//        "bal" | "who <tag>" | "send <chain> <amount> <to>" | "confirm" | "state"
//   out: "tx <to hex> <frame hex>" and "state ..." lines
#include "arcade/ArcadeClient.h"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <sys/stat.h>

using namespace arcade;

class DirStorage : public Storage
{
  public:
    explicit DirStorage(std::string d) : dir(std::move(d)) { mkdir(dir.c_str(), 0700); }
    bool load(const std::string &n, Bytes &out) override
    {
        std::ifstream f(dir + "/" + n, std::ios::binary);
        if (!f)
            return false;
        out.assign(std::istreambuf_iterator<char>(f), {});
        return true;
    }
    bool save(const std::string &n, const Bytes &d) override
    {
        std::ofstream f(dir + "/" + n, std::ios::binary | std::ios::trunc);
        f.write((const char *)d.data(), d.size());
        return (bool)f;
    }
    void remove(const std::string &n) override { ::remove((dir + "/" + n).c_str()); }
    std::string dir;
};

static Bytes unhex(const std::string &h)
{
    Bytes b;
    for (size_t i = 0; i + 1 < h.size(); i += 2)
        b.push_back((uint8_t)strtol(h.substr(i, 2).c_str(), nullptr, 16));
    return b;
}

static const char *linkName(ArcadeClient::Link l)
{
    switch (l) {
    case ArcadeClient::Link::Locked: return "locked";
    case ArcadeClient::Link::Searching: return "searching";
    case ArcadeClient::Link::SigningIn: return "signing-in";
    case ArcadeClient::Link::Online: return "online";
    default: return "no-account";
    }
}

int main(int argc, char **argv)
{
    DirStorage st(argc > 1 ? argv[1] : "/tmp/arcade-client");
    ArcadeClient c(st, 0x970046A4);
    uint32_t now = 1000;
    c.sendFrame = [](uint32_t to, const Bytes &f) {
        printf("tx %08x %s\n", to, toHex(f.data(), f.size()).c_str());
        fflush(stdout);
    };
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        std::string cmd;
        in >> cmd;
        if (cmd == "rx") {
            std::string from, hex;
            in >> from >> hex;
            Bytes f = unhex(hex);
            c.receive((uint32_t)strtoul(from.c_str(), nullptr, 16), f.data(), f.size(), now);
        } else if (cmd == "tick") {
            in >> now;
            c.tick(now);
        } else if (cmd == "create") {
            std::string pin, w, phrase;
            in >> pin;
            while (in >> w)
                phrase += (phrase.empty() ? "" : " ") + w;
            printf("created %d\n", c.createAccount(phrase, pin));
        } else if (cmd == "unlock") {
            std::string pin;
            in >> pin;
            printf("unlocked %d\n", c.unlock(pin));
        } else if (cmd == "lock") {
            c.lock();
        } else if (cmd == "bal") {
            c.refreshBalances();
        } else if (cmd == "who") {
            std::string t;
            in >> t;
            c.addContact(t);
        } else if (cmd == "send") {
            size_t chain;
            unsigned long long amount;
            std::string to;
            in >> chain >> amount >> to;
            c.askToSend(chain, to, amount);
        } else if (cmd == "confirm") {
            c.confirmSend();
        } else if (cmd == "msg") {
            std::string tag, w, text, why;
            in >> tag;
            while (in >> w)
                text += (text.empty() ? "" : " ") + w;
            printf("msg %d %s\n", c.sendMessage(tag, text, why), why.c_str());
        } else if (cmd == "cancelq") {
            size_t i;
            in >> i;
            printf("cancelled %d\n", c.cancelQueued(i));
        } else if (cmd == "resend") {
            std::string tag, why;
            size_t i;
            in >> tag >> i;
            printf("resend %d %s\n", c.resendMessage(tag, i, why), why.c_str());
        } else if (cmd == "thread") {
            std::string tag;
            in >> tag;
            for (auto &l : c.thread(tag))
                printf("letter %d %d %s|%s|%s\n", l.mine, l.state, l.txid.c_str(), l.text.c_str(), l.why.c_str());
            printf("unread %d\n", c.unread.count(tag) ? c.unread[tag] : 0);
        } else if (cmd == "state") {
            printf("state link=%s tag=%s gw=%08x status=%s\n", linkName(c.link), c.tag.c_str(), c.gateway, c.status.c_str());
            for (size_t i = 0; i < c.chains.size(); i++)
                printf("state avail %s %llu\n", c.chains[i].network.c_str(), (unsigned long long)c.available(i));
            for (auto &ch : c.chains)
                printf("state chain %s %llu %llu reg=%d\n", ch.network.c_str(), (unsigned long long)ch.confirmed,
                       (unsigned long long)ch.pending, ch.registered);
            for (auto &k : c.contacts)
                printf("state contact %s %s\n", k.tag.c_str(), k.address.c_str());
            printf("state send %d why=%s txid=%s fee=%llu change=%llu\n", (int)c.send.state, c.send.why.c_str(),
                   c.send.txid.c_str(), (unsigned long long)c.send.fee, (unsigned long long)c.send.change);
            printf("state who %d %s %s\n", (int)c.who.state, c.who.tag.c_str(), c.who.why.c_str());
            printf("state end\n");
        }
        fflush(stdout);
    }
    return 0;
}
