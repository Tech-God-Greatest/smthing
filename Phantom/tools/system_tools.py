"""
tools/system_tools.py — Comprehensive hardware and system monitoring tools for Phantom AI.

TOOL CONTRACT
=============
  ALL_TOOLS   list   -> OpenAI tool schemas for the tools in this file
  execute     func   -> execute(name: str, args: dict) -> str
"""

import subprocess
import shutil
import json
import platform
import time
import psutil

# Optional pynvml import for fast native NVML GPU access
try:
    import pynvml
    HAS_PYNVML = True
except ImportError:
    HAS_PYNVML = False


# ── Helper functions for metrics collection ───────────────────────────────────

def _get_gpu_metrics() -> list:
    """Fetch GPU usage, VRAM, temperature, fan speed, and power draw for all GPUs."""
    gpus = []

    # 1. Primary: Native pynvml (NVML)
    if HAS_PYNVML:
        try:
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            for i in range(count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")

                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_util = util.gpu

                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                vram_used_mb = mem.used / (1024 ** 2)
                vram_total_mb = mem.total / (1024 ** 2)
                vram_pct = (mem.used / mem.total * 100) if mem.total else 0.0

                try:
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                except Exception:
                    temp = "N/A"

                try:
                    fan = pynvml.nvmlDeviceGetFanSpeed(handle)
                except Exception:
                    fan = "N/A"

                try:
                    power_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
                    power_w = round(power_mw / 1000.0, 2)
                    limit_mw = pynvml.nvmlDeviceGetPowerManagementLimit(handle)
                    limit_w = round(limit_mw / 1000.0, 2)
                except Exception:
                    power_w = "N/A"
                    limit_w = "N/A"

                gpus.append({
                    "index": i,
                    "name": name,
                    "gpu_usage_pct": gpu_util,
                    "vram_used_mb": round(vram_used_mb, 1),
                    "vram_total_mb": round(vram_total_mb, 1),
                    "vram_usage_pct": round(vram_pct, 1),
                    "temp_c": temp,
                    "fan_speed_pct": fan,
                    "power_draw_w": power_w,
                    "power_limit_w": limit_w,
                })
            pynvml.nvmlShutdown()
            if gpus:
                return gpus
        except Exception:
            pass

    # 2. Secondary fallback: nvidia-smi CLI query
    if shutil.which("nvidia-smi"):
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,fan.speed,power.draw,power.limit",
                "--format=csv,noheader,nounits"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                for line in res.stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 9:
                        try:
                            idx = int(parts[0])
                            name = parts[1]
                            gpu_util = float(parts[2])
                            vram_used = float(parts[3])
                            vram_total = float(parts[4])
                            vram_pct = (vram_used / vram_total * 100) if vram_total else 0.0
                            temp = float(parts[5])
                            fan = parts[6]
                            try:
                                fan = float(fan)
                            except ValueError:
                                fan = "N/A"
                            power_w = float(parts[7])
                            limit_w = float(parts[8])

                            gpus.append({
                                "index": idx,
                                "name": name,
                                "gpu_usage_pct": gpu_util,
                                "vram_used_mb": round(vram_used, 1),
                                "vram_total_mb": round(vram_total, 1),
                                "vram_usage_pct": round(vram_pct, 1),
                                "temp_c": temp,
                                "fan_speed_pct": fan,
                                "power_draw_w": power_w,
                                "power_limit_w": limit_w,
                            })
                        except Exception:
                            continue
        except Exception:
            pass

    return gpus


_LIBRE_AVAILABLE = None

def _get_cpu_temperature() -> str:
    """Fetch CPU temperature via Windows performance counters / WMI or ACPI Thermal Zone."""
    # 1. Windows typeperf Thermal Zone Information (capped at 0.5s timeout)
    try:
        res = subprocess.run(
            ["typeperf", "\\Thermal Zone Information(*)\\Temperature", "-sc", "1"],
            capture_output=True,
            text=True,
            timeout=0.5
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            for line in lines:
                if line.startswith('"') and "," in line:
                    val_str = line.split(",")[-1].replace('"', '').strip()
                    try:
                        val_k = float(val_str)
                        if val_k > 200:  # Kelvin reading
                            val_c = round(val_k - 273.15, 1)
                            return f"{val_c} °C"
                    except ValueError:
                        pass
    except Exception:
        pass

    # 2. psutil sensors_temperatures fallback (Linux/macOS)
    if hasattr(psutil, "sensors_temperatures"):
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key, entries in temps.items():
                    for entry in entries:
                        if entry.current:
                            return f"{entry.current} °C ({entry.label or key})"
        except Exception:
            pass

    return "Sensor unavailable (requires elevated hardware monitor)"


def _get_disk_temperatures() -> str:
    """Fetch Disk temperatures via WMI / LibreHardwareMonitor if available."""
    global _LIBRE_AVAILABLE
    if _LIBRE_AVAILABLE is False:
        return "Sensor unavailable (requires elevated hardware monitor)"

    try:
        cmd = "Get-CimInstance -Namespace root\\LibreHardwareMonitor -ClassName Sensor | Where-Object {$_.SensorType -eq 'Temperature' -and $_.Name -like '*Disk*'} | Select-Object Name, Value"
        res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd], capture_output=True, text=True, timeout=1.2)
        if res.returncode == 0 and res.stdout.strip():
            lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip() and not line.startswith("Name") and not line.startswith("----")]
            if lines:
                _LIBRE_AVAILABLE = True
                return ", ".join(lines)
    except Exception:
        pass

    _LIBRE_AVAILABLE = False
    return "Sensor unavailable (requires elevated hardware monitor like LibreHardwareMonitor)"


