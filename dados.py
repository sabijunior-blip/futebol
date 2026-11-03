#!/usr/bin/env python3
"""Descarrega jogos da ESPN (dia a dia, o formato que funciona) e guarda-os em data/<liga>.json.
Cada execução atualiza os próximos dias e vai alargando o histórico e o calendário até cobrir
a época inteira. É retomável: se parar a meio, continua na execução seguinte."""
import json, os, time, datetime, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

LEAGUES = ["por.1","por.2","por.taca.portugal","por.league_cup","uefa.champions","uefa.europa","uefa.europa.conf",
 "eng.1","eng.2","eng.fa","eng.league_cup","esp.1","esp.copa_del_rey","ita.1","ita.coppa_italia",
 "ger.1","ger.dfb_pokal","fra.1","fra.coupe_de_france"]
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/"
UA = "Mozilla/5.0 (compatible; FutebolPessoal/1.0; uso pessoal)"
BUDGET = 20 * 60          # segundos por execução
T0 = time.time()

def get(url):
    """devolve (json|None, código). Não repete em erros 4xx."""
    code = None
    for i in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r), 200
        except urllib.error.HTTPError as e:
            code = e.code
            if 400 <= e.code < 500:
                return None, e.code
        except Exception:
            code = -1
        time.sleep(1.5)
    return None, code

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

def one(task):
    lid, d = task
    if time.time() - T0 > BUDGET:
        return lid, d, None, "tempo"
    data, code = get(f"{ESPN}{lid}/scoreboard?dates={d:%Y%m%d}")
    return lid, d, ([slim(e) for e in data.get("events", [])] if data else None), code

def run(days, leagues, store):
    tasks = [(l, d) for l in leagues for d in days]
    ok = bad = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for lid, d, evs, code in ex.map(one, tasks):
            if evs is None:
                bad += 1
                continue
            ok += 1
            for e in evs:
                store[lid][e["id"]] = e
    print(f"pedidos ok={ok} falhados={bad}", flush=True)
    return bad == 0

def main():
    os.makedirs("data", exist_ok=True)
    today = datetime.date.today()
    y = today.year if today.month >= 7 else today.year - 1
    s0, s1 = datetime.date(y, 7, 1), datetime.date(y + 1, 6, 30)
    # só as competições que a ESPN tem
    valid = []
    for lid in LEAGUES:
        data, code = get(f"{ESPN}{lid}/scoreboard?dates={today:%Y%m%d}")
        print(lid, "ok" if data else f"indisponível ({code})", flush=True)
        if data:
            valid.append(lid)
    store = {}
    for lid in valid:
        store[lid] = {}
        p = f"data/{lid}.json"
        if os.path.exists(p):
            try:
                for e in json.load(open(p, encoding="utf-8"))["events"]:
                    store[lid][e["id"]] = e
            except Exception:
                pass
    mp = "data/_meta.json"
    meta = json.load(open(mp)) if os.path.exists(mp) else None
    rng = lambda a, b: [a + datetime.timedelta(days=i) for i in range((b - a).days + 1)]
    run(rng(today - datetime.timedelta(days=3), today + datetime.timedelta(days=14)), valid, store)
    if meta is None:
        lo, hi = today - datetime.timedelta(days=3), today + datetime.timedelta(days=14)
    else:
        lo, hi = datetime.date.fromisoformat(meta["from"]), datetime.date.fromisoformat(meta["to"])
    while time.time() - T0 < BUDGET and (lo > s0 or hi < s1):
        nlo, nhi = max(s0, lo - datetime.timedelta(days=30)), min(s1, hi + datetime.timedelta(days=30))
        days = (rng(nlo, lo - datetime.timedelta(days=1)) if nlo < lo else []) + (rng(hi + datetime.timedelta(days=1), nhi) if nhi > hi else [])
        if not run(days, valid, store):
            break
        lo, hi = nlo, nhi
        json.dump({"from": lo.isoformat(), "to": hi.isoformat()}, open(mp, "w"))
    total = 0
    for lid in valid:
        ev = sorted(store[lid].values(), key=lambda e: (e["date"], e["id"]))
        new = json.dumps({"events": ev}, ensure_ascii=False, separators=(",", ":"))
        p = f"data/{lid}.json"
        if not os.path.exists(p) or open(p, encoding="utf-8").read() != new:
            open(p, "w", encoding="utf-8").write(new)
        total += len(ev)
    print("jogos", total, "cobertura", lo, hi, f"({int(time.time() - T0)}s)")

if __name__ == "__main__":
    main()
