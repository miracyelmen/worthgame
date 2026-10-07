#!/usr/bin/env python3
"""WorthGame fiyat botu (sadece standart kütüphane kullanır).

Kullanım:
  python guncelle.py                  -> Steam (PC) ve iOS fiyatlarını günceller, eksik kategorileri doldurur
  python guncelle.py kesfet 200       -> CheapShark'tan en fazla 200 yeni PC oyunu ekler
  python guncelle.py dogrula          -> steam_id'lerin oyun adıyla uyuşup uyuşmadığını yazdırır
  python guncelle.py ios-ara "Oyun"   -> iOS id'si bulmak için arama yapar
"""
import csv
import io
import json
import sys
import time
import urllib.parse
import urllib.request

DOSYA = "games.csv"
ULKE = "tr"                # fiyat ülkesi (Türkiye)
MAX_TOPLAM = 3000          # keşif, listeyi bu sayıya kadar büyütür
KATEGORI_LIMIT = 250       # bir çalıştırmada en fazla kaç oyunun kategorisi doldurulsun
SUTUNLAR = ["ad", "kategori", "puan", "pc_liste", "pc_guncel", "ps5_liste", "ps5_guncel",
            "xbox_liste", "xbox_guncel", "mobil_liste", "mobil_guncel", "steam_id", "ios_id"]

# SteamSpy etiketi -> WorthGame kategorisi (en çok oy alan etiketten başlayarak ilk eşleşen kazanır)
ETIKETLER = {
    "FPS": "FPS", "Horror": "Korku", "Survival Horror": "Korku", "Racing": "Yarış",
    "Sports": "Spor", "Football": "Spor", "Basketball": "Spor",
    "RPG": "RPG", "Action RPG": "RPG", "JRPG": "RPG", "CRPG": "RPG", "Party-Based RPG": "RPG",
    "Strategy": "Strateji", "RTS": "Strateji", "Turn-Based Strategy": "Strateji", "4X": "Strateji",
    "Grand Strategy": "Strateji", "Simulation": "Simülasyon", "City Builder": "Simülasyon",
    "Farming Sim": "Simülasyon", "Life Sim": "Simülasyon",
    "Action": "Aksiyon-Macera", "Adventure": "Aksiyon-Macera", "Action-Adventure": "Aksiyon-Macera",
    "Open World": "Aksiyon-Macera", "Platformer": "Aksiyon-Macera",
}


def get(url, bekle=1.0):
    """JSON döndürür: (veri, başlıklar). Hata olursa (None, None)."""
    istek = urllib.request.Request(url, headers={"User-Agent": "WorthGame/1.0"})
    for deneme in range(3):
        try:
            with urllib.request.urlopen(istek, timeout=30) as r:
                veri = json.loads(r.read().decode("utf-8"))
                basliklar = r.headers
            time.sleep(bekle)
            return veri, basliklar
        except Exception as e:
            print("  uyarı:", url[:100], e)
            time.sleep(3 * (deneme + 1))
    return None, None


def oku():
    metin = open(DOSYA, encoding="utf-8-sig").read()
    ilk = metin.split("\n")[0]
    ayrac = ";" if ilk.count(";") > ilk.count(",") else ","
    satirlar = []
    for r in csv.DictReader(io.StringIO(metin), delimiter=ayrac):
        satir = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k and isinstance(v, (str, type(None)))}
        if satir.get("ad"):
            satirlar.append(satir)
    return satirlar