# ── Tool implementations ──────────────────────────────────────────────────────

def get_system_overview() -> str:
    """Get a complete system status report covering CPU, RAM, GPU, VRAM, Disk, Temperatures, Fans, Power, Motherboard, Display, and Network."""
    # 1. CPU
    cpu_usage = psutil.cpu_percent(interval=0.05)
    logical_cores = psutil.cpu_count(logical=True)
    phys_cores = psutil.cpu_count(logical=False)
    freq_info = psutil.cpu_freq()
    freq_str = f" @ {freq_info.current:.0f} MHz" if freq_info else ""
    cpu_temp = _get_cpu_temperature()

    # 2. RAM
    mem = psutil.virtual_memory()
    ram_used_gb = mem.used / (1024 ** 3)
    ram_total_gb = mem.total / (1024 ** 3)

    # 3. Disks
    disk_summaries = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            used_gb = usage.used / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            disk_summaries.append(f"{part.mountpoint} {used_gb:.1f}/{total_gb:.1f} GB ({usage.percent}%)")
        except Exception:
            pass
    disk_str = ", ".join(disk_summaries) if disk_summaries else "N/A"
    disk_temp = _get_disk_temperatures()

    # 4. GPU
    gpus = _get_gpu_metrics()
    if gpus:
        gpu_lines = []
        for g in gpus:
            gpu_lines.append(
                f"{g['name']}: {g['gpu_usage_pct']}% GPU Usage | VRAM {g['vram_used_mb']}/{g['vram_total_mb']} MB ({g['vram_usage_pct']}%) | "
                f"Temp {g['temp_c']} °C | Fan {g['fan_speed_pct']}% | Power {g['power_draw_w']} W / {g['power_limit_w']} W"
            )
        gpu_str = "\n".join(gpu_lines)
    else:
        gpu_str = "No discrete GPU detected or GPU metrics unavailable."

    # 5. Motherboard short snippet
    mb_lines = get_motherboard_info().splitlines()
    mb_summary = mb_lines[1] if len(mb_lines) > 1 else mb_lines[0]

    report = (
        f"=== SYSTEM MONITORING OVERVIEW ===\n"
        f"{mb_summary}\n"
        f"• CPU Usage: {cpu_usage}% ({phys_cores}P/{logical_cores}L Cores{freq_str})\n"
        f"• CPU Temp: {cpu_temp}\n"
        f"• RAM Usage: {ram_used_gb:.1f} GB / {ram_total_gb:.1f} GB ({mem.percent}%)\n"
        f"• Disk Usage: {disk_str}\n"
        f"• Disk Temp: {disk_temp}\n"
        f"• GPU Metrics:\n  {gpu_str}"
    )
    return report


