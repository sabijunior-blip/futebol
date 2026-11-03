#!/usr/bin/env python3
"""Descarrega jogos (época inteira, passados e futuros, com golos e cartões) da ESPN
e guarda-os em data/<liga>.json. Corre no GitHub Actions, por isso a app não precisa de
pedir tudo ao telemóvel."""
import json, os, sys, time, datetime, urllib.request

LEAGUES = ["por.1","por.taca.portugal","por.league_cup","uefa.champions","uefa.europa","uefa.europa.conf",
 "eng.1","eng.2","eng.fa","eng.league_cup","esp.1","esp.copa_del_rey","ita.1","ita.coppa_italia",
 "ger.1","ger.dfb_pokal","fra.1","fra.coupe_de_france"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/"
UA = "Mozilla/5.0 (compatible; FutebolPessoal/1.0; uso pessoal)"

def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(1.5 * (i + 1))
    return None

def slim(e):
    c = (e.get("competitions") or [{}])[0]
    comps = []
    for x in c.get("competitors", []):
        t = x.get("team", {})
        comps.append({"homeAway": x.get("homeAway"), "score": x.get("score"),
                      "team": {k: t.get(k) for k in ("id", "displayName", "shortDisplayName", "logo")}})
    det = []
    for d in c.get("details", []) or []:
        det.append({"type": {"text": (d.get("type") or {}).get("text")},
                    "clock": {"displayValue": (d.get("clock") or {}).get("displayValue"),
                              "value": (d.get("clock") or {}).get("value")},
                    "team": {"id": (d.get("team") or {}).get("id")},
                    "athletesInvolved": [{"displayName": a.get("displayName")} for a in d.get("athletesInvolved", [])]})
    v = c.get("venue") or {}
    st = (e.get("status") or {}).get("type") or {}
    return {"id": e["id"], "date": e["date"],
            "status": {"type": {"state": st.get("state"), "shortDetail": st.get("shortDetail")}},
            "competitions": [{"competitors": comps,
                              "venue": {"fullName": v.get("fullName"), "address": {"city": (v.get("address") or {}).get("city")}},
                              "details": det}]}

def fetch_range(lid, a, b):
    base = f"{ESPN}{lid}/scoreboard?dates={a:%Y%m%d}-{b:%Y%m%d}"
    d = get(base + "&limit=500") or get(base)
    if d is not None:
        return [slim(e) for e in d.get("events", [])]
    out, day = [], a
    while day <= b:                       # último recurso: dia a dia
        d = get(f"{ESPN}{lid}/scoreboard?dates={day:%Y%m%d}")
        out += [slim(e) for e in (d or {}).get("events", [])]
        day += datetime.timedelta(days=1); time.sleep(0.3)
    return out

def main():
    today = datetime.date.today()
    y = today.year if today.month >= 7 else today.year - 1
    season = (datetime.date(y, 7, 1), datetime.date(y + 1, 6, 30))
    os.makedirs("data", exist_ok=True)
    total = 0
    for lid in LEAGUES:
        path = f"data/{lid}.json"
        old = {}
        if os.path.exists(path):
            try:
                old = {e["id"]: e for e in json.load(open(path, encoding="utf-8")).get("events", [])}
            except Exception:
                old = {}
        full = (not old) or (today.weekday() == 0 and datetime.datetime.utcnow().hour < 1)
        ranges = []
        if full:
            d = season[0]
            while d <= season[1]:
                e = min((d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1), season[1])
                ranges.append((d, e)); d = e + datetime.timedelta(days=1)
        else:
            ranges.append((today - datetime.timedelta(days=4), today + datetime.timedelta(days=21)))
        for a, b in ranges:
            for e in fetch_range(lid, a, b):
                old[e["id"]] = e
            time.sleep(0.4)
        ev = sorted(old.values(), key=lambda e: (e["date"], e["id"]))
        new = json.dumps({"events": ev}, ensure_ascii=False, separators=(",", ":"))
        if not os.path.exists(path) or open(path, encoding="utf-8").read() != new:
            open(path, "w", encoding="utf-8").write(new)
        total += len(ev)
        print(lid, len(ev))
    print("total", total)

if __name__ == "__main__":
    main()
