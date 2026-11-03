#!/usr/bin/env python3
"""Lê o guia do Apito TV (apitotv.pt) e escreve canais.json com o canal de cada jogo.
Uso pessoal, poucos pedidos por dia. Se o site mudar de estrutura, o ficheiro antigo é mantido."""
import json, re, sys, time, datetime, urllib.request

BASE = "https://www.apitotv.pt"
PAGES = ["/", "/amanha", "/fim-de-semana"] + [
    "/competicao/" + c for c in [
        "liga-portugal", "taca-de-portugal", "liga-dos-campeoes", "liga-europa", "liga-conferencia",
        "serie-a", "premier-league", "laliga", "bundesliga", "liga-francesa"]]
UA = "Mozilla/5.0 (compatible; FutebolPessoal/1.0; uso pessoal)"

def norm(t):
    t = re.sub(r"\s+", " ", t).strip()
    m = re.fullmatch(r"SPTV\s?(\d|\+)?", t, re.I)
    if m:
        return "Sport TV" + ((" " + m.group(1)) if m.group(1) and m.group(1) != "+" else ("+" if m.group(1) == "+" else ""))
    if t.lower() == "sportingtv":
        return "Sporting TV"
    return t

def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept-Language": "pt-PT"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def parse(h):
    end = h.find("Sobre o Apito")
    if end > 0:
        h = h[:end]
    ms = list(re.finditer(r'href="/jogo/([a-z0-9\-]+)"', h))
    out = {}
    for i, m in enumerate(ms):
        slug = m.group(1)
        d = re.search(r"\d{4}-\d{2}-\d{2}", slug)
        if not d:
            continue
        chunk = h[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(h)][:5000]
        chans = []
        for im in re.findall(r"<img[^>]+/icons/channels/[^>]*>", chunk):
            a = re.search(r'(?:title|alt)="([^"]+)"', im)
            if a:
                chans.append(norm(a.group(1)))
        text = re.sub(r"<[^>]+>", " ", chunk)
        for t in re.findall(r"SPTV\s?\+?\d?|SportingTV", text):
            chans.append(norm(t))
        chans = list(dict.fromkeys(c for c in chans if c))
        if chans:
            out[slug] = {"s": slug, "d": d.group(0), "c": chans}
    return out

def main():
    allm = {}
    for p in PAGES:
        try:
            allm.update(parse(get(p)))
            print("ok", p, len(allm))
        except Exception as e:
            print("falhou", p, e)
        time.sleep(2)
    if not allm:
        print("nenhum jogo lido; mantém o ficheiro antigo")
        return
    lim = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
    res = sorted((v for v in allm.values() if v["d"] >= lim), key=lambda v: (v["d"], v["s"]))
    json.dump(res, open("canais.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("escritos", len(res))

main()
