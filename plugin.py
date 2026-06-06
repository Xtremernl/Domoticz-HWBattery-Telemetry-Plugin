## HomeWizard Battery Telemetry Plugin
##
## Author:         Xtremernl based on etmmvdp
## Version:        0.2.0
## Last modified:  2026-06-06
##
"""
<plugin key="HomeWizardBatteryTelemetry" name="HomeWizard Battery Telemetry" author="Xtremernl" version="0.2.0" externallink="https://github.com/Xtremernl/HW-Battery-Telemetry-plugin/">
    <description>
        <h2>HomeWizard Battery Telemetry Plugin</h2><br/>
        This plugin provides several devices for the HomeWizard Plug-In Battery.<br/>
        Notes:
        <ul style="list-style-type:square">
            <li>The token needs to be created using the activate_user.py script. See the readme for details.</li>
            <li>The Extra P1 Device option, when set to yes, adds an additional device to provide for a combined
                overview of total imported and exported meter values, as well as current import and export power usage.<br/>
                It uses the Domoticz P1 Smart Meter device format.</li>
        </ul>
    </description>
    <params>
        <param field="Address" label="IP Address (Battery)" width="250px" required="true" default="127.0.0.1" />
        <param field="Port" label="Port" width="100px" required="true" default="443" />
        <param field="Mode2" label="Token" width="250px" required="true" default=""/>
        <param field="Mode1" label="Data interval" width="250px">
            <options>
                <option label="2 seconds" value="2" default="true"/>
                <option label="5 seconds" value="5"/>
                <option label="10 seconds" value="10"/>
                <option label="20 seconds" value="20"/>
                <option label="30 seconds" value="30"/>
            </options>
        </param>
        <param field="Mode3" label="Extra P1 Device" width="250px">
            <options>
                <option label="Yes" value="Yes"/>
                <option label="No" value="No" default="true"/>
            </options>
        </param>
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="true" />
            </options>
        </param>
    </params>
</plugin>
"""

import json
import ssl
import urllib.request

try:
    import Domoticz
except ImportError:
    from mock_domoticz import Domoticz, Parameters, Devices


