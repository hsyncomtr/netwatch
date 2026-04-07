# netwatch

Terminal tabanlı internet bağlantı izleyicisi. Hiçbir üçüncü taraf bağımlılığı gerektirmez; yalnızca Python standart kütüphanesiyle çalışır.

## Özellikler
- Saniye başı ping kontrolü ve gecikme ölçümü
- Son 30 pinge ait grafiksel geçmiş (ASCII)
- Aktif kesinti süresini canlı sayaç olarak gösterir
- Geçmiş kesintileri başlangıç/bitiş saatiyle listeler
- Public IP adresini takip eder, değiştiğinde bildirir
- Yüksek ping uyarısı (varsayılan: 1000 ms)
- Windows, macOS ve Linux üzerinde çalışır
- ANSI renk desteği (uyumlu terminal gerektirir)

## Kullanım
```bash
python netwatch.py
```

Çıkmak için `Ctrl+C`.
