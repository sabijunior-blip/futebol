#!/usr/bin/env python3
"""Junta notícias de futebol de vários jornais portugueses e guarda em data/noticias.json.
Descobre os feeds RSS a partir da página de cada jornal e acrescenta o Google News como reforço.
Guarda só título, imagem, fonte, data e ligação (nunca o texto da notícia)."""
import json, re, os, sys, html, datetime, unicodedata, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
SOURCES = [
    ("A Bola", "https://www.abola.pt"), ("Record", "https://www.record.pt"), ("O Jogo", "https://www.ojogo.pt"),
    ("Maisfutebol", "https://maisfutebol.iol.pt"), ("zerozero", "https://www.zerozero.pt"),
    ("Notícias ao Minuto", "https://www.noticiasaominuto.com/desporto"), ("RTP Desporto", "https://www.rtp.pt/noticias/desporto"),
    ("SAPO Desporto", "https://desporto.sapo.pt"), ("Observador", "https://observador.pt/seccao/desporto"),
    ("Público", "https://www.publico.pt/desporto"), ("CNN Portugal", "https://cnnportugal.iol.pt/desporto"),
    ("SIC Notícias", "https://sicnoticias.pt/desporto"), ("Bola na Rede", "https://bolanarede.pt"),
    ("Jornal de Notícias", "https://www.jn.pt/desporto"), ("Correio da Manhã", "https://www.cmjornal.pt/desporto"),
]
GUESS = ["/rss", "/feed", "/rss.xml", "/feed/", "/rss/desporto", "/rss/futebol"]
FUT = ["futebol", "liga", "golo", "jogo", "treinador", "jogador", "benfica", "sporting", "porto", "braga", "champions", "premier", "taça", "campeonato", "clube", "ucl"]
KW = {
    "por.1": ["benfica", "sporting", "fc porto", "braga", "liga portugal", "primeira liga", "liga betclic", "vitória sc", "guimarães", "famalicão", "gil vicente", "estoril", "casa pia", "rio ave", "arouca", "moreirense", "santa clara", "boavista", "estrela da amadora", "farense", "alverca", "tondela", "avs"],
    "por.2": ["liga portugal 2", "segunda liga", "liga 2"],
    "por.taca.portugal": ["taça de portugal"], "por.league_cup": ["taça da liga"],
    "uefa.champions": ["liga dos campeões", "champions league", "champions"], "uefa.europa": ["liga europa", "europa league"],
    "uefa.europa.conf": ["liga conferência", "conference league"],
    "eng.1": ["premier league", "manchester", "liverpool", "arsenal", "chelsea", "tottenham", "newcastle", "aston villa"],
    "eng.2": ["championship"], "eng.fa": ["fa cup"], "eng.league_cup": ["carabao", "taça da liga inglesa"],
    "esp.1": ["la liga", "laliga", "real madrid", "barcelona", "atlético de madrid", "sevilha", "villarreal"], "esp.copa_del_rey": ["copa del rey", "taça do rei"],
    "ita.1": ["serie a", "juventus", "inter de milão", "milan", "nápoles", "roma", "lazio"], "ita.coppa_italia": ["coppa italia", "taça de itália"],
    "ger.1": ["bundesliga", "bayern", "dortmund", "leverkusen"], "ger.dfb_pokal": ["dfb-pokal", "taça da alemanha"],
    "fra.1": ["ligue 1", "psg", "paris saint-germain", "marselha", "mónaco"], "fra.coupe_de_france": ["taça de frança", "coupe de france"],
}
GN = [("por.1", 'Benfica OR Sporting OR "FC Porto" OR "Liga Portugal"'), ("uefa.champions", '"Liga dos Campeões"'),
      ("uefa.europa", '"Liga Europa"'), ("eng.1", '"Premier League"'), ("eng.2", "Championship"), ("esp.1", '"La Liga"'),
      ("ita.1", '"Serie A"'), ("ger.1", "Bundesliga"), ("fra.1", '"Ligue 1"'), ("por.taca.portugal", '"Taça de Portugal"')]
SITES = " OR ".join("site:" + d for d in ["abola.pt", "record.pt", "ojogo.pt", "maisfutebol.iol.pt", "zerozero.pt", "rtp.pt", "observador.pt", "publico.pt", "noticiasaominuto.com", "cnnportugal.iol.pt", "sapo.pt"])
NOW = datetime.datetime.now(datetime.timezone.utc)
CUT = NOW - datetime.timedelta(days=15)

def fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "pt-PT,pt;q=0.9"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
        return raw.decode("utf-8", "replace")
    except Exception:
        return None

def nz(s):
    return unicodedata.normalize("NFD", (s or "").lower()).encode("ascii", "ignore").decode()

