#!/usr/bin/env python3
"""Aydem e-Arşiv fatura XML'ini okur, uygulamanın kayıt biçimine çevirir ve guncellemeler.json'a
tek seferlik bir 'fatura' işlemi ekler (uygulama açılışta veritabanına yazar).
Kişisel bilgiler (ad, adres, sözleşme no) alınmaz; yalnızca dönem, endeks, kWh ve tutarlar.
Kullanım: python3 scripts/fatura_ekle.py FATURA.xml"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KDV = 0.10

def tr_sayi(s):
    s = (s or "").strip()
    if not s: return None
    return float(s.replace(".", "").replace(",", "."))

def oku(xml):
    t = re.sub(r"<cbc:EmbeddedDocumentBinaryObject[^>]*>.*?</cbc:EmbeddedDocumentBinaryObject>", "", xml, flags=re.S)
    def g(k):
        m = re.search(r"#" + k + r": ?([^|<]*)", t)
        return m.group(1).strip() if m else ""
    if "InvoiceLine" not in t or not g("DONEM"):
        raise SystemExit("Aydem e-Arşiv fatura XML'i değil")
    tarih = lambda s: "-".join(reversed(s.split(".")))
    kwh = tr_sayi(g("TUKTT")); dag = tr_sayi(g("DAGT")); btv = tr_sayi(g("BTV")) or 0; fat = tr_sayi(g("FATTUT"))
    ebf = tr_sayi(g("BFT1")) or tr_sayi(g("BFT1K1")); ebf2 = tr_sayi(g("BFT1K2"))
    kademeli = ebf2 is not None and ebf is not None and abs(ebf2 - ebf) > 1e-6
    enerji = fat / (1 + KDV) - dag - btv
    s3 = lambda ks: round(sum(tr_sayi(g(k)) or 0 for k in ks), 3)
    return {
        "donem": g("DONEM").replace("/", "-"), "ilkTarih": tarih(g("IOTAR")), "sonTarih": tarih(g("SOTAR")),
        "ilkEndeks": s3(["IET1", "IET2", "IET3"]), "sonEndeks": s3(["SET1", "SET2", "SET3"]),
        "kwh": kwh, "enerjiBF": None if kademeli else round(enerji / kwh, 6), "dagitimBF": tr_sayi(g("DAGBF")),
        "dagitimTL": dag, "etv": btv, "kdv": tr_sayi(g("KDV2")), "faturaTutar": fat, "odenecek": tr_sayi(g("ODETUT")),
        "kaynak": "xml-otomatik",
    }

def main():
    rec = oku(Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace"))
    p = ROOT / "guncellemeler.json"
    g = json.loads(p.read_text(encoding="utf-8"))
    oid = "fatura-" + rec["donem"]
    if any(o.get("id") == oid for o in g["islemler"]):
        print("ZATEN VAR", oid); return
    g["islemler"].append({"id": oid, "tip": "fatura", "kayit": rec,
                          "mesaj": f"{rec['donem']} faturası eklendi: {rec['kwh']:.1f} kWh, {rec['odenecek']:.0f} TL"})
    p.write_text(json.dumps(g, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("EKLENDI", json.dumps(rec, ensure_ascii=False))

if __name__ == "__main__":
    main()