def get_cpu_status() -> str:
    """Get detailed CPU usage %, per-core breakdown, clock speed, and CPU temperature."""
    per_core = psutil.cpu_percent(interval=0.05, percpu=True)
    total_usage = round(sum(per_core) / len(per_core), 1) if per_core else psutil.cpu_percent(interval=0.05)
    phys_cores = psutil.cpu_count(logical=False)
    logical_cores = psutil.cpu_count(logical=True)
    freq = psutil.cpu_freq()
    freq_str = f"{freq.current:.0f} MHz (Min: {freq.min:.0f} MHz, Max: {freq.max:.0f} MHz)" if freq else "N/A"
    cpu_temp = _get_cpu_temperature()

    core_str = ", ".join([f"C{i+1}: {p}%" for i, p in enumerate(per_core)])

    return (
        f"CPU Overview:\n"
        f"• Total Usage: {total_usage}%\n"
        f"• Temperature: {cpu_temp}\n"
        f"• Clock Speed: {freq_str}\n"
        f"• Cores: {phys_cores} Physical, {logical_cores} Logical\n"
        f"• Per-Core Usage: {core_str}"
    )


def get_cpu_specs() -> str:
    """Get CPU hardware specifications: processor model, vendor, physical cores, threads, rated max speed, and L2/L3 cache sizes."""
    try:
        cmd = 'Get-CimInstance -ClassName Win32_Processor | Select-Object Name,Manufacturer,MaxClockSpeed,NumberOfCores,NumberOfLogicalProcessors,L2CacheSize,L3CacheSize | ConvertTo-Json'
        res = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd], capture_output=True, text=True, timeout=5)
        proc = json.loads(res.stdout.strip())
        if isinstance(proc, list):
            proc = proc[0]
        name = proc.get('Name', platform.processor())
        mfr = proc.get('Manufacturer', '')
        cores = proc.get('NumberOfCores', psutil.cpu_count(logical=False))
        threads = proc.get('NumberOfLogicalProcessors', psutil.cpu_count(logical=True))
        max_speed = proc.get('MaxClockSpeed', 0)
        l2 = proc.get('L2CacheSize', 0)
        l3 = proc.get('L3CacheSize', 0)
        l3_mb = l3 / 1024 if l3 else 0
        return (
            f"CPU Specs & Architecture:\n"
            f"• Processor: {name}\n"
            f"• Vendor: {mfr}\n"
            f"• Architecture: {cores} Physical Cores / {threads} Logical Threads\n"
            f"• Max Rated Clock Speed: {max_speed} MHz\n"
            f"• Cache Sizes: L2 Cache: {l2} KB, L3 Cache: {l3_mb:.1f} MB"
        )
    except Exception as e:
        return f"CPU specs unavailable: {e}"


def get_gpu_status() -> str:
    """Get detailed GPU metrics: model name, GPU utilization %, VRAM used/total/%, GPU temperature, fan speed %, and power draw."""
    gpus = _get_gpu_metrics()
    if not gpus:
        return "No discrete GPU metrics available (NVIDIA GPU or NVML driver not detected)."

    output = []
    for g in gpus:
        output.append(
            f"GPU {g['index']} ({g['name']}):\n"
            f"• GPU Core Utilization: {g['gpu_usage_pct']}%\n"
            f"• VRAM Usage: {g['vram_used_mb']} MB / {g['vram_total_mb']} MB ({g['vram_usage_pct']}%)\n"
            f"• GPU Temperature: {g['temp_c']} °C\n"
            f"• Fan Speed: {g['fan_speed_pct']}%\n"
            f"• Power Consumption: {g['power_draw_w']} W (Power Limit: {g['power_limit_w']} W)"
        )
    return "\n\n".join(output)


def get_display_info() -> str:
    """Get display monitor & GPU specs: active screen resolution, refresh rate (Hz), graphics driver version, and GPU model."""
    try:
        cmd = 'Get-CimInstance -ClassName Win32_VideoController | Select-Object Name,CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate,DriverVersion | ConvertTo-Json'
        res = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd], capture_output=True, text=True, timeout=5)
        data = json.loads(res.stdout.strip())
        if isinstance(data, dict):
            data = [data]
        disp_lines = []
        for d in data:
            name = d.get('Name', 'Graphics Adapter')
            res_h = d.get('CurrentHorizontalResolution')
            res_v = d.get('CurrentVerticalResolution')
            hz = d.get('CurrentRefreshRate')
            drv = d.get('DriverVersion', 'N/A')
            res_str = f"{res_h}x{res_v} @ {hz} Hz" if res_h and res_v else "Resolution N/A"
            disp_lines.append(f"• GPU: {name} | Display: {res_str} | Driver Version: {drv}")
        return "Display & GPU Output Specs:\n" + "\n".join(disp_lines)
    except Exception as e:
        return f"Display info unavailable: {e}"


