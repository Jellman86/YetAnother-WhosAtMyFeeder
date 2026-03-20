import os

def get_ram_usage_string() -> str | None:
    """Returns a formatted string of current system RAM usage (e.g., '4.2GB / 16.0GB'), or None if unavailable."""
    try:
        if not os.path.exists("/proc/meminfo"):
            return None
            
        with open("/proc/meminfo", "r") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
        
        mem_total = meminfo.get("MemTotal")
        mem_available = meminfo.get("MemAvailable")
        
        if mem_total is not None and mem_available is not None:
            used_kb = mem_total - mem_available
            used_gb = used_kb / (1024 * 1024)
            total_gb = mem_total / (1024 * 1024)
            return f"{used_gb:.1f}GB / {total_gb:.1f}GB"
            
    except Exception:
        pass
        
    return None