def tags(text):
    t = nz(text)
    return [k for k, ws in KW.items() if any(re.search(r"(?<![a-z0-9])" + re.escape(nz(w)) + r"(?![a-z0-9])", t) for w in ws)]

def strip(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def tdate(s):
    if not s:
        return NOW
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return NOW
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d

def local(e):
    return e.tag.split("}")[-1]

def parse(text, source):
    out = []
    try:
        root = ET.fromstring(text.strip().encode("utf-8"))
    except Exception:
        return out
    for it in root.iter():
        if local(it) not in ("item", "entry"):
            continue
        f = {}
        img = ""
        for c in it:
            n = local(c)
            if n in ("content", "thumbnail") and c.get("url"):
                if not img:
                    img = c.get("url")
                continue
            if n == "link":
                f["link"] = c.get("href") or (c.text or "").strip()
                if c.get("rel") == "enclosure" and (c.get("type") or "").startswith("image"):
                    img = c.get("href")
            elif n in ("title", "description", "summary", "content", "encoded", "pubDate", "published", "updated", "date"):
                f[n] = c.text or ""
            elif n in ("content", "thumbnail") and c.get("url") and not img:
                img = c.get("url")
            elif n == "enclosure" and (c.get("type") or "").startswith("image"):
                img = c.get("url") or img
        if not img:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)', html.unescape((f.get("encoded") or "") + (f.get("description") or "") + (f.get("summary") or "") + (f.get("content") or "")))
            img = m.group(1) if m else ""
        title = strip(f.get("title"))
        link = f.get("link")
        if not title or not link:
            continue
        d = tdate(f.get("pubDate") or f.get("published") or f.get("updated") or f.get("date"))
        desc = strip(f.get("description") or f.get("summary") or "")[:300]
        out.append({"t": title, "u": link, "i": img if img.startswith("http") else "", "s": source, "d": d.isoformat(), "x": desc})
    return out

def discover(home):
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(home))
    urls = []
    h = fetch(home)
    if h:
        for m in re.finditer(r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', h, re.I):
            m2 = re.search(r'href=["\']([^"\']+)', m.group(0))
            if m2:
                urls.append(urllib.parse.urljoin(home, html.unescape(m2.group(1))))
    urls += [base + g for g in GUESS]
    return list(dict.fromkeys(urls))

def source_items(src):
    name, home = src
    for u in discover(home)[:8]:
        t = fetch(u)
        if t and ("<rss" in t[:500].lower() or "<feed" in t[:500].lower() or "<?xml" in t[:100].lower()):
            items = parse(t, name)
            if items:
                print(f"ok {name}: {len(items)} notícias ({u})", flush=True)
                return items
    print(f"sem feed: {name}", flush=True)
    return []

def gnews(item):
    lid, q = item
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(f"({q}) ({SITES}) when:15d") + "&hl=pt-PT&gl=PT&ceid=PT:pt-150"
    t = fetch(url)
    out = []
    if not t:
        return out
    try:
        root = ET.fromstring(t.encode("utf-8"))
    except Exception:
        return out
    for it in root.iter("item"):
        title = strip(it.findtext("title"))
        link = it.findtext("link")
        src = ""
        for c in it:
            if local(c) == "source":
                src = strip(c.text)
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        if title and link:
            out.append({"t": title, "u": link, "i": "", "s": src or "Google News", "d": tdate(it.findtext("pubDate")).isoformat(), "x": "", "force": lid})
    return out

def main():
    items = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(source_items, SOURCES):
            items += r
        for r in ex.map(gnews, GN):
            items += r
    seen, res = set(), []
    for i in sorted(items, key=lambda i: i["d"], reverse=True):
        if tdate(i["d"]) < CUT:
            continue
        key = nz(re.sub(r"\W+", "", i["t"]))[:80]
        if key in seen or i["u"] in seen:
            continue
        seen.add(key); seen.add(i["u"])
        g = tags(i["t"] + " " + i.get("x", ""))
        if i.get("force") and i["force"] not in g:
            g.append(i["force"])
        fut = bool(g) or any(w in nz(i["t"]) for w in FUT)
        if not fut:
            continue
        res.append({"t": i["t"], "u": i["u"], "i": i["i"], "s": i["s"], "d": i["d"], "g": g})
    res = res[:400]
    if not res:
        print("nenhuma notícia obtida; mantém o ficheiro antigo")
        return
    os.makedirs("data", exist_ok=True)
    p = "data/noticias.json"
    old = []
    if os.path.exists(p):
        try:
            old = json.load(open(p, encoding="utf-8")).get("items", [])
        except Exception:
            old = []
    if old != res:
        json.dump({"t": NOW.isoformat(), "items": res}, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("notícias", len(res), "fontes com imagem", sum(1 for r in res if r["i"]))

if __name__ == "__main__":
    main()
