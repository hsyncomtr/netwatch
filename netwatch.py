#!/usr/bin/env python3
"""Terminal tabanlı internet bağlantı izleyicisi.

Özellikler:
- Her saniye google.com ping kontrolü yapar.
- Yaklaşık ping süresini ayrıştırır.
- Public IP adresini düzenli aralıklarla kontrol eder.
- IP değişimini olay listesinde gösterir.
- Aktif kesinti süresini canlı sayaç olarak gösterir.
- Basit renkler ve spinner ile sade bir canlı ekran sunar.
- Yalnızca Python standard library kullanır.
"""

from __future__ import annotations

import datetime as dt
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

try:
    import ctypes
except ImportError:
    ctypes = None
from typing import List, Optional


PING_HOST = "google.com"
PING_INTERVAL_SECONDS = 1.0
PING_TIMEOUT_SECONDS = 2.0
IP_CHECK_EVERY_SECONDS = 10.0
HIGH_PING_THRESHOLD_MS = 1000.0
MAX_EVENTS = 12
PUBLIC_IP_SERVICES = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
)


class Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


ANSI_SUPPORTED = False


@dataclass
class PingResult:
    ok: bool
    latency_ms: Optional[float]
    message: str
    checked_at: dt.datetime


@dataclass
class OutageRecord:
    started_at: dt.datetime
    ended_at: dt.datetime

    @property
    def duration_seconds(self) -> int:
        return round((self.ended_at - self.started_at).total_seconds())


@dataclass
class AppState:
    started_at: dt.datetime = field(default_factory=dt.datetime.now)
    last_ping: Optional[PingResult] = None
    current_ip: str = "Bilinmiyor"
    last_ip_check_at: float = 0.0
    last_ip_error: Optional[str] = None
    is_connected: Optional[bool] = None
    outage_started_at: Optional[dt.datetime] = None
    completed_outages: List[OutageRecord] = field(default_factory=list)
    event_log: List[str] = field(default_factory=list)
    ping_history: List[Optional[float]] = field(default_factory=list)
    stop_requested: bool = False

    def add_event(self, message: str) -> None:
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        self.event_log.insert(0, f"[{timestamp}] {message}")
        del self.event_log[MAX_EVENTS:]

    def add_ping_sample(self, latency_ms: Optional[float]) -> None:
        self.ping_history.append(latency_ms)
        if len(self.ping_history) > 30:
            self.ping_history.pop(0)


SPINNER_FRAMES = ["⠁", "⠂", "⠄", "⠂"]


def enable_ansi_support() -> bool:
    if not sys.stdout.isatty():
        return False

    if os.name != "nt":
        return True

    if ctypes is None:
        return False

    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        if handle == 0:
            return False

        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return False

        enabled = mode.value | 0x0004
        if kernel32.SetConsoleMode(handle, enabled) == 0:
            return False
        return True
    except Exception:
        return False


def clear_screen() -> None:
    if ANSI_SUPPORTED:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        return

    os.system("cls" if os.name == "nt" else "clear")


def hide_cursor() -> None:
    if ANSI_SUPPORTED:
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()


def show_cursor() -> None:
    if ANSI_SUPPORTED:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def colorize(text: str, color: str) -> str:
    if ANSI_SUPPORTED:
        return f"{color}{text}{Ansi.RESET}"
    return text


def bold(text: str) -> str:
    if ANSI_SUPPORTED:
        return f"{Ansi.BOLD}{text}{Ansi.RESET}"
    return text


def format_duration(delta: dt.timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def sanitize_text(text: str, limit: int = 80) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def ping_once(host: str) -> PingResult:
    checked_at = dt.datetime.now()
    system = platform.system().lower()

    if system == "windows":
        command = ["ping", "-n", "1", "-w", str(int(PING_TIMEOUT_SECONDS * 1000)), host]
    else:
        command = ["ping", "-c", "1", "-W", str(max(1, int(PING_TIMEOUT_SECONDS))), host]

    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=PING_TIMEOUT_SECONDS + 1,
        )
    except Exception as exc:  # noqa: BLE001
        return PingResult(False, None, f"Ping komutu çalışmadı: {sanitize_text(str(exc))}", checked_at)

    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    output = output.strip()

    latency_patterns = [
        r"time[=<]\s*(\d+(?:[\.,]\d+)?)\s*ms",
        r"time=\s*(\d+(?:[\.,]\d+)?)",
        r"Average = (\d+(?:[\.,]\d+)?)ms",
        r"Ortalama = (\d+(?:[\.,]\d+)?)ms",
    ]

    latency_ms: Optional[float] = None
    for pattern in latency_patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            latency_ms = float(match.group(1).replace(",", "."))
            break

    if completed.returncode == 0:
        message = "Yanıt alındı"
        if latency_ms is None:
            message = "Yanıt alındı, süre ayrıştırılamadı"
        return PingResult(True, latency_ms, message, checked_at)

    lowered = output.lower()
    if "timed out" in lowered or "zaman aşımı" in lowered:
        message = "Ping zaman aşımına uğradı"
    elif "could not find host" in lowered or "host bulunamadı" in lowered:
        message = "Host çözümlenemedi"
    elif output:
        message = sanitize_text(output)
    else:
        message = "Ping başarısız"

    return PingResult(False, None, message, checked_at)


