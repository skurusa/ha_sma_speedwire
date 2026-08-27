
import logging
import socket
import time
from struct import unpack_from
from time import monotonic

MY_SYSTEMID    = 0x00ED                # random number, has to be different from any device in local network
MY_SERIAL      = 0x23021922            # random number, has to be different from any device in local network
ANY_SYSTEMID   = 0xFFFF                # 0xFFFF is any susyid
ANY_SERIAL     = 0xFFFFFFFF            # 0xFFFFFFFF is any serialnumber
SMA_PKT_HEADER = "534D4100000402A000000001"
SMA_ESIGNATURE = "00106065"

# UDP_IPB = "239.12.255.254"
# MESSAGE = bytes.fromhex('534d4100000402a0ffffffff0000002000000000')

COMMAND_LIST = {
    # name,           [command,    first,      last      ]
    "login":          [0xFFFD040C, 0x00000007, 0x00000384],
    "logout":         [0xFFFD010E, 0xFFFFFFFF, 0x00000000],
    "info":           [0x58000200, 0x00821E00, 0x008220FF],
    "energy":         [0x54000200, 0x00260100, 0x002622FF],
    "power_ac_total": [0x51000200, 0x00263F00, 0x00263FFF],
    "power_ac_phases": [0x51000200, 0x00464000, 0x004642FF],
    "power_dc_strings": [0x53800200, 0x00251E00, 0x00251EFF],
    "voltage_current_ac": [0x51000200, 0x00464800, 0x004655FF],
    "voltage_current_dc": [0x53800200, 0x00451F00, 0x004521FF],
    "grid_frequency": [0x51000200, 0x00465700, 0x004657FF],
    "inverter_temperature": [0x52000200, 0x00237700, 0x002377FF],
    "device_status": [0x51800200, 0x00214800, 0x002148FF],
    "grid_relay_status": [0x51800200, 0x00416400, 0x004164FF],
}

# Extra measurements are intentionally polled less often than the three original
# entities.  This keeps a 10-second base interval useful without sending every
# diagnostic request to the inverter six times per minute.
FAST_DIAGNOSTIC_INTERVAL = 30
MEDIUM_DIAGNOSTIC_INTERVAL = 60
DIAGNOSTIC_FAILURE_LIMIT = 3
DIAGNOSTIC_RETRY_DELAY = 15 * 60

INVALID_U32_VALUES = {0xFFFFFFFF, 0x80000000, 0xFFFFFFEC, 0x00FFFFFE}

SMA_STATUS_TAGS = {
    35: "Error",
    51: "Closed",
    303: "Off",
    307: "OK",
    308: "On",
    309: "Operation",
    311: "Open",
    381: "Stop",
    455: "Warning",
    802: "Active",
    803: "Inactive",
    1295: "Standby",
    1392: "Errors",
    1393: "Waiting for PV voltage",
    1394: "Waiting for a valid AC grid",
    1395: "DC area",
    1396: "AC grid",
    1466: "Waiting",
    1467: "Starting",
    1468: "MPP search",
    1469: "Shutdown",
    1749: "Full stop",
    1779: "Disconnected",
    16777213: "Information not available",
}

REGISTER_SENSORS = {
    0x40464001: ("power_ac_l1", "int", 1),
    0x40464101: ("power_ac_l2", "int", 1),
    0x40464201: ("power_ac_l3", "int", 1),
    0x40251E01: ("power_dc_1", "uint", 1),
    0x40251E02: ("power_dc_2", "uint", 1),
    0x00464801: ("voltage_ac_l1", "uint", 100),
    0x00464901: ("voltage_ac_l2", "uint", 100),
    0x00464A01: ("voltage_ac_l3", "uint", 100),
    0x40465301: ("current_ac_l1", "uint", 1000),
    0x40465401: ("current_ac_l2", "uint", 1000),
    0x40465501: ("current_ac_l3", "uint", 1000),
    0x40451F01: ("voltage_dc_1", "uint", 100),
    0x40451F02: ("voltage_dc_2", "uint", 100),
    0x40452101: ("current_dc_1", "uint", 1000),
    0x40452102: ("current_dc_2", "uint", 1000),
    0x00465701: ("grid_frequency", "uint", 100),
    0x40237701: ("inverter_temperature", "int", 100),
    0x08214801: ("device_status", "status", 1),
    0x08416401: ("grid_relay_status", "status", 1),
}

