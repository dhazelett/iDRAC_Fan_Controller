import os
import time
import signal
import sys
import subprocess
from datetime import datetime
from typing import Optional
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
    fan_speed: int = int(os.getenv('FAN_SPEED', '25'))
    fan_speed_max: int = int(os.getenv('FAN_SPEED_MAX', '100'))
    cpu_temp_threshold: int = int(os.getenv('CPU_TEMPERATURE_THRESHOLD', '60'))
    check_interval: int = int(os.getenv('CHECK_INTERVAL', '15'))
    disable_pcie_cooling: bool = os.getenv('DISABLE_THIRD_PARTY_PCIE_CARD_DELL_DEFAULT_COOLING_RESPONSE', 'false').lower() == 'true'
    keep_pcie_state: bool = os.getenv('KEEP_THIRD_PARTY_PCIE_CARD_COOLING_RESPONSE_STATE_ON_EXIT', 'false').lower() == 'true'
    fan_rpm_min: int = int(os.getenv('FAN_RPM_MIN', '2500'))
    fan_rpm_max: int = int(os.getenv('FAN_RPM_MAX', '12000'))
    calibrate_fans: bool = os.getenv('CALIBRATE_FANS', 'false') == 'true'
    enable_debug: bool = os.getenv('ENABLE_DEBUG_OUTPUT', 'false').lower() == 'true'
    enable_dynamic_updates: bool = os.getenv('ENABLE_DYNAMIC_UPDATES', 'true').lower() == 'true'
    junction_offset: int = int(os.getenv('JUNCTION_OFFSET', '15'))


