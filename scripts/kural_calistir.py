#!/usr/bin/env python3
"""kurallar.json'daki akıllı priz kurallarını uygular (ör. termosifon günde 1,5 kWh'yi geçince kapat).

- Bugünkü (TSİ gece yarısından beri) tüketim Tuya cihaz kayıtlarındaki 'add_ele' değerlerinden toplanır.
- Sınır aşılmışsa ve priz açıksa 'switch_1' kapatılır.
- Kural günde bir kez uygulanır: kapattıktan sonra priz elle açılırsa o gün tekrar kapatılmaz (banyo öncesi açma).
- Durum kural_durum.json'a yazılır (uygulama bunu gösterir).
"""
import json, os, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tuya_olcum import Tuya, HOSTS, TR, olcekler, loglar  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KURAL = ROOT / "kurallar.json"
DURUM = ROOT / "kural_durum.json"


def bugun_kwh(api, did, sc):
    simdi = datetime.now(TR)
    bas = simdi.replace(hour=0, minute=0, second=0, microsecond=0)
    lg = loglar(api, did, "add_ele", int(bas.timestamp() * 1000), int(simdi.timestamp() * 1000))
    k = 10 ** -sc.get("add_ele", 3)
    return round(sum(float(l["value"]) for l in lg if l.get("code") == "add_ele") * k, 3)


def main():
    cid, sec = os.environ.get("TUYA_ACCESS_ID", "").strip(), os.environ.get("TUYA_ACCESS_SECRET", "").strip()
    if not cid or not sec:
        print("Tuya anahtarları yok; atlanıyor."); return 0
    kurallar = [k for k in json.loads(KURAL.read_text(encoding="utf-8")).get("kurallar", []) if k.get("aktif", True)]
    if not kurallar:
        return 0
    api = Tuya(cid, sec, HOSTS.get(os.environ.get("TUYA_REGION", "eu").strip() or "eu", HOSTS["eu"]))
    api.login()
    durum = json.loads(DURUM.read_text(encoding="utf-8")) if DURUM.exists() else {}
    once = json.dumps(durum, sort_keys=True)
    simdi = datetime.now(TR)
    gun = simdi.strftime("%Y-%m-%d")
    for k in kurallar:
        did = k["cihazId"]
        d = durum.setdefault(did, {})
        if d.get("gun") != gun:  # yeni gün: sayaç sıfırlanır
            d.clear(); d["gun"] = gun
        try:
            sc = olcekler(api, did)
            kwh = bugun_kwh(api, did, sc)
            st = {s["code"]: s["value"] for s in api.get(f"/v1.0/devices/{did}/status")}
            acik = bool(st.get("switch_1"))
        except Exception as e:
            print(f"{k['ad']}: okunamadı: {e}"); d["hata"] = str(e)[:200]; continue
        # depoya gereksiz kayıt düşmemek için yalnızca anlamlı değişimde güncelle (≥0,05 kWh, aç/kapa, kapatma)
        if abs(d.get("bugunKwh", -1) - kwh) >= 0.05 or d.get("acik") != acik or "ad" not in d:
            d.update({"ad": k.get("cihazAdi"), "limit": k["gunlukLimitKwh"], "bugunKwh": kwh, "acik": acik,
                      "kontrol": simdi.strftime("%Y-%m-%d %H:%M")})
        d.pop("hata", None)
        print(f"{k['ad']}: bugün {kwh} kWh / sınır {k['gunlukLimitKwh']} · priz {'açık' if acik else 'kapalı'}")
        if kwh >= k["gunlukLimitKwh"] and acik and not d.get("kapatildi"):
            try:
                api.post(f"/v1.0/devices/{did}/commands", {"commands": [{"code": "switch_1", "value": False}]})
                d["kapatildi"] = simdi.strftime("%H:%M"); d["acik"] = False
                print(f"  → sınır aşıldı, priz kapatıldı ({d['kapatildi']})")
            except Exception as e:
                print(f"  → kapatma başarısız: {e}"); d["hata"] = str(e)[:200]
    if json.dumps(durum, sort_keys=True) == once:
        print("Durumda anlamlı değişiklik yok."); return 0
    durum["guncelleme"] = simdi.strftime("%Y-%m-%d %H:%M")
    DURUM.write_text(json.dumps(durum, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
