#!/usr/bin/env python3
"""EPİAŞ günlük bülteninden (PDF) aylık PTF ortalamalarını okuyup prices.json'u günceller.

Bülten adresi: https://www.epias.com.tr/wp-content/uploads/YYYY/MM/epias-bulten-DD.MM.YYYY.pdf
Bültendeki "Aylık PTF Ortalamaları" tablosu satır satır şu biçimdedir:
    2023 2024 2025 2026
    01 - Ocak 3.431,49 1.942,90 2.508,80 2.894,92
"""
import json, re, subprocess, sys, tempfile, urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "prices.json"
UA = {"User-Agent": "Mozilla/5.0 (ElektrikTakip fiyat guncelleme)"}


def tr_num(s):
    return float(s.replace(".", "").replace(",", "."))


def parse_bulletin(text):
    """Bülten metninden {'YYYY-MM': ptf} ve günlük PTF ortalamasını çıkarır."""
    lines = text.splitlines()
    out = {}
    years = None
    in_table = False
    for ln in lines:
        if re.search(r"Aylık\s+PTF\s+Ortalama", ln, re.I):
            in_table, years = True, None
            continue
        if not in_table:
            continue
        if re.match(r"\s*Ortalama\s+\d", ln) and years:
            break  # tablo bitti
        m = re.search(r"((?:20\d\d\s+){1,9}20\d\d)(?!\d)", ln)
        if m:
            cand = [int(y) for y in m.group(1).split()]
            if cand == sorted(cand) and len(set(cand)) == len(cand):
                years = cand
            continue
        mr = re.search(r"(0[1-9]|1[0-2])\s*-\s*(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+((?:\d{1,3}(?:\.\d{3})*,\d{2}\s*)+)", ln)
        if mr and years:
            vals = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}", mr.group(2))
            if not vals or len(vals) > len(years):
                continue
            ay = int(mr.group(1))
            for y, v in zip(years, vals):
                out[f"{y}-{ay:02d}"] = tr_num(v)
    daily = None
    md = re.search(r"PTF\s+Arit\.?\s+Ortalaması\s*\(\s*TL/MWh\s*\)\s+(\d{1,3}(?:\.\d{3})*,\d{2})", text)
    if md:
        daily = tr_num(md.group(1))
    return out, daily


def fetch_pdf(d):
    name = f"epias-bulten-{d:%d.%m.%Y}.pdf"
    folders = [d, (d.replace(day=1) + timedelta(days=32)).replace(day=1)]
    for f in folders:
        url = f"https://www.epias.com.tr/wp-content/uploads/{f:%Y/%m}/{name}"
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if data[:4] == b"%PDF":
                return url, data
        except Exception:
            continue
    return None, None


def pdf_texts(data):
    """Aynı PDF'in farklı pdftotext modlarıyla çıkarılmış metinleri (tablo düzeni moda göre değişebiliyor)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as t:
        t.write(data); t.flush()
        for mode in (["-layout"], ["-raw"], []):
            yield subprocess.run(["pdftotext", *mode, t.name, "-"], capture_output=True, text=True).stdout


def main():
    today = date.today()
    for back in range(0, 15):
        d = today - timedelta(days=back)
        url, data = fetch_pdf(d)
        if not data:
            continue
        monthly, daily = {}, None
        for txt in pdf_texts(data):
            m, dl = parse_bulletin(txt)
            if len(m) > len(monthly):
                monthly, daily = m, dl or daily
        if len(monthly) < 12:
            print(f"{url}: tablo okunamadı ({len(monthly)} değer), önceki güne bakılıyor")
            continue
        prices = json.loads(PRICES.read_text(encoding="utf-8"))
        before = json.dumps(prices.get("ptf", {}), sort_keys=True)
        prices.setdefault("ptf", {}).update(monthly)
        prices["ptf"] = dict(sorted(prices["ptf"].items()))
        prices["ptfGunluk"] = {"tarih": d.isoformat(), "deger": daily} if daily else prices.get("ptfGunluk")
        prices["guncelleme"] = d.isoformat()
        prices["kaynakUrl"] = url
        PRICES.write_text(json.dumps(prices, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Güncellendi: {url} · {len(monthly)} aylık değer · değişti: {before != json.dumps(prices['ptf'], sort_keys=True)}")
        return 0
    print("Son 15 günde okunabilir bülten bulunamadı (EPİAŞ sitesine ulaşılamadı)", file=sys.stderr)
    # Fiyatlar zaten güncelse (son 4 gün) hata sayma: EPİAŞ ara sıra birkaç saat yanıt vermiyor
    try:
        son = date.fromisoformat(json.loads(PRICES.read_text(encoding="utf-8")).get("guncelleme", "2000-01-01"))
        if (today - son).days <= 4:
            print(f"Mevcut fiyatlar {son} tarihli, yeterince güncel; yarın tekrar denenecek.")
            return 0
    except Exception:
        pass
    return 1


if __name__ == "__main__":
    sys.exit(main())