class BasePlugin:
    # timing
    pluginInterval = 1
    dataInterval = 2
    dataIntervalCount = 0

    # flags
    use_p1_device = False

    # measurement fields (API v2 /api/measurement)
    energy_import_kwh = 0.0
    energy_export_kwh = 0.0
    power_w = 0.0
    voltage_v = 0.0
    current_a = 0.0
    frequency_hz = 0.0
    state_of_charge_pct = 0
    cycles = 0
    efficiency = 0

    # device IDs – gelijk aan originele plugin
    total_power_id = 150
    power_id = 153
    voltage_id = 154
    current_id = 155
    frequency_id = 156
    state_of_charge_id = 157
    cycles_id = 158
    efficiency_id = 159

    def onStart(self):
        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)
            _dump_config_to_log()

        self.use_p1_device = Parameters.get("Mode3", "") == "Yes"

        try:
            interval = int(Parameters["Mode1"])
            if interval in (2, 5, 10, 20, 30):
                self.dataInterval = interval
            else:
                self.dataInterval = 2
        except Exception:
            self.dataInterval = 2

        Domoticz.Log(f"HomeWizard Battery Telemetry started, data interval = {self.dataInterval}s")
        Domoticz.Heartbeat(self.pluginInterval)

    def onConnect(self, Status, Description):
        return True

    def onMessage(self, Data, Status, Extra):
        try:
            Domoticz.Debug(f"Raw measurement input: {Data}")

            # API v2 measurement fields
            self.energy_import_kwh = float(Data.get("energy_import_kwh", 0.0))
            self.energy_export_kwh = float(Data.get("energy_export_kwh", 0.0))
            self.power_w = float(Data.get("power_w", 0.0))
            self.voltage_v = float(Data.get("voltage_v", 0.0))
            self.current_a = float(Data.get("current_a", 0.0))
            self.frequency_hz = float(Data.get("frequency_hz", 0.0))
            self.state_of_charge_pct = int(Data.get("state_of_charge_pct", 0))
            self.cycles = int(Data.get("cycles", 0))

            if self.energy_import_kwh > 0:
                self.efficiency = int(100.0 * self.energy_export_kwh / self.energy_import_kwh)
            else:
                self.efficiency = 0

            Domoticz.Debug(
                f"Parsed: import={self.energy_import_kwh} kWh, "
                f"export={self.energy_export_kwh} kWh, power={self.power_w} W, "
                f"voltage={self.voltage_v} V, current={self.current_a} A, "
                f"freq={self.frequency_hz} Hz, soc={self.state_of_charge_pct} %, "
                f"cycles={self.cycles}, rte={self.efficiency} %"
            )

            if self.use_p1_device:
                self._update_total_power_device()

            self._update_power_device()
            self._update_voltage_device()
            self._update_current_device()
            self._update_frequency_device()
            self._update_soc_device()
            self._update_cycles_device()
            self._update_efficiency_device()

        except Exception as e:
            Domoticz.Error(f"Error processing measurement data {Data}: {e}")
        return True

    def onCommand(self, Unit, Command, Level, Hue):
        return True

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        return

    def onHeartbeat(self):
        self.dataIntervalCount += self.pluginInterval
        if self.dataIntervalCount >= self.dataInterval:
            self.dataIntervalCount = 0
            self._readMeasurement()
        return

    def onDisconnect(self):
        return

    def onStop(self):
        Domoticz.Log("HomeWizard Battery Telemetry stopped")
        return True

    # ---------- devices ----------

    def _update_total_power_device(self):
        """
        Extra P1 Device – exact volgens originele plugin:
        sValue = import_wh;0;export_wh;0;import_w;export_w
        """
        try:
            if self.total_power_id not in Devices:
                Domoticz.Device(
                    Name="Total Power",
                    Unit=self.total_power_id,
                    Type=250,
                    Subtype=1
                ).Create()

            # originele logica: kWh → Wh (×1000), integers
            import_wh = int(self.energy_import_kwh * 1000)
            export_wh = int(self.energy_export_kwh * 1000)

            if self.power_w >= 0:
                import_power_w = int(self.power_w)
                export_power_w = 0
            else:
                import_power_w = 0
                export_power_w = int(-self.power_w)

            sValue = f"{import_wh};0;{export_wh};0;{import_power_w};{export_power_w}"
            _update_device(self.total_power_id, 0, sValue, always_update=True)
        except Exception as e:
            Domoticz.Error(f"Failed to update Total Power device (Unit {self.total_power_id}): {e}")

    def _update_power_device(self):
        """
        Active Power – Type 243, Subtype 29, Switchtype 4.
        sValue = power_w;net_energy_kwh
        """
        try:
            if self.power_id not in Devices:
                Domoticz.Device(
                    Name="Active Power",
                    Unit=self.power_id,
                    Type=243,
                    Subtype=29,
                    Switchtype=4
                ).Create()

            net_energy_kwh = self.energy_import_kwh - self.energy_export_kwh
            sValue = f"{int(self.power_w)};{net_energy_kwh:.3f}"
            _update_device(self.power_id, 0, sValue, always_update=True)
        except Exception as e:
            Domoticz.Error(f"Failed to update Active Power device (Unit {self.power_id}): {e}")

    def _update_voltage_device(self):
        """
        Active Voltage – Type 243, Subtype 8.
        sValue = voltage_v;0
        """
        try:
            if self.voltage_id not in Devices:
                Domoticz.Device(
                    Name="Active Voltage",
                    Unit=self.voltage_id,
                    Type=243,
                    Subtype=8
                ).Create()

            sValue = f"{self.voltage_v:.1f};0"
            _update_device(self.voltage_id, 0, sValue)
        except Exception as e:
            Domoticz.Error(f"Failed to update Active Voltage device (Unit {self.voltage_id}): {e}")

    def _update_current_device(self):
        """
        Active Current – Type 243, Subtype 23.
        sValue = current_a;0
        """
        try:
            if self.current_id not in Devices:
                Domoticz.Device(
                    Name="Active Current",
                    Unit=self.current_id,
                    Type=243,
                    Subtype=23
                ).Create()

            sValue = f"{self.current_a:.3f};0"
            _update_device(self.current_id, 0, sValue, always_update=True)
        except Exception as e:
            Domoticz.Error(f"Failed to update Active Current device (Unit {self.current_id}): {e}")

    def _update_frequency_device(self):
        """
        Frequency – Type 243, Subtype 31 (Custom).
        Origineel: 1 decimaal.
        """
        try:
            if self.frequency_id not in Devices:
                Domoticz.Device(
                    Name="Frequency",
                    Unit=self.frequency_id,
                    Type=243,
                    Subtype=31,
                    Options={"Custom": "1;Hz"}
                ).Create()

            sValue = f"{self.frequency_hz:.1f}"
            _update_device(self.frequency_id, 0, sValue)
        except Exception as e:
            Domoticz.Error(f"Failed to update Frequency device (Unit {self.frequency_id}): {e}")

    def _update_soc_device(self):
        """
        SOC – Type 243, Subtype 6 (Percentage).
        """
        try:
            if self.state_of_charge_id not in Devices:
                Domoticz.Device(
                    Name="SOC",
                    Unit=self.state_of_charge_id,
                    Type=243,
                    Subtype=6
                ).Create()

            sValue = f"{self.state_of_charge_pct}"
            _update_device(self.state_of_charge_id, 0, sValue)
        except Exception as e:
            Domoticz.Error(f"Failed to update SOC device (Unit {self.state_of_charge_id}): {e}")

    def _update_cycles_device(self):
        """
        Cycles – Type 243, Subtype 31 (Custom).
        """
        try:
            if self.cycles_id not in Devices:
                Domoticz.Device(
                    Name="Cycles",
                    Unit=self.cycles_id,
                    Type=243,
                    Subtype=31,
                    Options={"Custom": "1;cycles"}
                ).Create()

            sValue = f"{self.cycles}"
            _update_device(self.cycles_id, 0, sValue)
        except Exception as e:
            Domoticz.Error(f"Failed to update Cycles device (Unit {self.cycles_id}): {e}")

    def _update_efficiency_device(self):
        """
        RTE – Type 243, Subtype 6 (Percentage).
        """
        try:
            if self.efficiency_id not in Devices:
                Domoticz.Device(
                    Name="RTE",
                    Unit=self.efficiency_id,
                    Type=243,
                    Subtype=6
                ).Create()

            sValue = f"{self.efficiency}"
            _update_device(self.efficiency_id, 0, sValue, always_update=True)
        except Exception as e:
            Domoticz.Error(f"Failed to update RTE device (Unit {self.efficiency_id}): {e}")

    # ---------- API call ----------

    def _readMeasurement(self):
        url = f"https://{Parameters['Address']}:{Parameters['Port']}/api/measurement"
        headers = {
            "Authorization": f"Bearer {Parameters['Mode2']}",
            "X-Api-Version": "2",
        }
        timeout = 5

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        try:
            Domoticz.Debug(f"Requesting measurement from {url} with timeout {timeout}s")
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                raw = response.read().decode("utf-8")
                api_json = json.loads(raw)
                Domoticz.Debug(f"Received measurement JSON: {api_json}")
                self.onMessage(api_json, "200", "")
        except Exception as e:
            Domoticz.Error(f"Failed to communicate with battery at {url}: {e}")