def fetch_public_ip(timeout: float = 3.0) -> tuple[Optional[str], Optional[str]]:
    headers = {"User-Agent": "Mozilla/5.0"}
    for service_url in PUBLIC_IP_SERVICES:
        request = urllib.request.Request(service_url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace").strip()
                if body:
                    return body, None
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            last_error = sanitize_text(str(exc))
            continue
    return None, last_error if "last_error" in locals() else "IP servisine erişilemedi"


def build_ping_bar(history: List[Optional[float]], width: int = 24) -> str:
    samples = history[-width:]
    if len(samples) < width:
        samples = [None] * (width - len(samples)) + samples

    chars = []
    for sample in samples:
        if sample is None:
            chars.append(colorize("·", Ansi.RED))
        elif sample >= HIGH_PING_THRESHOLD_MS:
            chars.append(colorize("▲", Ansi.YELLOW))
        elif sample >= 200:
            chars.append(colorize("■", Ansi.CYAN))
        else:
            chars.append(colorize("■", Ansi.GREEN))
    return "".join(chars)


def format_ping_status(ping: Optional[PingResult], spinner_index: int) -> tuple[str, str]:
    spinner = SPINNER_FRAMES[spinner_index % len(SPINNER_FRAMES)]

    if ping is None:
        return colorize(f"{spinner} İlk ölçüm bekleniyor", Ansi.CYAN), "-"

    if ping.ok:
        if ping.latency_ms is None:
            return colorize(f"{spinner} Bağlantı iyi", Ansi.GREEN), "ölçülemedi"
        if ping.latency_ms >= HIGH_PING_THRESHOLD_MS:
            return colorize(f"⚠️  Yüksek ping", Ansi.YELLOW), f"{ping.latency_ms:.0f} ms"
        return colorize(f"{spinner} Bağlantı iyi", Ansi.GREEN), f"{ping.latency_ms:.0f} ms"

    return colorize("✕ Bağlantı koptu", Ansi.RED), "-"


def draw_screen(state: AppState, spinner_index: int) -> None:
    clear_screen()
    terminal_width = shutil.get_terminal_size((100, 30)).columns
    line = "═" * max(60, min(terminal_width - 2, 96))

    runtime = format_duration(dt.datetime.now() - state.started_at)
    ping_status, ping_value = format_ping_status(state.last_ping, spinner_index)
    current_time = dt.datetime.now().strftime("%H:%M:%S")

    print(bold(line))
    print(bold("  İNTERNET DURUM İZLEYİCİSİ"))
    print(bold(line))
    print(f"Hedef             : {PING_HOST}")
    print(f"Çalışma süresi    : {runtime}")
    print(f"Son kontrol       : {current_time}")
    print(f"Durum             : {ping_status}")
    print(f"Ping              : {ping_value}")
    print(f"Public IP         : {state.current_ip}")

    if state.last_ip_error:
        print(f"IP kontrol notu   : {colorize(state.last_ip_error, Ansi.YELLOW)}")
    else:
        print("IP kontrol notu   : -")

    print(bold(line))
    print("Son 30 ping özeti : " + build_ping_bar(state.ping_history))

    if state.outage_started_at is not None:
        outage_duration = dt.datetime.now() - state.outage_started_at
        print(colorize(f"Aktif kesinti     : {int(outage_duration.total_seconds())} saniyedir sürüyor", Ansi.RED))
    else:
        print(colorize("Aktif kesinti     : Yok", Ansi.GREEN))

    print(bold(line))
    print("Son olaylar")
    if state.event_log:
        for event in state.event_log[:MAX_EVENTS]:
            print(f"- {event}")
    else:
        print("- Henüz olay kaydı yok")

    print(bold(line))
    print("Tamamlanan kesintiler")
    if state.completed_outages:
        for index, outage in enumerate(reversed(state.completed_outages[-8:]), start=1):
            started = outage.started_at.strftime("%H:%M:%S")
            ended = outage.ended_at.strftime("%H:%M:%S")
            print(f"- #{index}  {started} -> {ended}  |  {outage.duration_seconds} sn")
    else:
        print("- Kayıtlı kesinti yok")

    print(bold(line))
    print(colorize("Ctrl+C ile çıkabilirsiniz.", Ansi.DIM))


def update_connectivity_state(state: AppState, ping_result: PingResult) -> None:
    previous = state.is_connected
    state.last_ping = ping_result
    state.add_ping_sample(ping_result.latency_ms if ping_result.ok else None)

    if previous is None:
        state.is_connected = ping_result.ok
        if ping_result.ok:
            if ping_result.latency_ms is not None:
                state.add_event(f"Bağlantı aktif, {ping_result.latency_ms:.0f} ms")
            else:
                state.add_event("Bağlantı aktif")
        else:
            state.outage_started_at = ping_result.checked_at
            state.add_event("Bağlantı başlangıçta kesik göründü")
        return

    if ping_result.ok and not previous:
        started_at = state.outage_started_at or ping_result.checked_at
        outage = OutageRecord(started_at=started_at, ended_at=ping_result.checked_at)
        state.completed_outages.append(outage)
        state.outage_started_at = None
        state.is_connected = True
        state.add_event(f"Bağlantı geri geldi, kesinti {outage.duration_seconds} sn sürdü")
        return

    if not ping_result.ok and previous:
        state.is_connected = False
        state.outage_started_at = ping_result.checked_at
        state.add_event("Bağlantı koptu")
        return

    state.is_connected = ping_result.ok

    if ping_result.ok and ping_result.latency_ms is not None and ping_result.latency_ms >= HIGH_PING_THRESHOLD_MS:
        state.add_event(f"Yüksek ping algılandı: {ping_result.latency_ms:.0f} ms")


def refresh_public_ip_if_needed(state: AppState) -> None:
    now_monotonic = time.monotonic()
    if now_monotonic - state.last_ip_check_at < IP_CHECK_EVERY_SECONDS:
        return

    state.last_ip_check_at = now_monotonic
    ip_value, error_text = fetch_public_ip()

    if ip_value:
        state.last_ip_error = None
        if state.current_ip == "Bilinmiyor":
            state.current_ip = ip_value
            state.add_event(f"Public IP algılandı: {ip_value}")
        elif state.current_ip != ip_value:
            state.current_ip = ip_value
            state.add_event(f"IP değişti -> {ip_value}")
    else:
        state.last_ip_error = error_text or "IP alınamadı"
        if state.current_ip == "Bilinmiyor":
            state.add_event("Public IP henüz alınamadı")


def install_signal_handlers(state: AppState) -> None:
    def request_stop(signum: int, frame: object) -> None:  # noqa: ARG001
        state.stop_requested = True

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)