class DellServer:
    def __init__(self, config: ServerConfig):
        self.config = config
        self.console = Console()
        self.model, self.manufacturer = self._get_server_info()
        self.is_gen14_or_newer = self._check_server_generation()
        self.current_profile = "Initializing..."
        self.current_fan_speeds = []
        self.fan_speed_ranges = {
            'min': self.config.fan_rpm_min,
            'max': self.config.fan_rpm_max,
        }

        # make it optional if you already know your min/max
        if self.config.calibrate_fans:
            self.calibrate_fans()

    def _run_ipmitool(self, *args) -> str:
        cmd = ['ipmitool']

        if self.config.idrac_host == 'local':
            cmd.extend(['-I', 'open'])
        else:
            cmd.extend(['-I', 'lanplus',
                       '-H', self.config.idrac_host,
                       '-U', self.config.idrac_username,
                       '-P', self.config.idrac_password])

        cmd.extend(args)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            self.console.print(f"[red]IPMI command failed: {e.stderr}[/red]")
            return ""

    def _get_server_info(self) -> tuple[str, str]:
        try:
            fru_info = self._run_ipmitool('fru')
            manufacturer = "Unknown Manufacturer"
            model = "Unknown Model"

            for line in fru_info.splitlines():
                if 'Board Mfg' in line:
                    manufacturer = line.split(':', 1)[1].strip()
                elif 'Board Product' in line:
                    model = line.split(':', 1)[1].strip()

            return model, manufacturer
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not get server info: {e}[/yellow]")
            return "Unknown Model", "Unknown Manufacturer"

    def _check_server_generation(self) -> bool:
        pattern = r'.*[RT]\s?[0-9][4-9]0.*'
        return bool(re.match(pattern, self.model))

    def get_temperatures(self) -> dict:
        """
        Get temperature readings from IPMI.
        Note: CPU temperatures are package temperatures, not junction temperatures.
        Junction temperature is typically 10-20°C higher than package temperature.
        """
        temps = {
            'inlet': None,
            'cpu1': None,
            'cpu2': None,
            'exhaust': None
        }

        try:
            raw_data = self._run_ipmitool('sdr', 'type', 'temperature')
            temp_data = [line for line in raw_data.splitlines() if 'degrees' in line]

            # Parse CPU temperatures (lines containing '3.')
            cpu_data = [line for line in temp_data if '3.' in line]
            cpu_temps = []
            for line in cpu_data:
                temp_match = re.search(r'(\d{2})\s+degrees', line)
                if temp_match:
                    cpu_temps.append(int(temp_match.group(1)))

            if len(cpu_temps) >= 1:
                temps['cpu1'] = cpu_temps[0]
            if len(cpu_temps) >= 2:
                temps['cpu2'] = cpu_temps[1]

            for line in temp_data:
                if 'inlet' in line.lower():
                    temp_match = re.search(r'(\d{2})\s+degrees', line)
                    if temp_match:
                        temps['inlet'] = int(temp_match.group(1))
                elif 'exhaust' in line.lower():
                    temp_match = re.search(r'(\d{2})\s+degrees', line)
                    if temp_match:
                        temps['exhaust'] = int(temp_match.group(1))

            if self.config.enable_debug:
                self.console.print("[dim]Debug: Raw temperature data:[/dim]")
                for line in temp_data:
                    self.console.print(f"[dim]{line}[/dim]")

                if temps['cpu1']:
                    est_tj1 = temps['cpu1'] + 15  # Estimate Tj as 15°C higher than package temp
                    self.console.print(f"[dim]Debug: CPU1 estimated junction temperature: {est_tj1}°C[/dim]")
                if temps['cpu2']:
                    est_tj2 = temps['cpu2'] + 15  # Estimate Tj as 15°C higher than package temp
                    self.console.print(f"[dim]Debug: CPU2 estimated junction temperature: {est_tj2}°C[/dim]")

        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not get temperature readings: {e}[/yellow]")

        return temps

    def use_automatic_cooling(self, enable: bool):
        self._run_ipmitool('raw', '0x30', '0x30', '0x01', '0x01' if enable else '0x00')

    def set_fan_speed(self, speed: int):
        try:
            self.use_automatic_cooling(False)

            self._run_ipmitool('raw', '0x30', '0x30', '0x02', '0xff', format(speed, '02x'))

            self.current_profile = f"User {speed}%"
        except Exception as e:
            self.console.print(f"[red]Error setting fan speed: {e}[/red]")

    def set_dell_profile(self):
        try:
            self.use_automatic_cooling(True)
            self.current_profile = "Dell"
        except Exception as e:
            self.console.print(f"[red]Error setting Dell profile: {e}[/red]")

    def manage_pcie_cooling(self, enable: bool):
        if not self.is_gen14_or_newer:
            try:
                self._run_ipmitool(
                    'raw',
                    '0x30',
                    '0xce',
                    '0x00',
                    '0x16',
                    '0x05',
                    '0x00',
                    '0x00',
                    '0x00',
                    '0x05',
                    '0x00',
                    '0x00' if enable else '0x01',
                    '0x00',
                    '0x00'
                )
            except Exception as e:
                self.console.print(f"[red]Error managing PCIe cooling: {e}[/red]")

    def get_fan_speeds(self) -> dict:
        try:
            fan_data = self._run_ipmitool('sdr', 'type', 'fan')
            fan_speeds = {}
            for line in fan_data.splitlines():
                if 'RPM' in line and 'Fan Redundancy' not in line:
                    fan_match = re.match(r'Fan(\d+) RPM\s+\|\s+\w+\s+\|\s+\w+\s+\|\s+[\d.]+\s+\|\s+(\d+)', line)
                    if fan_match:
                        fan_num = int(fan_match.group(1))
                        speed = int(fan_match.group(2))
                        fan_speeds[fan_num] = speed

            if not fan_speeds and self.config.enable_debug:
                self.console.print("[yellow]Debug: No fan speeds found in output:[/yellow]")
                self.console.print(f"[dim]{fan_data}[/dim]")

            self.current_fan_speeds = fan_speeds
            return fan_speeds
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not get fan speeds: {e}[/yellow]")
            return {}

    def calibrate_fans(self):
        """Calibrate fans by testing min and max speeds"""
        self.console.print("[yellow]Starting fan calibration...[/yellow]")

        def get_stable_reading(wait_time=20):
            self.console.print(f"[dim]Waiting {wait_time}s for fans to stabilize...[/dim]")
            time.sleep(wait_time)  # Wait for fans to stabilize

            readings = []
            self.console.print("[dim]Taking 3 readings with 1s intervals...[/dim]")

            for i in range(3):  # Take 3 readings
                current_speeds = self.get_fan_speeds()
                if current_speeds and 1 in current_speeds:
                    fan1_speed = current_speeds[1]
                    self.console.print(f"[dim]Reading {i+1}: Fan1 = {fan1_speed} RPM[/dim]")
                    readings.append(fan1_speed)
                else:
                    self.console.print("[dim]Warning: Could not read Fan1 speed[/dim]")
                time.sleep(1)

            # Check stability - allow for small variations (within 5%)
            if len(readings) == 3:
                avg_reading = sum(readings) / len(readings)
                is_stable = all(abs(r - avg_reading) / avg_reading < 0.05 for r in readings)

                if is_stable:
                    self.console.print(f"[dim]Readings are stable (average: {int(avg_reading)} RPM)[/dim]")
                    return int(avg_reading)
                else:
                    self.console.print("[dim]Readings are not stable:[/dim]")
                    for i, reading in enumerate(readings):
                        self.console.print(f"[dim]  Reading {i+1}: {reading} RPM[/dim]")
                    return None
            else:
                self.console.print("[dim]Not enough valid readings[/dim]")
                return None

        try:
            # Test minimum speed (0%)
            self.console.print("\n[yellow]Testing minimum fan speed...[/yellow]")
            self.console.print("[dim]Setting fan speed to 0%...[/dim]")
            self.set_fan_speed(0)
            min_reading = get_stable_reading()
            if min_reading is None:
                raise Exception("Failed to get stable minimum fan speed readings")
            self.console.print(f"[dim]Minimum reading acquired: {min_reading} RPM[/dim]")

            # Test maximum speed (100%)
            self.console.print("\n[yellow]Testing maximum fan speed...[/yellow]")
            self.console.print("[dim]Setting fan speed to 100%...[/dim]")
            self.set_fan_speed(100)
            max_reading = get_stable_reading()
            if max_reading is None:
                raise Exception("Failed to get stable maximum fan speed readings")
            self.console.print(f"[dim]Maximum reading acquired: {max_reading} RPM[/dim]")

            self.fan_speed_ranges = {
                'min': min_reading,
                'max': max_reading
            }

            self.console.print("\n[green]Fan Calibration Results:[/green]")
            self.console.print(f"Fan range (based on Fan1): {min_reading} - {max_reading} RPM\n")

        except Exception as e:
            import traceback
            self.console.print(f"\n[red]Error during fan calibration: {str(e)}[/red]")
            self.console.print(f"[red]{traceback.format_exc()}[/red]")
            self.fan_speed_ranges = {
                'min': self.config.fan_rpm_min,
                'max': self.config.fan_rpm_max,
            }
            self.console.print("[yellow]Using default fan speed ranges due to calibration failure[/yellow]")

        finally:
            self.console.print("\n[yellow]Restoring original fan speed...[/yellow]")
            self.set_fan_speed(self.config.fan_speed)
            self.console.print("[green]Fan calibration complete.[/green]")

    def get_fan_percentage(self, rpm: int) -> int:
        """Convert RPM to percentage based on calibrated range"""
        min_rpm = self.fan_speed_ranges['min']
        max_rpm = self.fan_speed_ranges['max']

        if max_rpm == min_rpm:
            return 0

        percentage = ((rpm - min_rpm) / (max_rpm - min_rpm)) * 100
        return max(0, min(100, round(percentage)))

    def create_table(self, temps: dict) -> Table:
        table = Table(title="Dell iDRAC Fan Controller Status")

        table.add_column("Time", justify="center")
        table.add_column("Inlet Temp", justify="right")
        table.add_column("CPU1 Temp", justify="right")
        table.add_column("CPU2 Temp", justify="right")
        table.add_column("Exhaust Temp", justify="right")
        table.add_column("Fan Profile", justify="left")
        table.add_column("Fan Speeds", justify="right")

        def temp_color(temp: Optional[float]) -> Text:
            if temp is None:
                return Text("-", style="dim")
            temp_text = f"{temp}°C"
            if temp >= self.config.cpu_temp_threshold:
                return Text(temp_text, style="bold red")
            elif temp >= self.config.cpu_temp_threshold * 0.9:
                return Text(temp_text, style="bold yellow")
            return Text(temp_text, style="green")

        fan_speeds = self.get_fan_speeds()

        if fan_speeds:
            speeds = []
            for fan_num, rpm in sorted(fan_speeds.items()):
                percentage = self.get_fan_percentage(rpm)
                speeds.append(f"Fan{fan_num}: {rpm} RPM ({percentage}%)")
            fan_text = "\n".join(speeds)
        else:
            fan_text = "No data"

        table.add_row(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            temp_color(temps['inlet']),
            temp_color(temps['cpu1']),
            temp_color(temps['cpu2']),
            temp_color(temps['exhaust']),
            self.current_profile,
            fan_text
        )

        return table

def main():
    config = ServerConfig()
    server = DellServer(config)

    def graceful_exit(signum, frame):
        server.console.print("\n[yellow]Shutting down, restoring Dell profile[/yellow]")
        server.set_dell_profile()
        if not config.keep_pcie_state:
            server.manage_pcie_cooling(True)
        sys.exit(0)

    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    if config.disable_pcie_cooling:
        server.manage_pcie_cooling(False)

    with Live(
        server.create_table(server.get_temperatures()),
        refresh_per_second=1,
        console=server.console
    ) as live:
        while True:
            temps = server.get_temperatures()
            fan_speeds = server.get_fan_speeds()
            adjusted_threshold = config.cpu_temp_threshold - config.junction_offset

            if config.enable_dynamic_updates and (
                (temps['cpu1'] and temps['cpu1'] > adjusted_threshold) or \
                (temps['cpu2'] and temps['cpu2'] > adjusted_threshold)
            ):
                server.set_fan_speed(config.fan_speed_max)
            else:
                server.set_fan_speed(config.fan_speed)

            live.update(server.create_table(temps))
            time.sleep(config.check_interval)

if __name__ == "__main__":
    main()