COMMAND_SENSOR_KEYS = {
    "power_ac_phases": ("power_ac_l1", "power_ac_l2", "power_ac_l3"),
    "power_dc_strings": ("power_dc_1", "power_dc_2"),
    "voltage_current_ac": (
        "voltage_ac_l1",
        "voltage_ac_l2",
        "voltage_ac_l3",
        "current_ac_l1",
        "current_ac_l2",
        "current_ac_l3",
    ),
    "voltage_current_dc": (
        "voltage_dc_1",
        "voltage_dc_2",
        "current_dc_1",
        "current_dc_2",
    ),
    "grid_frequency": ("grid_frequency",),
    "inverter_temperature": ("inverter_temperature",),
    "device_status": ("device_status",),
    "grid_relay_status": ("grid_relay_status",),
}

FAST_DIAGNOSTIC_COMMANDS = ("power_ac_phases", "power_dc_strings")
MEDIUM_DIAGNOSTIC_COMMANDS = (
    "voltage_current_ac",
    "voltage_current_dc",
    "grid_frequency",
    "inverter_temperature",
    "device_status",
    "grid_relay_status",
)

SMA_INV_TYPE = {
    0000: "Unknown Inverter Type",
    9015: "SB 700",
    9016: "SB 700U",
    9017: "SB 1100",
    9018: "SB 1100U",
    9019: "SB 1100LV",
    9020: "SB 1700",
    9021: "SB 1900TLJ",
    9022: "SB 2100TL",
    9023: "SB 2500",
    9024: "SB 2800",
    9025: "SB 2800i",
    9026: "SB 3000",
    9027: "SB 3000US",
    9028: "SB 3300",
    9029: "SB 3300U",
    9030: "SB 3300TL",
    9031: "SB 3300TL HC",
    9032: "SB 3800",
    9033: "SB 3800U",
    9034: "SB 4000US",
    9035: "SB 4200TL",
    9036: "SB 4200TL HC",
    9037: "SB 5000TL",
    9038: "SB 5000TLW",
    9039: "SB 5000TL HC",
    9066: "SB 1200",
    9067: "STP 10000TL-10",
    9068: "STP 12000TL-10",
    9069: "STP 15000TL-10",
    9070: "STP 17000TL-10",
    9084: "WB 3600TL-20",
    9085: "WB 5000TL-20",
    9086: "SB 3800US-10",
    9098: "STP 5000TL-20",
    9099: "STP 6000TL-20",
    9100: "STP 7000TL-20",
    9101: "STP 8000TL-10",
    9102: "STP 9000TL-20",
    9103: "STP 8000TL-20",
    9104: "SB 3000TL-JP-21",
    9105: "SB 3500TL-JP-21",
    9106: "SB 4000TL-JP-21",
    9107: "SB 4500TL-JP-21",
    9108: "SCSMC",
    9109: "SB 1600TL-10",
    9131: "STP 20000TL-10",
    9139: "STP 20000TLHE-10",
    9140: "STP 15000TLHE-10",
    9157: "Sunny Island 2012",
    9158: "Sunny Island 2224",
    9159: "Sunny Island 5048",
    9160: "SB 3600TL-20",
    9168: "SC630HE-11",
    9169: "SC500HE-11",
    9170: "SC400HE-11",
    9171: "WB 3000TL-21",
    9172: "WB 3600TL-21",
    9173: "WB 4000TL-21",
    9174: "WB 5000TL-21",
    9175: "SC 250",
    9176: "SMA Meteo Station",
    9177: "SB 240-10",
    9171: "WB 3000TL-21",
    9172: "WB 3600TL-21",
    9173: "WB 4000TL-21",
    9174: "WB 5000TL-21",
    9179: "Multigate-10",
    9180: "Multigate-US-10",
    9181: "STP 20000TLEE-10",
    9182: "STP 15000TLEE-10",
    9183: "SB 2000TLST-21",
    9184: "SB 2500TLST-21",
    9185: "SB 3000TLST-21",
    9186: "WB 2000TLST-21",
    9187: "WB 2500TLST-21",
    9188: "WB 3000TLST-21",
    9189: "WTP 5000TL-20",
    9190: "WTP 6000TL-20",
    9191: "WTP 7000TL-20",
    9192: "WTP 8000TL-20",
    9193: "WTP 9000TL-20",
    9254: "Sunny Island 3324",
    9255: "Sunny Island 4.0M",
    9256: "Sunny Island 4248",
    9257: "Sunny Island 4248U",
    9258: "Sunny Island 4500",
    9259: "Sunny Island 4548U",
    9260: "Sunny Island 5.4M",
    9261: "Sunny Island 5048U",
    9262: "Sunny Island 6048U",
    9278: "Sunny Island 3.0M",
    9279: "Sunny Island 4.4M",
    9281: "STP 10000TL-20",
    9282: "STP 11000TL-20",
    9283: "STP 12000TL-20",
    9284: "STP 20000TL-30",
    9285: "STP 25000TL-30",
    9301: "SB1.5-1VL-40",
    9302: "SB2.5-1VL-40",
    9303: "SB2.0-1VL-40",
    9304: "SB5.0-1SP-US-40",
    9305: "SB6.0-1SP-US-40",
    9306: "SB8.0-1SP-US-40",
    9307: "Energy Meter",
    9313: "SB50.0-3SP-40",
    9319: "SB3.0-1AV-40 (Sunny Boy 3.0 AV-40)",
    9320: "SB3.6-1AV-40 (Sunny Boy 3.6 AV-40)",
    9321: "SB4.0-1AV-40 (Sunny Boy 4.0 AV-40)",
    9322: "SB5.0-1AV-40 (Sunny Boy 5.0 AV-40)",
    9324: "SBS1.5-1VL-10 (Sunny Boy Storage 1.5)",
    9325: "SBS2.0-1VL-10 (Sunny Boy Storage 2.0)",
    9326: "SBS2.5-1VL-10 (Sunny Boy Storage 2.5)",
    9327: "SMA Energy Meter",
    9331: "SI 3.0M-12 (Sunny Island 3.0M)",
    9332: "SI 4.4M-12 (Sunny Island 4.4M)",
    9333: "SI 6.0H-12 (Sunny Island 6.0H)",
    9334: "SI 8.0H-12 (Sunny Island 8.0H)",
    9335: "SMA Com Gateway",
    9336: "STP 15000TL-30",
    9337: "STP 17000TL-30",
    9344: "STP4.0-3AV-40 (Sunny Tripower 4.0)",
    9345: "STP5.0-3AV-40 (Sunny Tripower 5.0)",
    9346: "STP6.0-3AV-40 (Sunny Tripower 6.0)",
    9347: "STP8.0-3AV-40 (Sunny Tripower 8.0)",
    9348: "STP10.0-3AV-40 (Sunny Tripower 10.0)",
    9356: "SBS3.7-1VL-10 (Sunny Boy Storage 3.7)",
    9358: "SBS5.0-10 (Sunny Boy Storage 5.0)",
    9359: "SBS6.0-10 (Sunny Boy Storage 6.0)",
    9366: "STP3.0-3AV-40 (Sunny Tripower 3.0)",
    9401: "SB3.0-1AV-41 (Sunny Boy 3.0 AV-41)",
    9402: "SB3.6-1AV-41 (Sunny Boy 3.6 AV-41)",
    9403: "SB4.0-1AV-41 (Sunny Boy 4.0 AV-41)",
    9404: "SB5.0-1AV-41 (Sunny Boy 5.0 AV-41)",
    9405: "SB6.0-1AV-41 (Sunny Boy 6.0 AV-41)",
}

