# ⚡ Elektrik Takip

Cihaz bazında elektrik sarfiyatı planı, son kaynak tarifesine göre fatura tahmini, gerçek faturayla karşılaştırma ve yıllık 4.000 kWh limit takibi.

Canlı: https://memory56.github.io/ElektrikTakip/

- **Cihazlar:** her cihaz için güç (W) × günlük saat ya da akıllı prizden ölçülen kWh/gün, 12 ay ayrı ayrı.
- **Fatura tahmini:** enerji = max(düşük tarife, (PTF + YEKDEM) × K × kalibrasyon); + dağıtım bedeli; ETV %5 (enerji bedeli üzerinden); KDV %10.
- **Faturalar:** Aydem e-Arşiv XML'i yüklenince endeks, tarih, kWh, birim fiyatlar ve tutar otomatik okunur. Brüt kWh = ödenecek ÷ kWh.
- **Fiyatlar:** `prices.json` her gün GitHub Actions ile EPİAŞ günlük bülteninden (Aylık PTF Ortalamaları) güncellenir (`scripts/fiyat_guncelle.py`).
- Veriler Firebase (amerikano-b037f) `elektrik/` düğümünde, Google girişiyle.
