import os
import time
import signal
import sys
from datetime import datetime
from typing import Optional, Tuple
import re

import pyipmi
import pyipmi.interfaces
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.text import Text
from pydantic import BaseModel

class ServerConfig(BaseModel):
    idrac_host: str = os.getenv('IDRAC_HOST', 'local')
    idrac_username: str = os.getenv('IDRAC_USERNAME', 'root')
    idrac_password: str = os.getenv('IDRAC_PASSWORD', 'calvin')
    fan_speed: int = int(os.getenv('FAN_SPEED', '5'))
    cpu_temp_threshold: int = int(os.getenv('CPU_TEMPERATURE_THRESHOLD', '50'))
    check_interval: int = int(os.getenv('CHECK_INTERVAL', '60'))
    disable_pcie_cooling: bool = os.getenv('DISABLE_THIRD_PARTY_PCIE_CARD_DELL_DEFAULT_COOLING_RESPONSE', 'false').lower() == 'true'
    keep_pcie_state: bool = os.getenv('KEEP_THIRD_PARTY_PCIE_CARD_COOLING_RESPONSE_STATE_ON_EXIT', 'false').lower() == 'true'

class DellServer:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.ipmi = self._setup_ipmi()
        self.console = Console()
        self.model, self.manufacturer = self._get_server_info()
        self.is_gen14_or_newer = self._check_server_generation()
        self.current_profile = "Initializing..."
        
    def _setup_ipmi(self) -> pyipmi.Interface:
        interface = pyipmi.interfaces.create_interface(
            interface='ipmitool',
            interface_type='lanplus'
        )
        
        if self.config.idrac_host == 'local':
            ipmi = pyipmi.create_connection(interface)
            ipmi.session.set_session_type_rmcp(host='localhost')
        else:
            ipmi = pyipmi.create_connection(interface)
            ipmi.session.set_session_type_rmcp(
                host=self.config.idrac_host,
                username=self.config.idrac_username,
                password=self.config.idrac_password
            )
        
        return ipmi

    def _get_server_info(self) -> Tuple[str, str]:
        fru = self.ipmi.get_fru_inventory()
        return fru.board_product_name, fru.board_manufacturer

    def _check_server_generation(self) -> bool:
        pattern = r'.*[RT]\s?[0-9][4-9]0.*'
        return bool(re.match(pattern, self.model))

    def get_temperatures(self) -> dict:
        sensors = self.ipmi.get_sensor_reading(0)
        temps = {
            'inlet': None,
            'cpu1': None,
            'cpu2': None,
            'exhaust': None
        }
        
        for sensor in sensors:
            if 'Inlet' in sensor.name:
                temps['inlet'] = sensor.value
            elif 'CPU1' in sensor.name:
                temps['cpu1'] = sensor.value
            elif 'CPU2' in sensor.name:
                temps['cpu2'] = sensor.value
            elif 'Exhaust' in sensor.name:
                temps['exhaust'] = sensor.value
        
        return temps

    def set_fan_speed(self, speed: int):
        hex_speed = hex(speed)[2:].zfill(2)
        
        self.ipmi.raw_command(0x30, 0x30, 0x01, 0x00)
        self.ipmi.raw_command(0x30, 0x30, 0x02, 0xff, int(hex_speed, 16))
        self.current_profile = f"User static fan control profile ({speed}%)"

    def set_dell_profile(self):
        self.ipmi.raw_command(0x30, 0x30, 0x01, 0x01)
        self.current_profile = "Dell default dynamic fan control profile"

    def manage_pcie_cooling(self, enable: bool):
        if not self.is_gen14_or_newer:
            cmd = [0x30, 0xce, 0x00, 0x16, 0x05, 0x00, 0x00, 0x00, 0x05, 0x00]
            cmd.append(0x00 if enable else 0x01)
            cmd.extend([0x00, 0x00])
            self.ipmi.raw_command(*cmd)

    def create_table(self, temps: dict) -> Table:
        table = Table(title="Dell iDRAC Fan Controller Status")
        
        table.add_column("Time", justify="center")
        table.add_column("Inlet Temp", justify="right")
        table.add_column("CPU1 Temp", justify="right")
        table.add_column("CPU2 Temp", justify="right")
        table.add_column("Exhaust Temp", justify="right")
        table.add_column("Fan Profile", justify="left")
        table.add_column("Fan Speed", justify="right")
        
        def temp_color(temp: Optional[float]) -> Text:
            if temp is None:
                return Text("-", style="dim")
            temp_text = f"{temp}°C"
            if temp >= self.config.cpu_temp_threshold:
                return Text(temp_text, style="bold red")
            elif temp >= self.config.cpu_temp_threshold * 0.9:
                return Text(temp_text, style="bold yellow")
            return Text(temp_text, style="green")

        table.add_row(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            temp_color(temps['inlet']),
            temp_color(temps['cpu1']),
            temp_color(temps['cpu2']),
            temp_color(temps['exhaust']),
            self.current_profile,
            f"{self.config.fan_speed}%"
        )
        
        return table

def main():
    config = ServerConfig()
    server = DellServer(config)
    
    def graceful_exit(signum, frame):
        server.console.print("\n[yellow]Shutting down...[/yellow]")
        server.set_dell_profile()
        if not config.keep_pcie_state:
            server.manage_pcie_cooling(True)
        sys.exit(0)

    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    if config.disable_pcie_cooling:
        server.manage_pcie_cooling(False)

    with Live(server.create_table(server.get_temperatures()), 
              refresh_per_second=1, 
              console=server.console) as live:
        while True:
            temps = server.get_temperatures()
            
            if (temps['cpu1'] and temps['cpu1'] > config.cpu_temp_threshold) or \
               (temps['cpu2'] and temps['cpu2'] > config.cpu_temp_threshold):
                server.set_dell_profile()
            else:
                server.set_fan_speed(config.fan_speed)
            
            live.update(server.create_table(temps))
            time.sleep(config.check_interval)

if __name__ == "__main__":
    main()