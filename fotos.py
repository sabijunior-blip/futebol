#!/usr/bin/env python3
"""Constrói data/fotos.json com os plantéis e fotos dos clubes das ligas principais.
Usa a ESPN (grátis) e, para os jogadores sem foto, a API-Football (chave em segredo do GitHub,
no máximo 90 pedidos por execução). Cada clube é renovado de 30 em 30 dias."""
import json, os, re, time, unicodedata, urllib.request, urllib.parse

DOM = ["por.1","eng.1","eng.2","esp.1","ita.1","ger.1","fra.1"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/"
UA = "Mozilla/5.0 (compatible; FutebolPessoal/1.0; uso pessoal)"
KEY = os.environ.get("APIFOOTBALL_KEY", "")
calls = 0

def get(url, hdr=None):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(hdr or {})})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception:
        return None

def nz(s):
    return re.sub(r"[^a-z0-9 ]", "", unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower()).strip()

def af(path):
    global calls
    if not KEY or calls >= 90:
        return None
    calls += 1
    d = get("https://v3.football.api-sports.io/" + path, {"x-apisports-key": KEY})
    if not d or d.get("errors"):
        return None
    return d.get("response")

def teams():
    out = {}
    for lid in DOM:
        try:
            for e in json.load(open(f"data/{lid}.json", encoding="utf-8"))["events"]:
                for c in e["competitions"][0]["competitors"]:
                    out[c["team"]["id"]] = (lid, c["team"]["displayName"])
        except Exception:
            pass
    return out

def main():
    path = "data/fotos.json"
    db = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    now = int(time.time())
    todo = sorted(teams().items(), key=lambda kv: db.get(kv[0], {}).get("t", 0))
    done = 0
    for tid, (lid, name) in todo:
        if now - db.get(tid, {}).get("t", 0) < 30 * 86400 or done >= 40:
            continue
        d = get(f"{ESPN}{lid}/teams/{tid}/roster")
        if d is None:
            continue
        pl = []
        for a in d.get("athletes", []):
            for p in a.get("items", [a]):
                pl.append({"n": p.get("displayName") or p.get("fullName"), "h": (p.get("headshot") or {}).get("href", "")})
        com = sum(1 for p in pl if p["h"])
        if KEY and pl and com < 0.7 * len(pl):
            q = re.sub(r"\b(FC|CF|SC|CP|AFC)\b", "", name).strip().split(" ")[0]
            ts = af("teams?search=" + urllib.parse.quote(q)) or []
            t = next((x for x in ts if nz(x["team"]["name"]) == nz(name)), None) or next((x for x in ts if nz(q) in nz(x["team"]["name"])), None)
            sq = (af(f"players/squads?team={t['team']['id']}") or [{}])[0].get("players", []) if t else []
            for p in pl:
                if p["h"]:
                    continue
                n = nz(p["n"]); last = n.split(" ")[-1]
                m = next((x for x in sq if nz(x["name"]) == n), None) or next((x for x in sq if nz(x["name"]).split(" ")[-1] == last and nz(x["name"])[:1] == n[:1]), None)
                if m:
                    p["h"] = m.get("photo", "")
        db[tid] = {"t": now, "p": pl}
        done += 1
        print(name, len(pl), sum(1 for p in pl if p["h"]))
        time.sleep(0.5)
    open(path, "w", encoding="utf-8").write(json.dumps(db, ensure_ascii=False, separators=(",", ":")))
    print("clubes processados", done, "pedidos API-Football", calls)

if __name__ == "__main__":
    main()