SMA_INV_CLASS = {
    8000: "Any Device",
    8001: "Solar Inverter",
    8002: "Wind Turbine Inverter",
    8007: "Batterie Inverter",
    8033: "Consumer",
    8064: "Sensor System in General",
    8065: "Electricity meter",
    8128: "Communication product",
}

class smaError(Exception):
    pass

class SMA_SPEEDWIRE:
    def __init__(self, host, password="0000", logger=None):
        self.host = host
        self.port = 9522
        self.password = password
        self.pkt_id = 0
        self.my_id = MY_SYSTEMID.to_bytes(2, byteorder='little') + MY_SERIAL.to_bytes(4, byteorder='little')
        self.target_id = ANY_SYSTEMID.to_bytes(2, byteorder='little') + ANY_SERIAL.to_bytes(4, byteorder='little')
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(3.0)
        self.retry = 2
        self.fast_diagnostic_interval = FAST_DIAGNOSTIC_INTERVAL
        self.medium_diagnostic_interval = MEDIUM_DIAGNOSTIC_INTERVAL
        self._diagnostic_next_due = {
            command: 0.0 for command in COMMAND_SENSOR_KEYS
        }
        self._diagnostic_failures = {command: 0 for command in COMMAND_SENSOR_KEYS}
        self._diagnostic_retry_after = {
            command: 0.0 for command in COMMAND_SENSOR_KEYS
        }

        self.serial = None
        self.inv_class = None
        self.inv_type = None
        self.sensors = {
            "energy_total": {
                "name": "Energy Production Total",
                "value": None,
                "unit": "kWh",
            },
            "energy_today": {
                "name": "Energy Production Today",
                "value": None,
                "unit": "kWh",
            },
            "power_ac_total": {
                "name": "Power Production Now",
                "value": None,
                "unit": "W",
            },
            "power_ac_l1": {"name": "AC Power L1", "value": None, "unit": "W"},
            "power_ac_l2": {"name": "AC Power L2", "value": None, "unit": "W"},
            "power_ac_l3": {"name": "AC Power L3", "value": None, "unit": "W"},
            "voltage_ac_l1": {"name": "AC Voltage L1", "value": None, "unit": "V"},
            "voltage_ac_l2": {"name": "AC Voltage L2", "value": None, "unit": "V"},
            "voltage_ac_l3": {"name": "AC Voltage L3", "value": None, "unit": "V"},
            "current_ac_l1": {"name": "AC Current L1", "value": None, "unit": "A"},
            "current_ac_l2": {"name": "AC Current L2", "value": None, "unit": "A"},
            "current_ac_l3": {"name": "AC Current L3", "value": None, "unit": "A"},
            "power_dc_1": {"name": "DC Power String 1", "value": None, "unit": "W"},
            "power_dc_2": {"name": "DC Power String 2", "value": None, "unit": "W"},
            "voltage_dc_1": {"name": "DC Voltage String 1", "value": None, "unit": "V"},
            "voltage_dc_2": {"name": "DC Voltage String 2", "value": None, "unit": "V"},
            "current_dc_1": {"name": "DC Current String 1", "value": None, "unit": "A"},
            "current_dc_2": {"name": "DC Current String 2", "value": None, "unit": "A"},
            "grid_frequency": {"name": "Grid Frequency", "value": None, "unit": "Hz"},
            "inverter_temperature": {
                "name": "Inverter Temperature",
                "value": None,
                "unit": "°C",
            },
            "device_status": {"name": "Device Status", "value": None, "unit": None},
            "grid_relay_status": {
                "name": "Grid Relay Status",
                "value": None,
                "unit": None,
            },
        }

        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(logging.DEBUG)
            if not self.logger.handlers:
                ch = logging.StreamHandler()
                ch.setLevel(logging.DEBUG)
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                ch.setFormatter(formatter)
                self.logger.addHandler(ch)
        
    def _packet(self, cmd):
        self.pkt_id += 1                                                                                # increase packet counter
        commands = COMMAND_LIST[cmd]
        sep2 = bytes([0x00, 0x00])                                                                      # separator for default commands
        sep4 = bytes([0x00, 0x00, 0x00, 0x00])
        data = sep4                                                                                     # data same as separator4
        esignature = bytes.fromhex(SMA_ESIGNATURE + "09A0")

        if cmd == "login":
            sep2 = bytes([0x00, 0x01])                                                                  # separator for login
            esignature = bytes.fromhex(SMA_ESIGNATURE + "0EA0")
            encpasswd = [0x88, 0x88, 0x88, 0x88, 0x88, 0x88, 0x88, 0x88, 0x88, 0x88, 0x88, 0x88]
            encpasswd[0:len(self.password)] = [((0x88 + ord(char)) & 0xff) for char in self.password]   # encode password
            data = int(time.time()).to_bytes(4, byteorder='little')                                     # timestamp utc
            data += sep4 + bytes(encpasswd) + sep4                                                      # setarator4 + password + setarator4
        elif cmd == "logout":
            sep2 = bytes([0x00, 0x03])                                                                  # separator for logout
            esignature = bytes.fromhex(SMA_ESIGNATURE + "08A0")
            data = bytes([])                                                                            # no data on logout

        msg = bytes.fromhex(SMA_PKT_HEADER) + bytes([0x00, 0x00]) + esignature                          # header + placeholder len + signature
        msg += self.target_id + sep2 + self.my_id + sep2                                                # targets and my address
        msg += sep4 + (self.pkt_id | 0x8000).to_bytes(2, byteorder='little')                            # packet counter
        msg += commands[0].to_bytes(4, byteorder='little')                                              # command + first + last
        msg += commands[1].to_bytes(4, byteorder='little')
        msg += commands[2].to_bytes(4, byteorder='little')
        msg += data                                                                                     # data
        pkt_len = (len(msg)-20).to_bytes(2, byteorder='big')                                            # calculate packet length
        msg = msg[:12] + pkt_len + msg[14:]                                                             # insert packet length

        self.logger.debug("> %s", msg.hex())
        return msg

    def _send_recieve(self, cmd, receive=True, attempts=None):
        retry_limit = self.retry if attempts is None else attempts
        repeat = 0
        while repeat < retry_limit:
            repeat += 1
            try:
                msg = self._packet(cmd)
                self.sock.sendto(msg, (self.host, self.port))
                if not receive:
                    return
                data, address = self.sock.recvfrom(300)
                self.logger.debug("< %s", data.hex())
                size = len(data)
                if size > 42:
                    pkt_id = unpack_from("H", data, offset=40)[0]
                    error = unpack_from("I", data, offset=36)[0]
                    pkt_id &= 0x7FFF
                    # if (pkt_id != self.pkt_id) or (error != 0):
                    if error != 0:
                        self.logger.debug("Req/Rsp: Packet ID %X/%X, Error %d" % (self.pkt_id, pkt_id, error))
                        raise smaError("Inverter answer does not match our parameters.")
                    if (pkt_id != self.pkt_id):
                        self.pkt_id = pkt_id
                else:
                    raise smaError("Format of inverter response does not fit.")
                return data
            except (TimeoutError, socket.timeout, OSError) as exception:
                self.logger.warning(
                    "Communication error while requesting %s (%d/%d): %s",
                    cmd,
                    repeat,
                    retry_limit,
                    exception,
                )
                continue
        raise smaError(f"No response to {cmd}")

    def _login(self):
        data = self._send_recieve("login")
        if data:
            inv_susyid, inv_serial = unpack_from("<HI", data, offset=28)
            self.serial = inv_serial
            self.target_id = inv_susyid.to_bytes(2, byteorder='little') + inv_serial.to_bytes(4, byteorder='little')
            self.logger.debug("Logged in to inverter susyid: %d, serial: %d" % (inv_susyid, inv_serial))
            return True
        raise smaError("Login failed: no response")

    def _logout(self):
        try:
            self._send_recieve("logout", False)
        except smaError as exception:
            # A logout packet has no response.  Failure to send it must not turn a
            # successful measurement cycle into a failed Home Assistant update.
            self.logger.debug("Logout failed, ignoring: %s", exception)
        self.pkt_id = 0
        return True

    def set_diagnostic_intervals(self, fast_interval, medium_interval):
        """Set diagnostic polling intervals in seconds."""
        self.fast_diagnostic_interval = fast_interval
        self.medium_diagnostic_interval = medium_interval

    @staticmethod
    def _decode_status(register):
        """Decode the selected SMA tag from a status register."""
        for offset in range(8, len(register) - 3, 4):
            raw = int.from_bytes(register[offset : offset + 4], "little")
            if raw in INVALID_U32_VALUES:
                continue
            if raw & 0xFF000000:
                tag = raw & 0x00FFFFFF
                return SMA_STATUS_TAGS.get(tag, f"SMA tag {tag}")
        return None

    @staticmethod
    def _decode_number(register, value_type, factor):
        """Decode and scale the first value in an SMA register."""
        raw_unsigned = int.from_bytes(register[8:12], "little")
        if raw_unsigned in INVALID_U32_VALUES:
            return None
        signed = value_type == "int"
        value = int.from_bytes(register[8:12], "little", signed=signed)
        return value / factor if factor != 1 else value

    @staticmethod
    def _register_definition(register_id):
        """Return a definition, tolerating SMA's varying low identifier nibble."""
        definition = REGISTER_SENSORS.get(register_id)
        if definition is not None:
            return definition
        normalized_id = register_id >> 4
        for known_id, known_definition in REGISTER_SENSORS.items():
            if known_id >> 4 == normalized_id:
                return known_definition
        return None

    def _decode_register_response(self, data):
        """Decode diagnostics and report recognized and populated registers."""
        if len(data) < 58:
            self.logger.debug("Ignoring short diagnostic response (%d bytes)", len(data))
            return 0, 0

        first_register = unpack_from("I", data, offset=46)[0]
        last_register = unpack_from("I", data, offset=50)[0]
        register_count = last_register - first_register + 1
        payload_size = len(data) - 58
        if register_count <= 0 or payload_size <= 0:
            return 0, 0
        if payload_size % register_count:
            self.logger.debug(
                "Cannot split diagnostic response: %d bytes for %d registers",
                payload_size,
                register_count,
            )
            return 0, 0

        register_size = payload_size // register_count
        if register_size not in (16, 28, 40):
            self.logger.debug("Unsupported SMA register size: %d", register_size)
            return 0, 0

        recognized_count = 0
        decoded_count = 0
        for index in range(register_count):
            start = 54 + index * register_size
            register = data[start : start + register_size]
            if len(register) < 12:
                continue
            register_id = int.from_bytes(register[0:4], "little")
            definition = self._register_definition(register_id)
            if definition is None:
                continue
            recognized_count += 1
            sensor_key, value_type, factor = definition
            if value_type == "status":
                value = self._decode_status(register)
            else:
                value = self._decode_number(register, value_type, factor)
            if value is not None:
                self.sensors[sensor_key]["value"] = value
                decoded_count += 1
        return recognized_count, decoded_count

    def _record_diagnostic_failure(self, command, now, reason):
        """Back off a repeatedly unsupported optional command."""
        failures = self._diagnostic_failures[command] + 1
        self._diagnostic_failures[command] = failures
        if failures >= DIAGNOSTIC_FAILURE_LIMIT:
            self._diagnostic_retry_after[command] = now + DIAGNOSTIC_RETRY_DELAY
            self._diagnostic_failures[command] = 0
            self.logger.warning(
                "Optional diagnostic command %s failed repeatedly (%s); "
                "retrying in %d minutes",
                command,
                reason,
                DIAGNOSTIC_RETRY_DELAY // 60,
            )
        else:
            self.logger.debug(
                "Optional diagnostic command %s is unavailable (%d/%d): %s",
                command,
                failures,
                DIAGNOSTIC_FAILURE_LIMIT,
                reason,
            )

    def _fetch_diagnostics(self, command, now=None):
        """Fetch and decode one diagnostic command without fixed offsets."""
        now = monotonic() if now is None else now
        if now < self._diagnostic_retry_after[command]:
            return False

        for sensor_key in COMMAND_SENSOR_KEYS[command]:
            self.sensors[sensor_key]["value"] = None
        try:
            # Optional data must never hold up the three established production
            # entities for two complete socket timeouts.
            data = self._send_recieve(command, attempts=1)
        except smaError as exception:
            self._record_diagnostic_failure(command, now, exception)
            return False
        recognized_count, decoded_count = (
            self._decode_register_response(data) if data else (0, 0)
        )
        if recognized_count == 0:
            self._record_diagnostic_failure(command, now, "no compatible registers")
            return False

        # A compatible register containing SMA's no-value sentinel is a valid
        # response, most commonly seen while the inverter sleeps overnight.
        # Keep the entity unavailable, but do not classify the command as
        # unsupported or enter the 15-minute retry backoff.
        self._diagnostic_failures[command] = 0
        self._diagnostic_retry_after[command] = 0.0
        return True

    def _poll_next_diagnostic(self, commands, interval, now):
        """Poll at most one due command from a diagnostic tier."""
        for command in commands:
            if now < self._diagnostic_next_due[command]:
                continue
            self._fetch_diagnostics(command, now)
            self._diagnostic_next_due[command] = max(
                now + interval,
                self._diagnostic_retry_after[command],
            )
            return

    def _fetch(self, command):
        data = self._send_recieve(command)
        if data:
            data_len = len(data)
            cmd = unpack_from("H", data, offset=55)[0]
            self.logger.debug("Data identifier %02X" % cmd)
            if cmd == 0x821E:
                inv_class = unpack_from("I", data, offset=102)[0] & 0x00FFFFFF
                i = 142
                inv_type = 0
                while i + 4 <= data_len:  # 0x00FFFFFE is the attribute end marker
                    temp = unpack_from("I", data, offset=i)[0]
                    if temp == 0x00FFFFFE:
                        break
                    if (temp & 0xFF000000) == 0x01000000: # in some models a catalogue is transmitted, right model marked with: 0x01000000 OR INV_Type
                        inv_type = temp & 0x00FFFFFF
                    i = i + 4
                self.inv_class = str(inv_class)
                self.inv_type = str(inv_type)
                if inv_class in SMA_INV_CLASS:
                    self.inv_class = SMA_INV_CLASS[inv_class]
                if inv_type in SMA_INV_TYPE:
                    self.inv_type = SMA_INV_TYPE[inv_type]
                    
            elif cmd == 0x2601:
                if data_len >= 66:
                    value = unpack_from("I", data, offset=62)[0]
                    if value not in INVALID_U32_VALUES:
                        self.sensors['energy_total']['value'] = value / 1000
                if data_len >= 82:
                    value = unpack_from("I", data, offset=78)[0]
                    if value not in INVALID_U32_VALUES:
                        self.sensors['energy_today']['value'] = value / 1000

            elif cmd == 0x263F:
                value = unpack_from("I", data, offset=62)[0]
                if value in INVALID_U32_VALUES:
                    value = 0
                self.sensors['power_ac_total']['value'] = value
            return

    def init(self):
        self._login()
        self._fetch("info")
        self._logout()
    
    def update(self):
        now = monotonic()
        self._login()
        try:
            self._fetch("energy")
            self._fetch("power_ac_total")

            self._poll_next_diagnostic(
                FAST_DIAGNOSTIC_COMMANDS,
                self.fast_diagnostic_interval,
                now,
            )
            self._poll_next_diagnostic(
                MEDIUM_DIAGNOSTIC_COMMANDS,
                self.medium_diagnostic_interval,
                now,
            )
        finally:
            self._logout()

    def close(self):
        """Close the UDP socket."""
        self.sock.close()
