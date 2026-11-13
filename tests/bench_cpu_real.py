"""GERÇEK CPU ölçümü: gerçek bir tepsi host'u başlatır, widget'ları IPC ile açar ve host SÜRECİNİN CPU süresini ölçer.

Tahmin değil: işletim sisteminin süreç için tuttuğu kullanıcı+çekirdek CPU süresi (psutil, yoksa GetProcessTimes)
ölçüm penceresinin başında ve sonunda okunur. Raporlanan:
  * tek çekirdek eşdeğeri  = CPU süresi / duvar süresi × 100     (bir çekirdeğin yüzde kaçı)
  * toplam (tüm çekirdekler) = tek çekirdek eşdeğeri / mantıksal çekirdek sayısı
  * net = senaryo − boşta host (widget yokken host'un kendi maliyeti)

Kullanım:
    python tests/bench_cpu_real.py                    # gerçek ekran, varsayılan senaryolar, 30 sn
    python tests/bench_cpu_real.py --offscreen        # QT_QPA_PLATFORM=offscreen (ekran birleştirme yok)
    python tests/bench_cpu_real.py --seconds 15 --scenario saturn_3d --scenario "saturn_3d,donut_3d"
    python tests/bench_cpu_real.py --json sonuc.json
Çalışan bir ASCII Mate host'u varsa ölçüm yapılmaz (tekil örnek kilidi). Ölçüm kendi geçici config klasörünü kullanır
(ASCII_MATE_HOME), kullanıcının ayarlarına dokunmaz. Ölçüm sırasında ekranda widget'lar görünür; fareyle üstüne gelmeyin.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.cli.terminal_hub import is_ipc_available, send_ipc  # noqa: E402

DEFAULT_SCENARIOS = [
    "idle",  # boşta host
    "saturn_3d",
    "donut_3d",
    "heart_3d",
    "christmas_tree_3d",
    "hd_torus_knot_spin",
    "hd_poppy_field",
    "hd_portrait_static",
    "saturn_3d,donut_3d,heart_3d,hd_poppy_field",
]


def cpu_seconds(pid: int) -> float:
    try:
        import psutil

        t = psutil.Process(pid).cpu_times()
        return float(t.user + t.system)
    except ImportError:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32")
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        ft = [wintypes.FILETIME() for _ in range(4)]
        k32.GetProcessTimes(h, *[ctypes.byref(f) for f in ft])
        k32.CloseHandle(h)

        def v(f: wintypes.FILETIME) -> float:
            return ((f.dwHighDateTime << 32) | f.dwLowDateTime) / 1e7

        return v(ft[2]) + v(ft[3])


def rss_mb(pid: int) -> float:
    try:
        import psutil

        return psutil.Process(pid).memory_info().rss / 1048576.0
    except Exception:
        return 0.0


def start_host(offscreen: bool, home: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["ASCII_MATE_HOME"] = str(home)
    env["PYTHONUTF8"] = "1"
    if offscreen:
        env["QT_QPA_PLATFORM"] = "offscreen"
    else:
        env.pop("QT_QPA_PLATFORM", None)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen([sys.executable, str(BASE / "main.py"), "--host"], cwd=str(BASE), env=env, creationflags=flags)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if send_ipc({"cmd": "ping"}, timeout=0.5):
            return proc
        time.sleep(0.2)
    proc.kill()
    raise SystemExit("host başlatılamadı")


def _stats() -> List[dict]:
    r = send_ipc({"cmd": "stats"}, timeout=2) or {}
    return list(r.get("widgets", []))


def measure(pid: int, seconds: float) -> Dict[str, object]:
    s0 = _stats()
    c0, t0 = cpu_seconds(pid), time.perf_counter()
    time.sleep(seconds)
    c1, t1 = cpu_seconds(pid), time.perf_counter()
    s1 = _stats()
    wall = t1 - t0
    single = (c1 - c0) / wall * 100.0
    # Gerçekleşen tick/boyama hızları: widget'ın gerçekten çalıştığını (duraklamadığını) kanıtlar
    rates = []
    for a, b in zip(s0, s1):
        rates.append({"asset_id": b["asset_id"], "tick_hz": (b["ticks"] - a["ticks"]) / wall,
                      "paint_hz": (b["paints"] - a["paints"]) / wall, "suspended": b["suspended"],
                      "cell_path": b.get("cell_path"), "hd": b.get("hd")})
    return {"single_core_pct": single, "total_pct": single / (os.cpu_count() or 1), "rss_mb": rss_mb(pid), "rates": rates}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offscreen", action="store_true")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--warmup", type=float, default=4.0)
    ap.add_argument("--scenario", action="append", help="virgülle ayrılmış id listesi; boş = boşta host")
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)

    if is_ipc_available():
        print("Çalışan bir ASCII Mate host'u var; önce kapatın (tepsi → Tamamen Çık).")
        return 2
    home = Path(tempfile.mkdtemp(prefix="ascii_mate_bench_"))
    (home / "config.json").write_text(json.dumps({"global": {"hd_enabled": True, "battery_saver": False}}), encoding="utf-8")
    scenarios = args.scenario if args.scenario is not None else DEFAULT_SCENARIOS
    proc = start_host(args.offscreen, home)
    results = []
    try:
        idle = None
        for sc in scenarios:
            send_ipc({"cmd": "close_all"}, timeout=2)
            ids = [s for s in sc.split(",") if s and s != "idle"]
            for aid in ids:
                r = send_ipc({"cmd": "spawn", "asset_id": aid}, timeout=5)
                if not r or not r.get("ok"):
                    print(f"[UYARI] açılamadı: {aid}: {r}")
            time.sleep(args.warmup)
            m = measure(proc.pid, args.seconds)
            m["scenario"] = "(boşta host)" if not ids else sc
            if not ids:
                idle = m["single_core_pct"]
            m["net_single_core_pct"] = m["single_core_pct"] - (idle or 0.0) if ids else 0.0
            results.append(m)
            rate_txt = " ".join(f"[{r['asset_id']}: tick {r['tick_hz']:.1f}/s boya {r['paint_hz']:.1f}/s"
                                f"{' DURAKLADI' if r['suspended'] else ''}]" for r in m["rates"])
            print(f"{m['scenario']:52} tek çekirdek %{m['single_core_pct']:6.2f}  net %{m['net_single_core_pct']:6.2f}  "
                  f"toplam %{m['total_pct']:5.2f}  RSS {m['rss_mb']:6.0f} MB  {rate_txt}", flush=True)
    finally:
        send_ipc({"cmd": "shutdown"}, timeout=2)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    meta = {"offscreen": args.offscreen, "seconds": args.seconds, "cpu_count": os.cpu_count(), "results": results}
    if args.json:
        Path(args.json).write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
