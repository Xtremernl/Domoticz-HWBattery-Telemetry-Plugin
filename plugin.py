## HomeWizard Battery Plugin
##
## Author:         etmmvdp & XtremerNL
## Version:        0.0.4   # verhoogd ivm polling fix
## Last modified:  09-04-2025
##
"""
<plugin key="HomeWizardBattery" name="HomeWizard Battery" author="etmmvdp" version="0.0.4" externallink="https://www.homewizard.com/nl/plug-in-battery">
    <description>
        <h2>HomeWizard Battery Plugin</h2><br/>
        This plugin provides several devices for the HomeWizard Battery.<br/>
        Notes:
        <ul style="list-style-type:square">
            <li>The token needs to be created using the activate_user.py script. See the readme for details.</li>
            <li>The Extra P1 Device option, when set to yes, adds an additional device to provide for a combined
                overview of total imported and exported meter values, as wel as current import and export power usage.<br/>
                It is a bit of a hacky solution to use the P1 device, but it nicely provides for these details combined into one device.</li>
        </ul>
    </description>
    <params>
        <param field="Address" label="IP Address" width="250px" required="true" default="127.0.0.1" />
        <param field="Port" label="Port" width="250px" required="true" default="443" />
        <param field="Mode2" label="Token" width="250px" required="true" default=""/>
        <param field="Mode1" label="Data interval" width="250px">
            <options>
                <option label="2 seconds" value="2"/>
                <option label="5 seconds" value="5"/>
                <option label="10 seconds" value="10"/>
                <option label="20 seconds" value="20"/>
                <option label="30 seconds" value="30"/>
                <option label="1 minute" value="60" default="true"/>
                <option label="2 minutes" value="120"/>
                <option label="3 minutes" value="180"/>
                <option label="4 minutes" value="240"/>
                <option label="5 minutes" value="300"/>
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
import urllib
import urllib.request

try:
    import Domoticz
except ImportError:
    from mock_domoticz import Domoticz, Parameters, Devices

class BasePlugin:
    debug = False

    # Plugin variables
    pluginInterval = 1      # WAS 10 → heartbeat nu elke seconde
    dataInterval = 60
    dataIntervalCount = 0
    use_p1_device = False

    # Homewizard battery variables
    energy_import_kwh = -1
    energy_export_kwh = -1
    power_w = -1
    voltage_v = -1
    current_a = -1
    frequency_hz = -1
    state_of_charge_pct = -1
    cycles = -1

    efficiency = -1

    # Device ID's
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

        # WAS: 10 <= Mode1 <= 300
        if 2 <= int(Parameters["Mode1"]) <= 300:
            self.dataInterval = int(Parameters["Mode1"])
        else:
            self.dataInterval = 60

        Domoticz.Heartbeat(self.pluginInterval)
        return True

    def onConnect(self, Status, Description):
        return True

    def onMessage(self, Data, Status, Extra):
        try:
            Domoticz.Debug(f"Read battery measurement from input {Data}")
            self.energy_import_kwh = int(Data.get('energy_import_kwh', 0) * 1000)
            self.energy_export_kwh = int(Data.get('energy_export_kwh', 0) * 1000)
            self.power_w = int(Data.get('power_w', 0))
            self.voltage_v = int(Data.get('voltage_v', 0))
            self.current_a = float(Data.get('current_a', 0))
            self.frequency_hz = float(Data.get('frequency_hz', 0))
            self.state_of_charge_pct = int(Data.get('state_of_charge_pct', 0))
            self.cycles = int(Data.get('cycles', 0))

            self.efficiency = int(100.0 * self.energy_export_kwh / self.energy_import_kwh) if self.energy_import_kwh != 0 else 0

            if self.use_p1_device:
                try:
                    if self.total_power_id not in Devices:
                        Domoticz.Device(Name="Total Power", Unit=self.total_power_id, Type=250, Subtype=1).Create()

                    import_power_w = self.power_w if self.power_w >= 0 else 0
                    export_power_w = -1 * self.power_w if self.power_w < 0 else 0

                    _update_device(self.total_power_id, 0, f"{self.energy_import_kwh};0;{self.energy_export_kwh};0;{import_power_w};{export_power_w}", True)
                except Exception as e:
                    Domoticz.Error(f"Failed to update device id {self.total_power_id}: {e}")

            try:
                if self.power_id not in Devices:
                    Domoticz.Device(Name="Active Power", Unit=self.power_id, Type=243, Subtype=29, Switchtype=4).Create()

                net_energy_kwh = self.energy_import_kwh - self.energy_export_kwh
                _update_device(self.power_id, 0, f"{self.power_w};{net_energy_kwh}", True)
            except Exception as e:
                Domoticz.Error(f"Failed to update device id {self.power_id}: {e}")

            try:
                if self.voltage_id not in Devices:
                    Domoticz.Device(Name="Active Voltage", Unit=self.voltage_id, Type=243, Subtype=8).Create()

                _update_device(self.voltage_id, 0, f"{self.voltage_v};0")
            except Exception as e:
                Domoticz.Error(f"Failed to update device id {self.voltage_id}: {e}")

            try:
                if self.current_id not in Devices:
                    Domoticz.Device(Name="Active Current", Unit=self.current_id, Type=243, Subtype=23).Create()

                _update_device(self.current_id, 0, f"{self.current_a:.3f};0", True)
            except Exception as e:
                Domoticz.Error(f"Failed to update device id {self.current_id}: {e}")

            try:
                if self.frequency_id not in Devices:
                    Domoticz.Device(Name="Frequency", Unit=self.frequency_id, Type=243, Subtype=31, Options={"Custom": "1;Hz"}).Create()

                _update_device(self.frequency_id, 0, f"{self.frequency_hz:.1f}")
            except Exception as e:
                Domoticz.Error(f"Failed to update device id {self.frequency_id}: {e}")

            try:
                if self.state_of_charge_id not in Devices:
                    Domoticz.Device(Name="SOC", Unit=self.state_of_charge_id, Type=243, Subtype=6).Create()

                _update_device(self.state_of_charge_id, 0, f"{self.state_of_charge_pct}")
            except Exception as e:
                Domoticz.Error(f"Failed to update device id {self.state_of_charge_id}: {e}")

            try:
                if self.cycles_id not in Devices:
                    Domoticz.Device(Name="Cycles", Unit=self.cycles_id, Type=243, Subtype=31, Options={"Custom": "1;cycles"}).Create()

                _update_device(self.cycles_id, 0, f"{self.cycles}")
            except Exception as e:
                Domoticz.Error(f"Failed to update device id {self.cycles_id}: {e}")

            try:
                if self.efficiency_id not in Devices:
                    Domoticz.Device(Name="RTE", Unit=self.efficiency_id, Type=243, Subtype=6).Create()

                _update_device(self.efficiency_id, 0, f"{self.efficiency}", always_update=True)
            except Exception as e:
                Domoticz.Error(f"Failed to update device id {self.efficiency_id}: {e}")

        except Exception as e:
            Domoticz.Error(f"Error reading battery measurement from input {Data}: {e}")
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
        return True

    def _readMeasurement(self):
        url = f"https://{Parameters['Address']}:{Parameters['Port']}/api/measurement"
        headers = {
            "Authorization": f"Bearer {Parameters['Mode2']}",
            "X-Api-Version": 2
        }

        # WAS: timeout = self.pluginInterval / 2  → veroorzaakte handshake timeouts
        timeout = 5   # vaste veilige timeout

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                api_json = json.loads(response.read().decode("utf-8"))
                self.onMessage(api_json, "200", "")
        except Exception as e:
            Domoticz.Error(f"Failed to communicate with battery at {url}: {e}")

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

def _dump_config_to_log():
    Domoticz.Debug(f"parameters:")
    for key, value in Parameters.items():
        Domoticz.Debug(f"\t'{key}': '{value}'")

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
