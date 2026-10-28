#!/usr/bin/env python3
"""Bir prizin son N saatlik aç/kapa ve güç kayıtlarını Tuya'dan okuyup priz_gecmis.json'a yazar (teşhis için)."""
import json, os, sys
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tuya_olcum import Tuya, HOSTS, TR, loglar, olcekler

ROOT = Path(__file__).resolve().parent.parent
did = os.environ.get("PRIZ_ID", "608610038caab5d7cb7e")
saat = int(os.environ.get("SAAT", "36"))
api = Tuya(os.environ["TUYA_ACCESS_ID"].strip(), os.environ["TUYA_ACCESS_SECRET"].strip(),
           HOSTS.get((os.environ.get("TUYA_REGION") or "eu").strip() or "eu", HOSTS["eu"]))
api.login()
sc = olcekler(api, did)
simdi = datetime.now(TR)
lg = loglar(api, did, "switch_1,cur_power,add_ele", int((simdi - timedelta(hours=saat)).timestamp() * 1000), int(simdi.timestamp() * 1000))
out = []
for l in sorted(lg, key=lambda x: int(x["event_time"])):
    v = l.get("value")
    if l["code"] == "cur_power": v = round(float(v) * 10 ** -sc.get("cur_power", 1), 1)
    if l["code"] == "add_ele": v = round(float(v) * 10 ** -sc.get("add_ele", 3), 3)
    out.append({"zaman": datetime.fromtimestamp(int(l["event_time"]) / 1000, TR).strftime("%Y-%m-%d %H:%M:%S"),
                "kod": l["code"], "deger": v, "kaynak": l.get("event_from"), "id": l.get("event_id")})
(ROOT / "priz_gecmis.json").write_text(json.dumps({"priz": did, "olusturma": simdi.strftime("%Y-%m-%d %H:%M"), "kayitlar": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(out), "kayıt")
