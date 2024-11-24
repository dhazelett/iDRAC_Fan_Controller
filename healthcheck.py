import sys
import os
from typing import Dict, Any
from pydrac import ServerConfig, DellServer

def check_temperatures(temps: Dict[str, Any], config: ServerConfig) -> tuple[bool, str]:
    """
    Check if temperatures are within safe ranges.
    Accounts for the difference between package temperature (what we measure)
    and junction temperature (what we want to protect against).
    """
    if not temps:
        return False, "No temperature data available"

    # Check if we have critical temperature sensors
    if temps['cpu1'] is None and temps['cpu2'] is None:
        return False, "No CPU temperature readings available"

    # Adjust threshold to account for junction temperature difference
    # If we want to protect against Tj of 70°C and Tj is typically 15°C higher
    # than what we measure, we should trigger at 55°C measured temperature
    adjusted_threshold = config.cpu_temp_threshold - config.junction_offset

    if temps['cpu1'] and temps['cpu1'] > adjusted_threshold:
        return False, (f"CPU1 package temperature ({temps['cpu1']}°C) indicates junction "
                      f"temperature may exceed threshold ({config.cpu_temp_threshold}°C)")
    if temps['cpu2'] and temps['cpu2'] > adjusted_threshold:
        return False, (f"CPU2 package temperature ({temps['cpu2']}°C) indicates junction "
                      f"temperature may exceed threshold ({config.cpu_temp_threshold}°C)")

    return True, "Temperature checks passed"

def healthcheck() -> bool:
    try:
        config = ServerConfig()
        server = DellServer(config)

        temps = server.get_temperatures()
        temps_ok, temp_message = check_temperatures(temps, config)
        if not temps_ok:
            print(f"Temperature check failed: {temp_message}", file=sys.stderr)
            return False

        if not server._run_ipmitool('mc', 'info'):
            print("IPMI communication check failed", file=sys.stderr)
            return False

        return True

    except Exception as e:
        print(f"Healthcheck failed with error: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    sys.exit(0 if healthcheck() else 1)