def get_ram_status() -> str:
    """Get system RAM memory statistics: total RAM, used RAM, available RAM, usage %, and swap/pagefile memory."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    used_gb = mem.used / (1024 ** 3)
    total_gb = mem.total / (1024 ** 3)
    avail_gb = mem.available / (1024 ** 3)

    swap_used_gb = swap.used / (1024 ** 3)
    swap_total_gb = swap.total / (1024 ** 3)

    return (
        f"RAM Memory Status:\n"
        f"• Total RAM: {total_gb:.2f} GB\n"
        f"• Used RAM: {used_gb:.2f} GB ({mem.percent}%)\n"
        f"• Available RAM: {avail_gb:.2f} GB\n"
        f"• Pagefile / Swap: {swap_used_gb:.2f} GB / {swap_total_gb:.2f} GB ({swap.percent}%)"
    )


_RAM_SPECS_CACHE = None
_STORAGE_INFO_CACHE = None
_MOTHERBOARD_CACHE = None

def get_ram_hardware_specs() -> str:
    """Get physical RAM hardware details: installed memory module capacity per slot, RAM speed (MHz), slots filled, and part numbers."""
    global _RAM_SPECS_CACHE
    if _RAM_SPECS_CACHE is not None:
        return _RAM_SPECS_CACHE

    try:
        cmd = 'Get-CimInstance -ClassName Win32_PhysicalMemory | Select-Object Capacity,Speed,Manufacturer,PartNumber | ConvertTo-Json'
        res = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd], capture_output=True, text=True, timeout=3.0)
        data = json.loads(res.stdout.strip())
        if isinstance(data, dict):
            data = [data]
        sticks = []
        total_cap_gb = 0
        for i, slot in enumerate(data):
            cap_gb = int(slot.get('Capacity', 0)) / (1024 ** 3)
            total_cap_gb += cap_gb
            speed = slot.get('Speed', 'N/A')
            part = str(slot.get('PartNumber', '')).strip()
            mfr = str(slot.get('Manufacturer', '')).strip()
            sticks.append(f"• Slot {i+1}: {cap_gb:.0f} GB @ {speed} MHz (Part: {part or 'Generic'}, Manufacturer: {mfr or 'N/A'})")
        res_str = f"Physical RAM Hardware Specs:\n• Total Installed Memory: {total_cap_gb:.0f} GB across {len(sticks)} slots\n" + "\n".join(sticks)
        _RAM_SPECS_CACHE = res_str
        return res_str
    except Exception as e:
        return f"RAM hardware specs unavailable: {e}"


def get_disk_status() -> str:
    """Get disk storage statistics for all mounted partitions (used, free, total space, and usage %) and disk temperature."""
    partitions = psutil.disk_partitions(all=False)
    disk_lines = []
    for part in partitions:
        try:
            usage = psutil.disk_usage(part.mountpoint)
            used_gb = usage.used / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            free_gb = usage.free / (1024 ** 3)
            disk_lines.append(
                f"• Drive {part.mountpoint} ({part.fstype}): {used_gb:.2f} GB used / {total_gb:.2f} GB total ({usage.percent}% used, {free_gb:.2f} GB free)"
            )
        except Exception:
            pass

    disk_temp = _get_disk_temperatures()
    return "Disk Usage Status:\n" + "\n".join(disk_lines) + f"\n• Disk Temperature: {disk_temp}"


def get_storage_hardware_info() -> str:
    """Get physical storage drive specifications: drive model, size in GB, media type (HDD/SSD), bus interface (NVMe/SATA/IDE), and serial number."""
    global _STORAGE_INFO_CACHE
    if _STORAGE_INFO_CACHE is not None:
        return _STORAGE_INFO_CACHE

    try:
        cmd = 'Get-CimInstance -ClassName Win32_DiskDrive | Select-Object Model,MediaType,InterfaceType,Size,SerialNumber | ConvertTo-Json'
        res = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd], capture_output=True, text=True, timeout=3.0)
        data = json.loads(res.stdout.strip())
        if isinstance(data, dict):
            data = [data]
        disk_lines = []
        for d in data:
            model = d.get('Model', 'Disk Drive')
            media = d.get('MediaType', 'Storage')
            bus = d.get('InterfaceType', 'N/A')
            size_gb = int(d.get('Size', 0)) / (1024 ** 3)
            sn = str(d.get('SerialNumber', '')).strip()
            disk_lines.append(f"• {model}: {size_gb:.1f} GB ({media}, Bus: {bus}, S/N: {sn or 'N/A'})")
        res_str = "Physical Storage Drive Hardware Specs:\n" + "\n".join(disk_lines)
        _STORAGE_INFO_CACHE = res_str
        return res_str
    except Exception as e:
        return f"Storage hardware specs unavailable: {e}"


def get_motherboard_info() -> str:
    """Get motherboard & BIOS specifications: motherboard manufacturer, model name, board serial number, BIOS vendor, and BIOS version."""
    global _MOTHERBOARD_CACHE
    if _MOTHERBOARD_CACHE is not None:
        return _MOTHERBOARD_CACHE

    # 1. Native Windows Registry read (sub-millisecond instant fetch)
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS")
        m_mfr, _ = winreg.QueryValueEx(key, "BaseBoardManufacturer")
        m_prod, _ = winreg.QueryValueEx(key, "BaseBoardProduct")
        try:
            m_sn, _ = winreg.QueryValueEx(key, "BaseBoardSerialNumber")
        except Exception:
            m_sn = "N/A"
        b_mfr, _ = winreg.QueryValueEx(key, "BIOSVendor")
        b_ver, _ = winreg.QueryValueEx(key, "BIOSVersion")
        res = (
            f"Motherboard & BIOS Information:\n"
            f"• Motherboard: {m_mfr} {m_prod} (Serial Number: {m_sn})\n"
            f"• BIOS: {b_mfr} Version {b_ver}"
        )
        _MOTHERBOARD_CACHE = res
        return res
    except Exception:
        pass

    # 2. PowerShell fallback only if winreg fails
    try:
        cmd = 'Get-CimInstance -ClassName Win32_BaseBoard | Select-Object Manufacturer,Product,SerialNumber | ConvertTo-Json'
        res = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd], capture_output=True, text=True, timeout=3.0)
        mb = json.loads(res.stdout.strip())

        cmd_bios = 'Get-CimInstance -ClassName Win32_BIOS | Select-Object Manufacturer,SMBIOSBIOSVersion | ConvertTo-Json'
        res_bios = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd_bios], capture_output=True, text=True, timeout=3.0)
        bios = json.loads(res_bios.stdout.strip())

        m_mfr = mb.get('Manufacturer', 'N/A')
        m_prod = mb.get('Product', 'N/A')
        m_sn = mb.get('SerialNumber', 'N/A')
        b_mfr = bios.get('Manufacturer', 'N/A')
        b_ver = bios.get('SMBIOSBIOSVersion', 'N/A')
        res = (
            f"Motherboard & BIOS Information:\n"
            f"• Motherboard: {m_mfr} {m_prod} (Serial Number: {m_sn})\n"
            f"• BIOS: {b_mfr} Version {b_ver}"
        )
        _MOTHERBOARD_CACHE = res
        return res
    except Exception as e:
        return f"Motherboard info unavailable: {e}"


def get_network_info() -> str:
    """Get active network adapters, IP addresses (IPv4/IPv6), connection speeds (Mbps), status, and total network traffic (data sent/received)."""
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io = psutil.net_io_counters()
    net_lines = []
    for iface, addr_list in addrs.items():
        ipv4s = [a.address for a in addr_list if a.family.name in ['AF_INET', '4']]
        if ipv4s and not ipv4s[0].startswith('127.'):
            is_up = stats[iface].isup if iface in stats else True
            speed = f"{stats[iface].speed} Mbps" if iface in stats and stats[iface].speed > 0 else "Active"
            net_lines.append(f"• Interface \"{iface}\": IP {ipv4s[0]} ({speed}, Status: {'UP' if is_up else 'DOWN'})")

    sent_mb = io.bytes_sent / (1024 ** 2)
    recv_mb = io.bytes_recv / (1024 ** 2)
    traffic = f"Network Traffic: {sent_mb:.1f} MB Sent / {recv_mb:.1f} MB Received"
    return "Network Interfaces & IP Info:\n" + "\n".join(net_lines) + f"\n• {traffic}"


def get_battery_status() -> str:
    """Get battery percentage, power plug state (AC/Battery), and estimated battery remaining time."""
    bat = psutil.sensors_battery()
    if not bat:
        return "Power / Battery Status:\n• System Power: AC Power Outlet (Desktop PC / No battery installed)"
    pct = bat.percent
    plugged = "Plugged in (Charging/AC)" if bat.power_plugged else "On Battery Power"
    secs_left = bat.secsleft
    if secs_left == psutil.POWER_TIME_UNLIMITED:
        time_str = "Continuous AC Power"
    elif secs_left == psutil.POWER_TIME_UNKNOWN:
        time_str = "Calculating..."
    else:
        hrs = secs_left // 3600
        mins = (secs_left % 3600) // 60
        time_str = f"{hrs}h {mins}m remaining"
    return f"Battery & Power Status:\n• Charge Level: {pct}%\n• Power Source: {plugged}\n• Remaining Time: {time_str}"


def get_temperatures() -> str:
    """Get all available system component temperatures: CPU temperature, GPU temperature, and Disk temperature."""
    cpu_temp = _get_cpu_temperature()
    disk_temp = _get_disk_temperatures()
    gpus = _get_gpu_metrics()

    gpu_temp_str = ", ".join([f"{g['name']}: {g['temp_c']} °C" for g in gpus]) if gpus else "N/A"

    return (
        f"Hardware Temperatures:\n"
        f"• CPU Temperature: {cpu_temp}\n"
        f"• GPU Temperature: {gpu_temp_str}\n"
        f"• Disk Temperature: {disk_temp}"
    )


def get_fan_speeds() -> str:
    """Get current fan speeds for GPU and system cooling fans."""
    gpus = _get_gpu_metrics()
    gpu_fan_str = ", ".join([f"{g['name']}: {g['fan_speed_pct']}%" for g in gpus]) if gpus else "N/A"

    sys_fans = []
    if hasattr(psutil, "sensors_fans"):
        try:
            fans = psutil.sensors_fans()
            for key, entries in fans.items():
                for entry in entries:
                    sys_fans.append(f"{entry.label or key}: {entry.current} RPM")
        except Exception:
            pass

    sys_fan_str = ", ".join(sys_fans) if sys_fans else "Automatic / Mainboard managed"

    return (
        f"Fan Speeds:\n"
        f"• GPU Fan Speed: {gpu_fan_str}\n"
        f"• System / CPU Fans: {sys_fan_str}"
    )


def get_power_draw() -> str:
    """Get system power consumption statistics: GPU power draw (W), GPU power limit (W), and system power metrics."""
    gpus = _get_gpu_metrics()
    if gpus:
        gpu_power_lines = [
            f"• {g['name']}: {g['power_draw_w']} W (Power Limit: {g['power_limit_w']} W)"
            for g in gpus
        ]
        gpu_power_str = "\n".join(gpu_power_lines)
    else:
        gpu_power_str = "• GPU Power: N/A"

    return (
        f"Power Draw Status:\n"
        f"{gpu_power_str}\n"
        f"• System Power State: AC Power (Normal Desktop Operation)"
    )


def get_top_resource_apps(resource: str = "all", limit: int = 7) -> str:
    """Inbuilt Task Manager: list applications occupying the most CPU %, RAM memory (MB/GB), or GPU VRAM."""
    resource = str(resource).lower().strip()
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 7

    procs_list = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            p.cpu_percent()
            procs_list.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    time.sleep(0.04)

    from collections import defaultdict
    grouped = defaultdict(lambda: {'count': 0, 'ram_mb': 0.0, 'cpu_pct': 0.0, 'pids': []})

    for p in procs_list:
        try:
            name = p.name()
            if name in ['System Idle Process', 'Memory Compression']:
                continue
            cpu = p.cpu_percent()
            ram_mb = p.memory_info().rss / (1024 ** 2)

            grouped[name]['count'] += 1
            grouped[name]['ram_mb'] += ram_mb
            grouped[name]['cpu_pct'] += cpu
            grouped[name]['pids'].append(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    lines = ["=== INBUILT TASK MANAGER — TOP RESOURCE CONSUMING APPS ==="]

    if resource in ["ram", "memory", "all"]:
        sorted_ram = sorted(grouped.items(), key=lambda x: x[1]['ram_mb'], reverse=True)
        ram_lines = ["Top Applications by RAM Memory Usage:"]
        for app, data in sorted_ram[:limit]:
            c = data['count']
            proc_str = f"({c} processes)" if c > 1 else "(1 process)"
            ram_gb = data['ram_mb'] / 1024.0
            ram_fmt = f"{ram_gb:.2f} GB" if ram_gb >= 1.0 else f"{data['ram_mb']:.1f} MB"
            ram_lines.append(f"• {app:24s} {proc_str:14s} | RAM: {ram_fmt:>8s} | CPU: {data['cpu_pct']:5.1f}%")
        lines.append("\n".join(ram_lines))

    if resource in ["cpu", "processor", "all"]:
        sorted_cpu = sorted(grouped.items(), key=lambda x: x[1]['cpu_pct'], reverse=True)
        cpu_lines = ["Top Applications by CPU Usage:"]
        for app, data in sorted_cpu[:limit]:
            c = data['count']
            proc_str = f"({c} processes)" if c > 1 else "(1 process)"
            ram_gb = data['ram_mb'] / 1024.0
            ram_fmt = f"{ram_gb:.2f} GB" if ram_gb >= 1.0 else f"{data['ram_mb']:.1f} MB"
            cpu_lines.append(f"• {app:24s} {proc_str:14s} | CPU: {data['cpu_pct']:5.1f}% | RAM: {ram_fmt:>8s}")
        lines.append("\n".join(cpu_lines))

    gpus = _get_gpu_metrics()
    if gpus and resource in ["gpu", "vram", "all"]:
        gpu_summary = ", ".join([f"{g['name']} ({g['gpu_usage_pct']}% GPU, VRAM {g['vram_used_mb']}/{g['vram_total_mb']} MB)" for g in gpus])
        lines.append(f"GPU Hardware Status:\n• {gpu_summary}")

    return "\n\n".join(lines)


def get_process_list(filter_name: str = "") -> str:
    """Filter running processes by name to view PID, memory usage, CPU usage %, and status."""
    filter_name = str(filter_name).lower().strip()
    matching = []

    for p in psutil.process_iter(['pid', 'name', 'status', 'memory_info']):
        try:
            name = p.info['name'] or ""
            if not filter_name or filter_name in name.lower():
                rss_mb = p.info['memory_info'].rss / (1024 ** 2) if p.info['memory_info'] else 0.0
                matching.append((rss_mb, p.info['pid'], name, p.info['status']))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    matching.sort(key=lambda x: x[0], reverse=True)
    if not matching:
        return f"No active processes found matching '{filter_name}'."

    out_lines = [f"Process List (matching '{filter_name}' — total {len(matching)} found):"]
    for rss_mb, pid, name, status in matching[:15]:
        ram_fmt = f"{rss_mb/1024.0:.2f} GB" if rss_mb >= 1024 else f"{rss_mb:.1f} MB"
        out_lines.append(f"• PID {pid:6d} | {name:28s} | RAM: {ram_fmt:>8s} | Status: {status}")

    return "\n".join(out_lines)


# ── OpenAI Function Call Schemas ──────────────────────────────────────────────

ALL_TOOLS = [
    {
        "name": "get_system_overview",
        "description": "Get high-level system overview summary of CPU %, RAM %, GPU %, Disk %, and temperatures. (DO NOT use for listing top applications using resources — use get_top_resource_apps instead).",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_cpu_status",
        "description": "Get overall CPU utilization percentage, per-core utilization breakdown, clock speed, and CPU temperature. (DO NOT use to list which apps are using CPU — use get_top_resource_apps instead).",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_cpu_specs",
        "description": "Get CPU hardware specifications: processor model, vendor, physical core & thread count, max rated clock speed, and L2/L3 cache sizes.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_gpu_status",
        "description": "Get detailed GPU metrics including GPU core utilization percentage, VRAM memory usage, GPU temperature in °C, fan speed %, and power draw in Watts. (DO NOT use to list which apps are using GPU — use get_top_resource_apps instead).",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_display_info",
        "description": "Get display monitor and GPU specifications: active screen resolution, refresh rate (Hz), graphics driver version, and GPU model.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_ram_status",
        "description": "Get system RAM memory statistics: total RAM, used RAM, available RAM, usage percentage, and swap/pagefile memory. (DO NOT use to list which apps are using RAM — use get_top_resource_apps instead).",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_ram_hardware_specs",
        "description": "Get physical RAM hardware details: capacity per slot, RAM speed in MHz, slots filled, and RAM part numbers.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_disk_status",
        "description": "Get disk storage statistics for all mounted partitions (used, free, total space, and usage %) and disk temperature.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_storage_hardware_info",
        "description": "Get physical storage drive specifications: drive model, size in GB, media type (HDD/SSD), bus interface (NVMe/SATA/IDE), and serial numbers.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_motherboard_info",
        "description": "Get motherboard and BIOS specifications: motherboard manufacturer, model name, board serial number, BIOS vendor, and BIOS version.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_network_info",
        "description": "Get active network adapters (Ethernet, Wi-Fi), IP addresses (IPv4/IPv6), connection speeds (Mbps), status, and total network data traffic sent/received.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_battery_status",
        "description": "Get battery percentage, power plug state (AC/Battery), and estimated battery remaining time.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_temperatures",
        "description": "Get all hardware component temperatures: CPU temperature, GPU temperature, and Disk temperature.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_fan_speeds",
        "description": "Get current fan speeds for GPU cooling fans and system fans.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_power_draw",
        "description": "Get power consumption statistics: GPU power draw in Watts, GPU power limit, and system power state.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_top_resource_apps",
        "description": "ALWAYS use this tool when asked which app, process, or program is occupying or using the most CPU %, RAM memory MB/GB, or GPU VRAM. Inbuilt Task Manager ranking top apps by resource usage.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource": {
                    "type": "string",
                    "description": "Which resource to rank apps by: 'cpu', 'ram', 'gpu', or 'all' (default: 'all')."
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of top apps to list (default: 7)."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_process_list",
        "description": "Search or filter active running processes by name to view PID, memory usage, CPU usage %, and process status.",
        "parameters": {
            "type": "object",
            "properties": {
                "filter_name": {
                    "type": "string",
                    "description": "Optional name filter (e.g. 'chrome', 'python', 'code'). Leave empty to list all top processes."
                }
            },
            "required": []
        }
    }
]


# ── Dispatcher ────────────────────────────────────────────────────────────────

def execute(name: str, args: dict) -> str:
    """Route tool call by name. Called automatically by registry.dispatch."""
    if name == "get_system_overview":
        return get_system_overview()
    elif name == "get_cpu_status":
        return get_cpu_status()
    elif name == "get_cpu_specs":
        return get_cpu_specs()
    elif name == "get_gpu_status":
        return get_gpu_status()
    elif name == "get_display_info":
        return get_display_info()
    elif name == "get_ram_status":
        return get_ram_status()
    elif name == "get_ram_hardware_specs":
        return get_ram_hardware_specs()
    elif name == "get_disk_status":
        return get_disk_status()
    elif name == "get_storage_hardware_info":
        return get_storage_hardware_info()
    elif name == "get_motherboard_info":
        return get_motherboard_info()
    elif name == "get_network_info":
        return get_network_info()
    elif name == "get_battery_status":
        return get_battery_status()
    elif name == "get_temperatures":
        return get_temperatures()
    elif name == "get_fan_speeds":
        return get_fan_speeds()
    elif name == "get_power_draw":
        return get_power_draw()
    elif name == "get_top_resource_apps":
        resource = args.get("resource", "all")
        limit = args.get("limit", 7)
        return get_top_resource_apps(resource=resource, limit=limit)
    elif name == "get_process_list":
        filter_name = args.get("filter_name", "")
        return get_process_list(filter_name=filter_name)
    else:
        return f"[system_tools] Unknown tool: '{name}'"