# ---------- Domoticz glue ----------

global _plugin
_plugin = BasePlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onConnect(Status, Description):
    _plugin.onConnect(Status, Description)


def onMessage(Data, Status, Extra):
    _plugin.onMessage(Data, Status, Extra)


def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)


def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)


def onDisconnect():
    _plugin.onDisconnect()


def onHeartbeat():
    _plugin.onHeartbeat()


# ---------- helpers ----------

def _dump_config_to_log():
    Domoticz.Debug("Parameters:")
    for key, value in Parameters.items():
        Domoticz.Debug(f"  '{key}': '{value}'")

    Domoticz.Debug(f"Device count: {len(Devices)}")
    for device in Devices:
        Domoticz.Debug(f"Device:           {device} - {Devices[device]}")
        Domoticz.Debug(f"Device ID:       '{Devices[device].ID}'")
        Domoticz.Debug(f"Device Name:     '{Devices[device].Name}'")
        Domoticz.Debug(f"Device nValue:    {Devices[device].nValue}")
        Domoticz.Debug(f"Device sValue:   '{Devices[device].sValue}'")
        Domoticz.Debug(f"Device LastLevel: {Devices[device].LastLevel}")


def _update_device(Unit, nValue, sValue, always_update=False, signal_level=12):
    if Unit in Devices:
        if Devices[Unit].nValue != nValue or Devices[Unit].sValue != sValue or always_update:
            Devices[Unit].Update(nValue=nValue, sValue=sValue, SignalLevel=signal_level)
