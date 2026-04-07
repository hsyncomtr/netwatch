# netwatch

A lightweight, real-time internet connection monitor for the terminal. No third-party dependencies — works entirely with the Python standard library.

## Features
- Ping check every second with latency measurement
- Rolling 30-sample ASCII ping history bar
- Live outage timer for the active disconnection
- Outage log with start/end timestamps and duration
- Public IP tracking with change detection
- High-ping warning (default threshold: 1000 ms)
- Cross-platform: Windows, macOS, Linux
- ANSI color support with automatic fallback

## Usage
```bash
python netwatch.py
```

Press `Ctrl+C` to exit.
<img width="895" height="638" alt="image" src="https://github.com/user-attachments/assets/7c6576ed-119a-498e-bf3f-49940ad0ed7a" />

########################################


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
