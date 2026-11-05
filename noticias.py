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

def fetch(url, limit=None):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "pt-PT,pt;q=0.9"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read(limit) if limit else r.read()
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

SPORTS_SRC = {"A Bola", "Record", "O Jogo", "Maisfutebol", "zerozero", "Bola na Rede", "SAPO Desporto"}
# palavras só de futebol (anulam a exclusão de outras modalidades)
HARD = re.compile(r"(?<![a-z0-9])(futebol|futebolist\w*|golos?|guarda-redes|avancado\w*|penalti\w*|fora de jogo|livre direto|canto|dérbi|derbi|liga dos campeoes|champions|premier league|la liga|serie a|bundesliga|ligue 1|primeira liga|liga portugal|taca de portugal)(?![a-z0-9])")
# palavras gerais de desporto (aceites só em jornais desportivos)
STRONG = re.compile(r"(?<![a-z0-9])(treinador\w*|medio\w*|defesa\w*|arbitr\w*|var|fifa|uefa|jornada|transferenc\w*|estadio\w*|empat\w*|derrota\w*|vitoria\w*|liga|taca|campeonato|selecao|clube\w*|equipa\w*|jogador\w*|mercado|onze|convocad\w*)(?![a-z0-9])")
OTHER = re.compile(r"(?<![a-z0-9])(basquetebol|basquete|nba|andebol|voleibol|hoquei|tenis|formula 1|f1|motogp|ciclismo|volta a portugal|rali|rugby|ragui|natacao|atletismo|surf|judo|golfe|padel|futsal|esports?|poker|boxe|mma|ufc)(?![a-z0-9])")
SPORT_URL = re.compile(r"/(desporto|futebol|sport|sports|futebol-nacional|futebol-internacional)(/|-|\.|$)")
SECTION = re.compile(r"^(noticias?|news)\s*(de\s*)?(spain|portugal|espanha|mundo|internacional)?$")

def relevant(i, g):
    title = nz(i["t"]); text = title + " " + nz(i.get("x", ""))
    if SECTION.match(re.sub(r"[^a-z ]", "", title).strip()) or (len(title.split()) <= 3 and title.startswith("noticias")):
        return False
    hard = bool(HARD.search(text)); strong = bool(STRONG.search(text)); other = bool(OTHER.search(text))
    if other and not hard:
        return False
    if i["s"] in SPORTS_SRC or i.get("force"):
        return bool(g) or hard or strong
    return (bool(g) or hard) and (bool(SPORT_URL.search(urllib.parse.urlparse(i["u"]).path.lower())) or bool(i.get("force")))

def og_image(url):
    t = fetch(url, 200000)
    if not t:
        return ""
    for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]*content=["\']([^"\']+)', r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)'):
        m = re.search(pat, t, re.I)
        if m:
            u = html.unescape(m.group(1))
            return urllib.parse.urljoin(url, u) if not u.startswith("http") else u
    return ""

def main():
    p = "data/noticias.json"
    old = []
    if os.path.exists(p):
        try:
            old = json.load(open(p, encoding="utf-8")).get("items", [])
        except Exception:
            old = []
    oldimg = {o["u"]: o["i"] for o in old if o.get("i")}
    items = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(source_items, SOURCES):
            items += r
        for r in ex.map(gnews, GN):
            items += r
    best = {}
    for i in sorted(items, key=lambda i: i["d"], reverse=True):
        if tdate(i["d"]) < CUT:
            continue
        g = tags(i["t"] + " " + i.get("x", ""))
        if i.get("force") and i["force"] not in g:
            g.append(i["force"])
        if not relevant(i, g):
            continue
        i["g"] = g
        key = nz(re.sub(r"\W+", "", i["t"]))[:80]
        cur = best.get(key)
        google = "news.google.com" in i["u"]
        if cur is None:
            best[key] = i
        else:
            curg = "news.google.com" in cur["u"]
            if (curg and not google) or (not cur["i"] and i["i"]):
                i["g"] = sorted(set(i["g"]) | set(cur["g"]))
                best[key] = i
            else:
                cur["g"] = sorted(set(cur["g"]) | set(g))
    res = sorted(best.values(), key=lambda i: i["d"], reverse=True)[:400]
    # imagens em falta: reutiliza as anteriores ou lê a imagem da própria página (máx. 150 por execução)
    todo = []
    for i in res:
        if not i["i"] and i["u"] in oldimg:
            i["i"] = oldimg[i["u"]]
        if not i["i"] and "news.google.com" not in i["u"]:
            todo.append(i)
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, img in zip(todo[:150], ex.map(og_image, [t["u"] for t in todo[:150]])):
            i["i"] = img
    res = [{"t": i["t"], "u": i["u"], "i": i["i"], "s": i["s"], "d": i["d"], "g": i["g"]} for i in res]
    if not res:
        print("nenhuma notícia obtida; mantém o ficheiro antigo")
        return
    os.makedirs("data", exist_ok=True)
    if old != res:
        json.dump({"t": NOW.isoformat(), "items": res}, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("notícias", len(res), "com imagem", sum(1 for r in res if r["i"]))

if __name__ == "__main__":
    main()