def print_exit_summary(state: AppState) -> None:
    print()
    print(bold("İzleyici durduruldu."))
    print(f"Toplam çalışma süresi : {format_duration(dt.datetime.now() - state.started_at)}")
    print(f"Tamamlanan kesinti    : {len(state.completed_outages)}")
    if state.outage_started_at is not None:
        active_seconds = int((dt.datetime.now() - state.outage_started_at).total_seconds())
        print(f"Aktif kesinti         : {active_seconds} sn ile devam ediyordu")
    print(f"Son public IP         : {state.current_ip}")


def main() -> int:
    global ANSI_SUPPORTED

    ANSI_SUPPORTED = enable_ansi_support()
    state = AppState()
    spinner_index = 0
    install_signal_handlers(state)

    try:
        hide_cursor()
        state.add_event("İzleyici başlatıldı")

        while not state.stop_requested:
            loop_started = time.monotonic()

            ping_result = ping_once(PING_HOST)
            update_connectivity_state(state, ping_result)
            refresh_public_ip_if_needed(state)
            draw_screen(state, spinner_index)

            spinner_index += 1
            elapsed = time.monotonic() - loop_started
            sleep_seconds = max(0.0, PING_INTERVAL_SECONDS - elapsed)
            time.sleep(sleep_seconds)

    finally:
        show_cursor()
        clear_screen()
        print_exit_summary(state)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