def yaz(satirlar):
    ekstra = []
    for r in satirlar:
        for k in r:
            if k not in SUTUNLAR and k not in ekstra:
                ekstra.append(k)
    sutunlar = SUTUNLAR + ekstra
    with open(DOSYA, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\r\n")
        w.writerow(sutunlar)
        for r in satirlar:
            w.writerow([r.get(k, "") for k in sutunlar])


def fiyat(v):
    s = "%.2f" % v
    if s.endswith(".00"):
        s = s[:-3]
    return s.replace(".", ",")


def sayi(s):
    try:
        return float(str(s).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def steam_fiyatlari(idler):
    """{steam_id: (liste, guncel)} ya da {steam_id: None} (Türkiye'de fiyat yok / ücretsiz)."""
    sonuc = {}
    for i in range(0, len(idler), 40):
        grup = idler[i:i + 40]
        url = ("https://store.steampowered.com/api/appdetails?filters=price_overview&cc=%s&appids=%s"
               % (ULKE, ",".join(grup)))
        veri, _ = get(url, 1.5)
        if not isinstance(veri, dict):
            continue  # istek başarısız: bu oyunların eski fiyatı korunur
        for sid in grup:
            if sid not in veri:
                continue
            kayit = veri[sid] if isinstance(veri[sid], dict) else {}
            data = kayit.get("data") if isinstance(kayit.get("data"), dict) else {}
            po = data.get("price_overview")
            sonuc[sid] = (po["initial"] / 100, po["final"] / 100) if po else None
    return sonuc


def ios_guncelle(satirlar):
    for r in satirlar:
        if not r.get("ios_id"):
            continue
        veri, _ = get("https://itunes.apple.com/lookup?id=%s&country=%s" % (r["ios_id"], ULKE), 0.4)
        sonuc = (veri or {}).get("results") or []
        if not sonuc:
            continue
        p = sonuc[0].get("price")
        if p is None:
            continue
        if p <= 0:  # ücretsiz
            r["mobil_liste"] = r["mobil_guncel"] = ""
            continue
        r["mobil_guncel"] = fiyat(p)
        liste = sayi(r.get("mobil_liste", ""))
        if liste is None or liste < p:  # App Store liste fiyatı vermez; elle yazılanı koru
            r["mobil_liste"] = fiyat(p)


GENEL = {"Aksiyon-Macera"}  # "Open World", "Action" gibi geniş etiketler en son denenir


def kategori_bul(tags):
    ilk = [ad for ad, _ in sorted(tags.items(), key=lambda x: -x[1])[:10]]
    for ad in ilk:  # önce belirgin türler (FPS, RPG, Korku...), oy sırasına göre
        if ad in ETIKETLER and ETIKETLER[ad] not in GENEL:
            return ETIKETLER[ad]
    for ad in ilk:
        if ad in ETIKETLER:
            return ETIKETLER[ad]
    return "Diğer"


def kategori_doldur(satirlar):
    n = 0
    for r in satirlar:
        if n >= KATEGORI_LIMIT:
            break
        if r.get("kategori") or not r.get("steam_id"):
            continue
        veri, _ = get("https://steamspy.com/api.php?request=appdetails&appid=" + r["steam_id"], 1.2)
        if not isinstance(veri, dict):
            continue
        tags = veri.get("tags")
        r["kategori"] = kategori_bul(tags) if isinstance(tags, dict) and tags else "Diğer"
        n += 1
    print("kategori doldurulan oyun:", n)


def guncelle():
    satirlar = oku()
    idler = [r["steam_id"] for r in satirlar if r.get("steam_id")]
    fiyatlar = steam_fiyatlari(idler)
    for r in satirlar:
        sid = r.get("steam_id")
        if sid in fiyatlar:
            f = fiyatlar[sid]
            r["pc_liste"], r["pc_guncel"] = (fiyat(f[0]), fiyat(f[1])) if f else ("", "")
    ios_guncelle(satirlar)
    kategori_doldur(satirlar)
    yaz(satirlar)
    print("tamam:", len(satirlar), "oyun,", len(fiyatlar), "Steam fiyatı alındı")


def kesfet(adet):
    satirlar = oku()
    mevcut = {r["steam_id"] for r in satirlar if r.get("steam_id")}
    eklenen, sayfa = 0, 0
    while eklenen < adet and len(satirlar) < MAX_TOPLAM and sayfa < 100:
        url = ("https://www.cheapshark.com/api/1.0/deals?storeID=1&pageSize=60&sortBy=Metacritic"
               "&desc=1&metacritic=70&pageNumber=%d" % sayfa)
        veri, _ = get(url, 1.5)
        if not veri:
            break
        for d in veri:
            sid = str(d.get("steamAppID") or "")
            if not sid or sid in mevcut:
                continue
            if int(d.get("steamRatingCount") or 0) < 500:
                continue
            puan = int(d.get("metacriticScore") or 0) or int(d.get("steamRatingPercent") or 0)
            satirlar.append({"ad": d.get("title", sid), "kategori": "", "puan": str(puan), "steam_id": sid})
            mevcut.add(sid)
            eklenen += 1
            if eklenen >= adet or len(satirlar) >= MAX_TOPLAM:
                break
        if len(veri) < 60:
            break
        sayfa += 1
    yaz(satirlar)
    print("eklenen yeni oyun:", eklenen, "| toplam:", len(satirlar))


def dogrula():
    for r in oku():
        sid = r.get("steam_id")
        if not sid:
            continue
        veri, _ = get("https://store.steampowered.com/api/appdetails?filters=basic&appids=" + sid, 1.5)
        kayit = (veri or {}).get(sid) or {}
        data = kayit.get("data") if isinstance(kayit.get("data"), dict) else {}
        steam_ad = data.get("name", "?")
        a, b = r["ad"].lower(), steam_ad.lower()
        print("OK " if (a in b or b in a) else "?? ", sid, "|", r["ad"], "|", steam_ad)


def ios_ara(ad):
    url = ("https://itunes.apple.com/search?entity=software&limit=5&country=%s&term=%s"
           % (ULKE, urllib.parse.quote(ad)))
    veri, _ = get(url, 0.2)
    for s in (veri or {}).get("results", []):
        print(s.get("trackId"), "|", s.get("trackName"), "|", s.get("price"), s.get("currency"))


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        guncelle()
    elif a[0] == "kesfet":
        kesfet(int(a[1]) if len(a) > 1 else 100)
    elif a[0] == "dogrula":
        dogrula()
    elif a[0] == "ios-ara":
        ios_ara(" ".join(a[1:]))
    else:
        print(__doc__)
