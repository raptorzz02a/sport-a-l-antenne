#!/usr/bin/env python3
"""Construit data/events.json et data/sports.ics a partir :
- du guide XMLTV de xmltvfr.fr (chaines TV francaises, 5 jours a venir),
- de l'API officielle EuroLeague (tous les matchs EuroLeague et EuroCup = EuroLeague TV).

Bibliotheque standard uniquement. Usage :
    python3 scripts/build_data.py                 # telecharge les sources
    python3 scripts/build_data.py --xmltv f.xml   # utilise un fichier local (tests)
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import lzma
import os
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data")
UA = {"User-Agent": "programme-tv-sport/1.0 (+github actions)"}

# Guides XMLTV essayes dans l'ordre ; le premier qui repond est utilise.
XMLTV_URLS = [
    "https://xmltvfr.fr/xmltv/xmltv.xml.gz",
    "https://xmltvfr.fr/xmltv/xmltv.xz",
    "https://xmltvfr.fr/xmltv/xmltv_fr.xml.gz",
    "https://xmltvfr.fr/xmltv/xmltv_fr.xz",
]
# Complement (chaines gratuites) si xmltvfr est indisponible.
FALLBACK_XMLTV = "https://raw.githubusercontent.com/Catch-up-TV-and-More/xmltv/master/tv_guide_fr.xml"

# Diffuseurs suivis : regex sur l'identifiant XMLTV ou sur le nom affiche.
BROADCASTERS = [
    ("DAZN", r"^dazn"),
    ("L'Équipe", r"^(l.?equipe ?(21|live)?|la chaine l.?equipe)"),
    ("beIN Sports", r"^bein ?sports"),
    ("Canal+", r"^(canal ?(\+|plus)( ?(sport|foot|live|premier league|ligue 1|hd)|$)|infosport ?(\+|plus))"),
    ("Eurosport", r"^eurosport ?(1|2|360)"),
    ("France TV", r"^france ?[234]( |$|hd|uhd)"),
    ("TF1", r"^tf1( ?hd)?$"),
    ("M6", r"^m6( ?hd)?$"),
    ("RMC Sport", r"^rmc ?sport"),
]
EXCLUDE_CHANNEL = r"(international|\.af$|\.ch$|\.be$|\.ar$|frdrom|barsat|^france ?3 ?-|^france ?3 (corse|normandie|nouvelle)|alt$)"

# Sports suivis : (cle, libelle, motifs). Les motifs s'appliquent sur un texte normalise
# (minuscules, sans accents).
SPORTS = [
    ("basket", "Basket-ball", [r"basket", r"\bnba\b", r"\bwnba\b", r"euroligue", r"euroleague", r"eurocup",
                                r"betclic elite", r"\bpro a\b", r"\bpro b\b", r"leaders cup", r"\blfb\b", r"\bfiba\b"]),
    ("hand", "Handball", [r"handball", r"\bhand\b", r"starligue", r"liqui moly", r"\behf\b", r"ligue butagaz"]),
    ("hockey", "Hockey sur glace", [r"hockey", r"\bnhl\b", r"ligue magnus", r"\biihf\b"]),
    ("darts", "Fléchettes", [r"flechette", r"\bdarts?\b", r"\bpdc\b"]),
    ("petanque", "Pétanque", [r"petanque", r"\bboules?\b lyonnaise", r"masters de petanque"]),
    ("mma", "MMA", [r"\bmma\b", r"\bufc\b", r"\bpfl\b", r"bellator", r"ares fighting", r"\bares\b \d", r"arts martiaux mixtes"]),
    ("motogp", "MotoGP", [r"moto ?gp", r"\bmoto ?[23]\b", r"grand prix .{0,40}moto", r"vitesse moto", r"motocyclisme"]),
    ("f1", "Formule 1", [r"formule ?1", r"\bf1\b", r"formula ?1", r"grand prix .{0,40}formule"]),
    ("rugby", "Rugby", [r"rugby"]),
    ("foot", "Football", [r"football", r"\bfoot\b", r"ligue 1", r"ligue 2", r"premier league", r"\bliga\b", r"serie a",
                          r"bundesliga", r"champions league", r"ligue des champions", r"europa league",
                          r"conference league", r"coupe de france", r"\bmls\b", r"\bcan 20", r"coupe du monde fifa",
                          r"\buefa\b", r"\bfifa\b", r"\bd1 arkema\b", r"national 1"]),
]
NOT_SPORT = [r"football americain", r"foot us", r"\bnfl\b", r"futsal", r"beach soccer", r"hockey sur gazon",
             r"field hockey", r"rink hockey", r"foot 2 rue", r"\bs\d+ \(n.\d+", r"f1h2o", r"motonautisme"]
# Programme dont le titre commence par un autre sport ("Cyclo-cross : Coupe de France") : ignore.
OTHER_SPORT_PREFIX = (r"^(cyclo.?cross|cyclisme|vtt|tennis|tennis de table|golf|equitation|hippisme|athletisme|natation|ski|"
                      r"biathlon|voile|volley|beach.?volley|badminton|padel|judo|escrime|patinage|catch|baseball|cricket|"
                      r"triathlon|trail|rallye|endurance|wec|indycar|nascar|superbike|motocross|enduro|boxe|kick.?boxing|"
                      r"snooker|billard|squash|lutte|gymnastique|aviron|canoe|surf|sports? mecaniques?|automobile|"
                      r"e-?sport|poker|rugby a xiii|football americain|halterophilie|sports? de combat|bowling)\b\s*:")
# Indices qu'un programme est une competition (match, course, combat), et non une emission autour du sport.
EVENT = (r"( / | - | vs\.? | contre |grand prix|\bgp\b|essais|qualif|course|sprint|warm.?up|finale|journee|\bmatch\b|"
         r"combat|\bufc \d|fight night|\bpfl\b|\bares\b|hexagone mma|\bksw\b|masters|championnat|coupe|trophee|"
         r"tournoi|\bopen\b|playoffs?|\bround\b|\bnight\b|series|derby|\bcup\b|ligue|league|liga|serie a|bundesliga|"
         r"\bnba\b|\bnhl\b|euroligue|eurocup|betclic|starligue|top 14)")
SPORT_TITLE = (r"^(football|basket-?ball|handball|hockey sur glace|hockey|flechettes|darts|petanque|mma|formule 1|f1|"
               r"moto ?gp|moto ?[23]|rugby)\b")
MAGAZINE = (r"(magazine|talk|debat|journal|jt-sport|plateau|avant-match|apres-match|avant match|apres match|debrief|"
            r"club$|le mag|ceremonie|ballon d.or|classiques|resume|best of|highlights|meilleurs moments|conference de presse|"
            r"pesee|extra\b|en route pour|stream team|l.equipe de|stade 2|telefoot|format mma|sur canal|les matchs de|"
            r"the match|inside|reportage|portrait|documentaire|histoire|retro|legende|replay|interview|emission|"
            r"l.integrale|tirage au sort|mercato|infos?\b|le debrief|after\b|late show|programme)")
GENERIC_SPORT_CAT = r"(sport|multisport)"
MAG_CAT = r"(magazine|\bmag\b|talk|\bdoc\b|documentaire|debat|divertissement|jt-sport|journal)"
# Rugby : seulement Top 14, coupes d'Europe (Champions Cup, Challenge Cup) et equipe de France.
RUGBY_COMP = r"(top ?14|champions cup|challenge cup|coupe d.europe|investec|\bepcr\b)"
RUGBY_EXCLUDE = r"(pro ?d2|nationale|federale|a 7\b|sevens|xiii|rugby league|super rugby|premiership|urc\b|bledisloe|rugby championship)"
NON_LIVE_CAT = r"(dessin|anime|serie|feuilleton|film|telefilm|documentaire|jeunesse|jeu\b|fiction)"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s.replace("’", "'"))


def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if url.endswith(".gz") or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    elif url.endswith(".xz") or data[:6] == b"\xfd7zXZ\x00":
        data = lzma.decompress(data)
    return data


def parse_xmltv_time(s):
    s = s.strip()
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", s)
    t = dt.datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2) or "+0000"
    sign = 1 if off[0] == "+" else -1
    tz = dt.timezone(sign * dt.timedelta(hours=int(off[1:3]), minutes=int(off[3:5])))
    return t.replace(tzinfo=tz).astimezone(dt.timezone.utc)


def broadcaster_for(cid, name):
    for key in (norm(cid).replace(".fr", "").replace("plus", " plus"), norm(name)):
        if re.search(EXCLUDE_CHANNEL, norm(cid)) or re.search(EXCLUDE_CHANNEL, norm(name)):
            return None
        for label, pat in BROADCASTERS:
            if re.search(pat, key):
                return label
    return None


def classify(title, sub, desc, cats):
    """Retourne la cle du sport, ou None. Priorite : categories, puis titre, puis description
    (la description seulement si le programme est categorise sport)."""
    cat_txt = norm(" ".join(cats))
    head = norm(f"{title} {sub}")
    body = norm(desc)[:400]
    full = f"{cat_txt} {head} {body}"
    if re.search(OTHER_SPORT_PREFIX, norm(title)):
        return None
    if re.search(NON_LIVE_CAT, cat_txt) or any(re.search(p, f"{cat_txt} {head}") for p in NOT_SPORT):
        return None
    sources = [cat_txt, head]
    if re.search(GENERIC_SPORT_CAT, cat_txt):
        sources.append(body)
    for src in sources:
        for key, _, pats in SPORTS:
            if any(re.search(p, src) for p in pats):
                if key == "rugby":
                    if re.search(RUGBY_EXCLUDE, f"{head} {body}"):
                        return None
                    if re.search(RUGBY_COMP, f"{head} {body}") or re.search(r"(\bfrance\b|xv de france|les bleus)", head):
                        return "rugby"
                    return None
                if key == "foot" and any(re.search(p, full) for p in NOT_SPORT):
                    return None
                return key
    return None


def kind_of(title, sub, desc, cats, has_live):
    t = norm(f"{title} {sub}")
    c = norm(" ".join(cats))
    if re.search(MAG_CAT, c) or re.search(MAGAZINE, t):
        return "magazine"
    if has_live or re.search(r"\b(en direct|direct)\b", t) or re.search(r"\ben direct\b", norm(desc)[:300]):
        return "direct"
    if re.search(EVENT, t) or re.search(SPORT_TITLE, t):
        return "diffusion"
    return "magazine"


def from_xmltv(xml_bytes, source_label):
    root = ET.fromstring(xml_bytes)
    chans = {}
    for c in root.findall("channel"):
        name = c.findtext("display-name") or c.get("id")
        b = broadcaster_for(c.get("id"), name)
        if b:
            chans[c.get("id")] = (b, name.strip())
    events = []
    for p in root.findall("programme"):
        cid = p.get("channel")
        if cid not in chans:
            continue
        title = (p.findtext("title") or "").strip()
        sub = (p.findtext("sub-title") or "").strip()
        desc = (p.findtext("desc") or "").strip()
        cats = [c.text or "" for c in p.findall("category")]
        sport = classify(title, sub, desc, cats)
        if not sport:
            continue
        start = parse_xmltv_time(p.get("start"))
        stop = parse_xmltv_time(p.get("stop")) if p.get("stop") else start + dt.timedelta(hours=2)
        b, cname = chans[cid]
        events.append({
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": stop.isoformat().replace("+00:00", "Z"),
            "sport": sport,
            "broadcaster": b,
            "channel": cname,
            "title": title,
            "subtitle": sub,
            "desc": desc[:280],
            "kind": kind_of(title, sub, desc, cats, p.find("live") is not None),
            "cats": [c for c in cats if c][:3],
            "source": source_label,
        })
    print(f"[{source_label}] {len(chans)} chaines suivies, {len(events)} programmes retenus", file=sys.stderr)
    return events


def euroleague(now):
    """Saison courante : commence en juillet."""
    year = now.year if now.month >= 7 else now.year - 1
    events = []
    for comp, label in (("E", "EuroLeague"), ("U", "EuroCup")):
        url = f"https://api-live.euroleague.net/v2/competitions/{comp}/seasons/{comp}{year}/games"
        try:
            data = json.loads(fetch(url, timeout=60))
        except Exception as e:  # noqa: BLE001
            print(f"[euroleague] {label} indisponible : {e}", file=sys.stderr)
            continue
        for g in data.get("data", []):
            try:
                start = dt.datetime.fromisoformat(g["utcDate"].replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                continue
            if g.get("played") or start < now - dt.timedelta(hours=3) or start > now + dt.timedelta(days=21):
                continue
            home = g["local"]["club"].get("name", "?")
            away = g["road"]["club"].get("name", "?")
            rnd = g.get("roundName") or ""
            phase = (g.get("phaseType") or {}).get("name") or ""
            events.append({
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": (start + dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
                "sport": "basket",
                "broadcaster": "EuroLeague TV",
                "channel": "EuroLeague TV",
                "title": f"{home} / {away}",
                "subtitle": f"{label} · {phase} · {rnd}".strip(" ·"),
                "desc": "" if g.get("confirmedHour", True) else "Horaire à confirmer",
                "kind": "direct",
                "source": "euroleague",
            })
    print(f"[euroleague] {len(events)} matchs", file=sys.stderr)
    return events


def ics_escape(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def write_ics(events, path, sport_labels):
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//programme-tv-sport//FR", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Sport à la TV", "X-WR-TIMEZONE:Europe/Paris", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
             "X-PUBLISHED-TTL:PT6H"]
    for e in events:
        if e["kind"] == "magazine":
            continue
        uid = hashlib.sha1(f'{e["start"]}{e["channel"]}{e["title"]}'.encode()).hexdigest()
        f = lambda s: s.replace("-", "").replace(":", "")[:15] + "Z"  # noqa: E731
        lines += ["BEGIN:VEVENT", f"UID:{uid}@programme-tv-sport", f"DTSTAMP:{stamp}",
                  f"DTSTART:{f(e['start'])}", f"DTEND:{f(e['end'])}",
                  "SUMMARY:" + ics_escape(f"{sport_labels[e['sport']]} · {e['title']} ({e['channel']})"),
                  "DESCRIPTION:" + ics_escape(" — ".join(x for x in (e["subtitle"], e["desc"]) if x)),
                  "LOCATION:" + ics_escape(e["channel"]),
                  "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-PT15M", "DESCRIPTION:Bientôt à la TV", "END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\r\n".join(fold(l) for l in lines) + "\r\n")


def fold(line):
    """Coupe les lignes ICS a 75 octets (RFC 5545)."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not out else 74):
            out.append(cur)
            cur = ""
        cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def dedupe(events):
    seen, out = set(), []
    for e in sorted(events, key=lambda e: (e["start"], e["broadcaster"], e["channel"])):
        k = (e["start"][:16], norm(e["channel"]), norm(e["title"]))
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xmltv", help="fichier XMLTV local (sinon telechargement)")
    ap.add_argument("--no-euroleague", action="store_true")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()
    now = dt.datetime.now(dt.timezone.utc)
    events, sources = [], []

    if args.xmltv:
        with open(args.xmltv, "rb") as fh:
            data = fh.read()
        events += from_xmltv(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data, "xmltv-local")
        sources.append(args.xmltv)
    else:
        got = False
        for url in XMLTV_URLS:
            try:
                events += from_xmltv(fetch(url, timeout=300), "xmltvfr")
                sources.append(url)
                got = True
                break
            except Exception as e:  # noqa: BLE001
                print(f"[xmltvfr] {url} : {e}", file=sys.stderr)
        try:
            events += from_xmltv(fetch(FALLBACK_XMLTV), "telerama")
            sources.append(FALLBACK_XMLTV)
        except Exception as e:  # noqa: BLE001
            print(f"[fallback] {e}", file=sys.stderr)
        if not got:
            print("ATTENTION : guide xmltvfr indisponible, seules les chaines gratuites sont couvertes", file=sys.stderr)

    if not args.no_euroleague:
        events += euroleague(now)

    cutoff = now - dt.timedelta(hours=6)
    events = [e for e in dedupe(events) if dt.datetime.fromisoformat(e["end"].replace("Z", "+00:00")) >= cutoff]
    labels = {k: lbl for k, lbl, _ in SPORTS}
    os.makedirs(args.out, exist_ok=True)
    payload = {
        "generated": now.isoformat().replace("+00:00", "Z"),
        "sources": sources,
        "sports": labels,
        "broadcasters": [b for b, _ in BROADCASTERS] + ["EuroLeague TV"],
        "events": events,
    }
    with open(os.path.join(args.out, "events.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    write_ics(events, os.path.join(args.out, "sports.ics"), labels)
    print(f"OK : {len(events)} evenements ecrits dans {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
