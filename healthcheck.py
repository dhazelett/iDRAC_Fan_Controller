import sys
from idrac_controller import ServerConfig, DellServer

def health_check():
    try:
        config = ServerConfig()
        server = DellServer(config)
        temps = server.get_temperatures()
        return all(temp is not None for temp in temps.values() if temp is not None)
    except Exception as e:
        print(f"Healthcheck failed: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    sys.exit(0 if health_check() else 1)