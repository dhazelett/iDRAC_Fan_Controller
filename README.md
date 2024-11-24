<div id="top"></div>
This version of the container uses python to control ipmi.


# Dell iDRAC fan controller Docker image
Download Docker image from :
- [Docker Hub](https://hub.docker.com/r/dhazelett/idrac_fan_controller)
- [GitHub Containers Repository](https://github.com/dhazelett/iDRAC_Fan_Controller/pkgs/container/idrac_fan_controller)

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li><a href="#container-console-log-example">Container console log example</a></li>
    <li><a href="#supported-architectures">Supported architectures</a></li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#troubleshooting">Troubleshooting</a></li>
    <li><a href="#contributing">Contributing</a></li>
  </ol>
</details>

## Container console log example

![image](https://github.com/user-attachments/assets/beba33c0-c1db-4216-a181-48fe0492a79a)

## Prerequisites
### iDRAC version

This Docker container only works on Dell PowerEdge servers that support IPMI commands, i.e. < iDRAC 9 firmware 3.30.30.30.

### To access iDRAC over LAN (not needed in "local" mode) :

1. Log into your iDRAC web console

![001](https://github.com/user-attachments/assets/9855dcd2-5e27-4df8-8760-0e863f76c29a)

2. In the left side menu, expand "iDRAC settings", click "Network".

3. Check the "Enable IPMI over LAN" checkbox then click "Apply" button.

![002](https://github.com/user-attachments/assets/b02fc640-42a3-484c-8e55-9d4714d986dc)

4. Test access to IPMI over LAN running the following commands :
```bash
apt -y install ipmitool
ipmitool -I lanplus \
  -H <iDRAC IP address> \
  -U <iDRAC username> \
  -P <iDRAC password> \
  sdr elist all
```

<p align="right">(<a href="#top">back to top</a>)</p>

## Supported architectures

This Docker container is currently built and available for the following CPU architectures:
- AMD64
- ARM64

<p align="right">(<a href="#top">back to top</a>)</p>

## Usage
### Available Environment Variables

| Environment Variable | Default Value | Description |
|---------------------|---------------|-------------|
| `IDRAC_HOST` | `local` | iDRAC host address. Use `local` for direct IPMI access or an IP address for network access |
| `IDRAC_USERNAME` | `root` | iDRAC username for authentication when using network access |
| `IDRAC_PASSWORD` | `calvin` | iDRAC password for authentication when using network access |
| `FAN_SPEED` | `25` | Target fan speed percentage when using custom profile (1-100) |
| `FAN_SPEED_MAX` | `100` | Maximum fan speed percentage to use when CPU temperature exceeds threshold |
| `CPU_TEMPERATURE_THRESHOLD` | `60` | Temperature threshold in °C that triggers higher fan speeds |
| `CHECK_INTERVAL` | `15` | Time in seconds between ipmi probes |
| `FAN_RPM_MIN` | `2500` | Minimum expected RPM for fans |
| `FAN_RPM_MAX` | `12000` | Maximum expected RPM for fans |
| `DISABLE_THIRD_PARTY_PCIE_CARD_DELL_DEFAULT_COOLING_RESPONSE` | `false` | Whether to disable Dell's default cooling response for third-party PCIe cards (Gen 13 and older only) |
| `KEEP_THIRD_PARTY_PCIE_CARD_COOLING_RESPONSE_STATE_ON_EXIT` | `false` | Whether to maintain the PCIe cooling response state when process exits |
| `CALIBRATE_FANS` | `false` | Whether to perform fan calibration at startup to determine actual min/max RPM ranges |
| `ENABLE_DEBUG_OUTPUT` | `false` | Enable additional debug output for troubleshooting |
| `ENABLE_DYNAMIC_UPDATES` | `true` | You can set this to false if you just want your system to always run at x% while the container is running. |
| `JUNCTION_OFFSET` | `15` | Temperature difference (°C) between CPU package and junction temperatures |

> note that the min and max fan rpm settings are just for calculating your current %


### Example Usage:

```yaml
environment:
  - IDRAC_HOST=192.168.1.100
  - IDRAC_USERNAME=root
  - IDRAC_PASSWORD=your_password
  - FAN_SPEED=20
  - CPU_TEMPERATURE_THRESHOLD=60
  - CHECK_INTERVAL=30
```

#### `docker run`
```bash
docker run -d \
  --device /dev/ipmi0:/dev/ipmi0:rw \
  --name idrac-controller \
  -e FAN_SPEED=5 \
  -e CPU_TEMPERATURE_THRESHOLD=50 \
  dhazelett/idrac-controller:latest
```

#### `docker-compose`
```yml
services:
    idrac-controller:
        image: dhazelett/idrac-controller:latest
        container_name: idrac-controller
        environment:
            - FAN_SPEED=5
            - CPU_TEMPERATURE_THRESHOLD=50
        devices:
            - /dev/ipmi0:/dev/ipmi0:rw
```

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- TROUBLESHOOTING -->
## Troubleshooting

If your server frequently switches back to the default Dell fan mode:
1. Check `Tcase` (case temperature) of your CPU on Intel Ark website and then set `CPU_TEMPERATURE_THRESHOLD` to a slightly lower value. Example with my CPUs ([Intel Xeon E5-2630L v2](https://www.intel.com/content/www/us/en/products/sku/75791/intel-xeon-processor-e52630l-v2-15m-cache-2-40-ghz/specifications.html)) : Tcase = 63°C, I set `CPU_TEMPERATURE_THRESHOLD` to 60(°C).
2. If it's already good, adapt your `FAN_SPEED` value to increase the airflow and thus further decrease the temperature of your CPU(s)
3. If neither increasing the fan speed nor increasing the threshold solves your problem, then it may be time to replace your thermal paste

<p align="right">(<a href="#top">back to top</a>)</p>

<!-- CONTRIBUTING -->
## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

<p align="right">(<a href="#top">back to top</a>)</p>
