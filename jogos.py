#!/usr/bin/env python3
"""Para cada jogo terminado há mais de 3 horas que ainda não esteja na base de dados,
vai buscar eventos, estatísticas e constituições à ESPN e guarda em data/jogos/<id>.json.
Como um jogo terminado não muda, cada jogo só é pedido uma vez."""
import json, os, time, datetime, urllib.request

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/"
UA = "Mozilla/5.0 (compatible; FutebolPessoal/1.0; uso pessoal)"
MAX = 1500          # jogos por execução
LIMIT_S = 20 * 60   # tempo máximo por execução

def get(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None

def slim(d):
    ke = [{"t": (k.get("type") or {}).get("text"), "m": (k.get("clock") or {}).get("displayValue"),
           "v": (k.get("clock") or {}).get("value"), "tm": (k.get("team") or {}).get("id"),
           "p": [(p.get("athlete") or {}).get("displayName") for p in k.get("participants", []) if (p.get("athlete") or {}).get("displayName")],
           "x": k.get("shortText") or k.get("text")} for k in d.get("keyEvents", [])]
    st = [{"id": (t.get("team") or {}).get("id"), "s": {z.get("name"): z.get("displayValue") for z in t.get("statistics", [])}}
          for t in (d.get("boxscore") or {}).get("teams", [])]
    ro = []
    for r in d.get("rosters", []):
        tm = r.get("team") or {}
        ro.append({"ha": r.get("homeAway"), "tm": {"id": tm.get("id"), "displayName": tm.get("displayName"), "color": tm.get("color")},
                   "f": r.get("formation"),
                   "r": [{"st": p.get("starter"), "j": p.get("jersey"), "fp": p.get("formationPlace"),
                          "n": (p.get("athlete") or {}).get("displayName"), "sn": (p.get("athlete") or {}).get("shortName")}
                         for p in r.get("roster", [])]})
    return {"k": ke, "s": st, "r": ro}

def main():
    os.makedirs("data/jogos", exist_ok=True)
    cut = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
    todo = []
    for f in sorted(os.listdir("data")):
        if not f.endswith(".json") or f == "fotos.json":
            continue
        lid = f[:-5]
        try:
            ev = json.load(open("data/" + f, encoding="utf-8"))["events"]
        except Exception:
            continue
        for e in ev:
            if e["status"]["type"]["state"] != "post":
                continue
            try:
                dt = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00"))
            except Exception:
                continue
            if dt < cut and not os.path.exists(f"data/jogos/{e['id']}.json"):
                todo.append((dt, lid, e["id"]))
    todo.sort(reverse=True)               # primeiro os mais recentes
    print("em falta", len(todo))
    t0, n = time.time(), 0
    for dt, lid, eid in todo[:MAX]:
        if time.time() - t0 > LIMIT_S:
            break
        d = get(f"{ESPN}{lid}/summary?event={eid}")
        if d is None:
            continue
        open(f"data/jogos/{eid}.json", "w", encoding="utf-8").write(json.dumps(slim(d), ensure_ascii=False, separators=(",", ":")))
        n += 1
        time.sleep(0.25)
    print("guardados", n, "restam", max(0, len(todo) - n))

if __name__ == "__main__":
    main()
