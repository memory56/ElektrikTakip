#!/usr/bin/env python3
"""Smart Life (Tuya) akıllı prizlerinin günlük kWh tüketimini Tuya Cloud'dan okuyup olcumler.json'a yazar.

Ücretsiz Tuya geliştirici hesabında "statistics" servisi yok; bu yüzden cihaz kayıtları (logs, 7 gün saklanır)
okunur: priz 'add_ele' (son rapordan beri eklenen enerji) gönderiyorsa bunlar toplanır, yoksa anlık güç
'cur_power' zamana göre entegre edilir.

Gerekli GitHub secret'ları: TUYA_ACCESS_ID, TUYA_ACCESS_SECRET  (isteğe bağlı TUYA_REGION: eu|us|cn|in, varsayılan eu)
"""
import hashlib, hmac, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "olcumler.json"
TR = timezone(timedelta(hours=3))
HOSTS = {"eu": "https://openapi.tuyaeu.com", "us": "https://openapi.tuyaus.com",
         "cn": "https://openapi.tuyacn.com", "in": "https://openapi.tuyain.com",
         "weu": "https://openapi-weaz.tuyaeu.com"}
EMPTY_SHA = hashlib.sha256(b"").hexdigest()
GUN_GERI = int(os.environ.get("TUYA_GUN", "3"))  # kaç günü yeniden hesapla (log saklama 7 gün)
MAX_ARA = 1800  # cur_power entegrasyonunda en fazla bu kadar saniye boşluk say


class Tuya:
    def __init__(self, cid, secret, host):
        self.cid, self.secret, self.host, self.token = cid, secret, host, ""

    def _req(self, path, query=None, auth=True, method="GET", body=None):
        query = query or {}
        q = "&".join(f"{k}={query[k]}" for k in sorted(query))
        url = path + ("?" + q if q else "")
        t = str(int(time.time() * 1000))
        data = json.dumps(body, separators=(",", ":")).encode() if body is not None else b""
        string_to_sign = method + "\n" + hashlib.sha256(data).hexdigest() + "\n\n" + url
        msg = self.cid + (self.token if auth else "") + t + string_to_sign
        sign = hmac.new(self.secret.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()
        h = {"client_id": self.cid, "sign": sign, "t": t, "sign_method": "HMAC-SHA256"}
        if auth:
            h["access_token"] = self.token
        if body is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(self.host + url, headers=h, data=data if body is not None else None, method=method)
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read().decode())
        if not j.get("success"):
            raise RuntimeError(f"{path}: {j.get('code')} {j.get('msg')}")
        return j["result"]

    def login(self):
        self.token = self._req("/v1.0/token", {"grant_type": "1"}, auth=False)["access_token"]

    def get(self, path, query=None):
        return self._req(path, query)

    def post(self, path, body):
        return self._req(path, None, method="POST", body=body)


def cihazlari_listele(api):
    out, row = [], None
    while True:
        q = {"size": "100"}
        if row:
            q["last_row_key"] = row
        r = api.get("/v1.0/iot-01/associated-users/devices", q)
        out += r.get("devices", [])
        if not r.get("has_more"):
            return out
        row = r.get("last_row_key")


def olcekler(api, did):
    sc = {}
    try:
        for s in api.get(f"/v1.0/devices/{did}/specifications").get("status", []):
            try:
                sc[s["code"]] = int(json.loads(s.get("values") or "{}").get("scale", 0))
            except Exception:
                pass
    except Exception as e:
        print(f"  ölçek okunamadı: {e}")
    return sc


def loglar(api, did, codes, bas_ms, bit_ms):
    out, row = [], None
    for _ in range(200):
        q = {"type": "7", "codes": codes, "start_time": str(bas_ms), "end_time": str(bit_ms), "size": "100"}
        if row:
            q["start_row_key"] = row
        r = api.get(f"/v1.0/devices/{did}/logs", q)
        out += r.get("logs", [])
        if not r.get("has_next"):
            break
        row = r.get("next_row_key") or r.get("current_row_key")
        if not row:
            break
    return out


def gunluk_hesapla(logs, sc, gunler):
    """{'YYYY-MM-DD': kWh} ve kullanılan yöntem."""
    add = [l for l in logs if l.get("code") == "add_ele"]
    res = {g: 0.0 for g in gunler}
    if add:
        k = 10 ** -sc.get("add_ele", 3)
        for l in add:
            g = datetime.fromtimestamp(int(l["event_time"]) / 1000, TR).strftime("%Y-%m-%d")
            if g in res:
                res[g] += float(l["value"]) * k
        return {g: round(v, 3) for g, v in res.items()}, "add_ele"
    pw = sorted((int(l["event_time"]), float(l["value"]) * 10 ** -sc.get("cur_power", 1))
                for l in logs if l.get("code") == "cur_power")
    if not pw:
        return None, None
    for (t0, w0), (t1, _) in zip(pw, pw[1:]):
        dt = min((t1 - t0) / 1000, MAX_ARA)
        g = datetime.fromtimestamp(t0 / 1000, TR).strftime("%Y-%m-%d")
        if g in res:
            res[g] += w0 * dt / 3600 / 1000
    return {g: round(v, 3) for g, v in res.items()}, "cur_power"


def main():
    cid, sec = os.environ.get("TUYA_ACCESS_ID", "").strip(), os.environ.get("TUYA_ACCESS_SECRET", "").strip()
    if not cid or not sec:
        print("TUYA_ACCESS_ID / TUYA_ACCESS_SECRET tanımlı değil; atlanıyor.")
        return 0
    api = Tuya(cid, sec, HOSTS.get(os.environ.get("TUYA_REGION", "eu").strip() or "eu", HOSTS["eu"]))
    api.login()
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"cihazlar": {}}
    simdi = datetime.now(TR)
    bugun = simdi.date()
    gunler = [(bugun - timedelta(days=i)).isoformat() for i in range(GUN_GERI, 0, -1)]  # bugün hariç (tamamlanmamış)
    bas = datetime.fromisoformat(gunler[0]).replace(tzinfo=TR)
    bit = datetime.fromisoformat(bugun.isoformat()).replace(tzinfo=TR)
    devs = cihazlari_listele(api)
    print(f"{len(devs)} cihaz bulundu")
    for d in devs:
        did = d["id"]
        status = {s["code"]: s["value"] for s in d.get("status", [])}
        if "cur_power" not in status and "add_ele" not in status:
            continue  # enerji ölçmeyen cihaz
        sc = olcekler(api, did)
        try:
            lg = loglar(api, did, "add_ele,cur_power", int(bas.timestamp() * 1000), int(bit.timestamp() * 1000) - 1)
            gun, yontem = gunluk_hesapla(lg, sc, gunler)
        except Exception as e:
            print(f"  {d.get('name')}: log okunamadı: {e}")
            gun, yontem = None, None
        rec = data["cihazlar"].setdefault(did, {"gunluk": {}})
        rec.update({"ad": d.get("name"), "kategori": d.get("category"), "online": d.get("online")})
        if "cur_power" in status:
            rec["anlikW"] = round(float(status["cur_power"]) * 10 ** -sc.get("cur_power", 1), 1)
            rec["anlikZaman"] = simdi.strftime("%Y-%m-%d %H:%M")
        if gun:
            rec["gunluk"].update(gun)
            rec["yontem"] = yontem
            rec["gunluk"] = dict(sorted(rec["gunluk"].items())[-400:])
        print(f"  {d.get('name')}: {yontem or 'veri yok'} {gun or ''}")
    data["guncelleme"] = simdi.strftime("%Y-%m-%d %H:%M")
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
