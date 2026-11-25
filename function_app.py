import azure.functions as func
import mysql.connector
import base64
import json
import os
import math
import csv
import io
import logging
import struct
from payload_decoders import em_320_tilt_decoder, em_310_tilt_decoder, em_500_udl_decoder, nwr_rts_decoder, em_320_th_decoder, em_300_th_decoder, wts_506_decoder, ct_101_decoder, em_400_mud_decoder, dl_pyr_decoder, dl_sth35_decoder, arf_ftd_decoder, at101_decoder, em_500_swl_decoder
from datetime import datetime, timezone
from cobs import cobs

app = func.FunctionApp(
    http_auth_level=func.AuthLevel.FUNCTION
)


EXPECTED_PAYLOAD_LENGTH = 32

ALERT_BYTE_POSITIONS = {1: -4, 2: -3, 3: -2}

DEFAULT_SENSOR_FIELDS = {
    "temperature": None,
    "humidity": None,
    "latitude": None,
    "longitude": None,
    "tilt": None,
    "distance": None,
    "angle_x": None,
    "angle_y": None,
    "angle_z": None,
    "battery": None,
    "degrees_hoz": None,
    "degrees_vert": None,
    "temp_rail": None,
    "temp_internal": None,
    "batt_perc": None,
    "batt_volt": None,
    "batt_day_remain": None,
    "sys_time": None,
    "on_track": None,
    "signal_quality": None,
    "total_current": None,
    "current": None,
    "water_level": None,
    "wind_direction": None,
    "pressure": None,
    "wind_speed": None,
    "rainfall_total": None,
    "rainfall_counter": None,
    "total_radiation": None,
    "a_enable": None,
    "a_1_triggered": None,
    "a_2_triggered": None,
    "a_3_triggered": None,
    "a_1_threshold": None,
    "a_2_threshold": None,
    "a_3_threshold": None
}

# ============================================================
# WELD PACKET CONFIGURATION
# ============================================================

START_MARKER = 0xA5
FORMAT_VERSION = 0x01

EXPECTED_MEASUREMENT_COUNT = 64
EXPECTED_RAW_PACKET_LENGTH = 135

MAX_PREHEAT_CYCLES = 8
PREHEAT_VALUES_PER_CYCLE = 5

RAIL_TYPE_NAMES = {
    0x01: "006-56 E1 260(6)",
    0x02: "011-60 E2 260(11)",
    0x03: "003-No75 CON(3)",
}

def get_connection():

    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        port=3306
    )

def lorawan_signal_quality(rssi: float, snr: float) -> int:
    """
    Convert LoRaWAN RSSI and SNR into a quality score from 1 (worst) to 5 (best).

    Parameters:
        rssi (float): Received Signal Strength Indicator in dBm.
        snr (float): Signal-to-Noise Ratio in dB.

    Returns:
        int: Quality score from 1 to 5.
    """
    if rssi is None or snr is None:
        return 1

    if isinstance(rssi, float) and math.isnan(rssi):
        return 1
    if isinstance(snr, float) and math.isnan(snr):
        return 1

    # Clamp RSSI between -120 and -30 dBm
    rssi_clamped = max(min(rssi, -30), -120)
    rssi_score = ((rssi_clamped + 120) / 90) * 4 + 1  # Normalize to 1-5

    # Clamp SNR between -20 and 10 dB
    snr_clamped = max(min(snr, 10), -20)
    snr_score = ((snr_clamped + 20) / 30) * 4 + 1  # Normalize to 1-5

    # Average both scores
    final_score = (float(rssi_score) + float(snr_score)) / 2

    return round(final_score)

def decode_payload(app_id, payload_bytes, f_port):

    if not payload_bytes:
        return None

    decoder_map = {
        "nwr-em320-tilt": em_320_tilt_decoder,
        "nwr-em310-tilt": em_310_tilt_decoder,
        "nwr-em500-udl": em_500_udl_decoder,
        "nwr-em300-th": em_300_th_decoder,
        "lifts-escalators": em_320_th_decoder,
        "nwr-em320-th": em_320_th_decoder,
        "nwr-rts": nwr_rts_decoder,
        "nwr-ct101": ct_101_decoder,
        "nwr-wts506": wts_506_decoder,
        "nwr-em400-mud": em_400_mud_decoder,
        "nwr-em500-swl": em_500_swl_decoder,
        "nwr-dl-pyr": dl_pyr_decoder,
        "nwr-dl-sth35": dl_sth35_decoder,
        "nwr-arf-ftd": arf_ftd_decoder,
        "nwr-at101": at101_decoder
    }

    decoder = decoder_map.get(app_id)

    if not decoder:
        return None
    
    f_port_decoders = {
        "nwr-rts"
    } # more can be added later if any require f_ports

    if app_id in f_port_decoders:
        return decoder(payload_bytes, f_port)
    
    return decoder(payload_bytes)

def process_row(row):

    payload_bytes = row["encoded_payload"]

    row["encoded_payload"] = (
        base64.b64encode(payload_bytes).decode("utf-8")
        if payload_bytes else None
    )

    row["latitude_set"] = (
        float(row["latitude_set"])
        if row["latitude_set"] is not None
        else None
    )

    row["longitude_set"] = (
        float(row["longitude_set"])
        if row["longitude_set"] is not None
        else None
    )

    row["latitude_latest"] = (
        float(row["latitude_latest"])
        if row["latitude_latest"] is not None
        else None
    )

    row["longitude_latest"] = (
        float(row["longitude_latest"])
        if row["longitude_latest"] is not None
        else None
    )   
    row["snr"] = (
        float(row["snr"])
        if row["snr"] is not None
        else None
    )

    row["rssi"] = (
        float(row["rssi"])
        if row["rssi"] is not None
        else None
    )

    row["f_port"] = (
        float(row["f_port"])
        if row["f_port"] is not None
        else None
    )

    row["recv_at"] = (
            row["recv_at"]
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    row.update(DEFAULT_SENSOR_FIELDS.copy())

    if row["rssi"] is not None and row["snr"] is not None:

        row["signal_quality"] = lorawan_signal_quality(
            row["rssi"],
            row["snr"]
        )

    try:
        decoded = decode_payload(
            row["app_id"],
            payload_bytes,
            row["f_port"]
        )
    except Exception as ex:
        logging.warning(
            "Decode failed for row %s: %s",
            row.get("id"),
            ex
        )
        decoded = {}

    if decoded:
        row.update(decoded)

    return row

def json_http_response(data, status_code=200):
    return func.HttpResponse(
        body=json.dumps(data, default=str),
        status_code=status_code,
        mimetype="application/json"
    )


# ============================================================
# CRC-16/CCITT-FALSE
# ============================================================

def crc16_ccitt(data):
    """
    Calculate CRC-16/CCITT-FALSE.

    Polynomial: 0x1021
    Initial value: 0xFFFF
    Final XOR: 0x0000
    """

    crc = 0xFFFF

    for byte in data:
        crc ^= byte << 8

        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    return crc

# ============================================================
# PAYLOAD EXTRACTION
# ============================================================

def extract_uplink_details(request_json):
    """
    Extract a payload from either:

    1. A The Things Stack v3 webhook
    2. A simple JSON test request containing payload_hex
    3. A simple JSON test request containing frm_payload

    Returns:
        encoded_payload
        device_id
        f_port
        frame_counter
        received_at
    """

    if not isinstance(request_json, dict):
        raise ValueError("Request body must be a JSON object")

    # --------------------------------------------------------
    # The Things Stack v3 webhook format
    # --------------------------------------------------------

    uplink_message = request_json.get("uplink_message")

    if isinstance(uplink_message, dict):
        frm_payload = uplink_message.get("frm_payload")

        if not frm_payload:
            raise ValueError(
                "The Things Stack webhook does not contain "
                "uplink_message.frm_payload"
            )

        try:
            encoded_payload = base64.b64decode(
                frm_payload,
                validate=True
            )
        except Exception as error:
            raise ValueError(
                "uplink_message.frm_payload is not valid Base64"
            ) from error

        end_device_ids = request_json.get(
            "end_device_ids",
            {}
        )

        device_id = end_device_ids.get(
            "device_id",
            "unknown"
        )

        f_port = uplink_message.get("f_port")
        frame_counter = uplink_message.get("f_cnt")

        received_at = parse_received_at(
            request_json.get("received_at")
            or uplink_message.get("received_at")
        )

        return {
            "encoded_payload": encoded_payload,
            "device_id": device_id,
            "f_port": f_port,
            "frame_counter": frame_counter,
            "received_at": received_at,
        }

    # --------------------------------------------------------
    # Direct hexadecimal test format
    # --------------------------------------------------------

    payload_hex = request_json.get("payload_hex")

    if payload_hex:
        cleaned_hex = (
            str(payload_hex)
            .replace(" ", "")
            .replace("\r", "")
            .replace("\n", "")
            .replace(":", "")
            .replace("-", "")
        )

        if cleaned_hex.lower().startswith("0x"):
            cleaned_hex = cleaned_hex[2:]

        try:
            encoded_payload = bytes.fromhex(cleaned_hex)
        except ValueError as error:
            raise ValueError(
                "payload_hex contains invalid hexadecimal data"
            ) from error

        return {
            "encoded_payload": encoded_payload,
            "device_id": request_json.get(
                "device_id",
                "manual-test"
            ),
            "f_port": request_json.get("f_port"),
            "frame_counter": request_json.get("frame_counter"),
            "received_at": parse_received_at(
                request_json.get("received_at")
            ),
        }

    # --------------------------------------------------------
    # Direct Base64 test format
    # --------------------------------------------------------

    frm_payload = request_json.get("frm_payload")

    if frm_payload:
        try:
            encoded_payload = base64.b64decode(
                frm_payload,
                validate=True
            )
        except Exception as error:
            raise ValueError(
                "frm_payload is not valid Base64"
            ) from error

        return {
            "encoded_payload": encoded_payload,
            "device_id": request_json.get(
                "device_id",
                "manual-test"
            ),
            "f_port": request_json.get("f_port"),
            "frame_counter": request_json.get("frame_counter"),
            "received_at": parse_received_at(
                request_json.get("received_at")
            ),
        }

    raise ValueError(
        "No supported payload was found. Supply a The Things "
        "Stack webhook, payload_hex or frm_payload."
    )

def parse_received_at(value):
    """
    Convert an ISO timestamp to a timezone-aware datetime.

    If no timestamp is supplied, use the current UTC time.
    """

    if not value:
        return datetime.now(timezone.utc)

    try:
        timestamp = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(timestamp)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except ValueError as error:
        raise ValueError(
            f"Invalid received_at timestamp: {value!r}"
        ) from error

# ============================================================
# COBS DECODING
# ============================================================

def decode_transport_payload(encoded_payload):
    """
    Recover the original raw packet.

    The transmitter uses COBS because the UC300 was observed to
    terminate serial data at a 0x00 byte.

    For testing, this function also accepts an already-decoded raw
    packet beginning with 0xA5.
    """

    if not encoded_payload:
        raise ValueError("The received payload is empty")

    # Permit direct raw-packet testing.
    if (
        len(encoded_payload) == EXPECTED_RAW_PACKET_LENGTH
        and encoded_payload[0] == START_MARKER
    ):
        return encoded_payload

    try:
        raw_packet = cobs.decode(encoded_payload)
    except cobs.DecodeError as error:
        raise ValueError(
            "The received payload is not valid COBS data"
        ) from error

    return raw_packet

# ============================================================
# FIXED-SCALE DECODING
# ============================================================

def get_measurement_scale(measurement_index):
    """
    Return the scale for one of the 64 normalised measurements.

    This must match the transmitter exactly.
    """

    # Initial values:
    #
    # 0 FE_t
    # 1 FE_s
    # 2 FE_Irms
    # 3 FE_Fmean
    # 4 PrH_Cyc

    if measurement_index == 4:
        return 1

    if measurement_index < 5:
        return 10

    # Eight preheat groups, five values per group.
    preheat_start = 5
    preheat_end = (
        preheat_start
        + MAX_PREHEAT_CYCLES * PREHEAT_VALUES_PER_CYCLE
    )

    if preheat_start <= measurement_index < preheat_end:
        position_in_cycle = (
            measurement_index - preheat_start
        ) % PREHEAT_VALUES_PER_CYCLE

        # Cycle number
        if position_in_cycle == 0:
            return 1

        # On and off times
        if position_in_cycle in {1, 2}:
            return 100

        # Current and force
        return 10

    # The remaining 19 values:
    #
    #  0 FF_t
    #  1 FF_s
    #  2 FF_bVel
    #  3 FF_eVel
    #  4 FF_Irms
    #  5 FF_Fmean
    #  6 FF_Fmean_x_mm
    #  7 FF_x_mm
    #  8 UP_ton
    #  9 UP_t
    # 10 UP_s
    # 11 UP_Vel
    # 12 UP_Irms
    # 13 UP_Fmean
    # 14 UP_s_Drop
    # 15 UP_F_Drop
    # 16 PoH_Cyc
    # 17 t_Weld
    # 18 s_Weld

    tail_position = measurement_index - preheat_end

    if tail_position in {2, 3, 8, 9}:
        return 100

    if tail_position == 16:
        return 1

    return 10

SCALE_FACTORS = [
    get_measurement_scale(index)
    for index in range(EXPECTED_MEASUREMENT_COUNT)
]

def unscale(value, scale):
    """
    Convert a transmitted scaled integer back to a number.

    Integer fields remain integers. Decimal fields become floats
    suitable for insertion into MySQL DECIMAL columns.
    """

    if scale == 1:
        return int(value)

    return value / scale

# ============================================================
# WELD PACKET DECODER
# ============================================================

def decode_weld_packet(raw_packet):
    """
    Decode and validate one 135-byte weld packet.

    Packet layout:

        byte 0       start marker
        byte 1       format version
        bytes 2-3    weld number uint16
        byte 4       rail type
        bytes 5-132  64 signed int16 measurements
        bytes 133-134 CRC-16
    """

    if len(raw_packet) != EXPECTED_RAW_PACKET_LENGTH:
        raise ValueError(
            f"Decoded packet is {len(raw_packet)} bytes; "
            f"expected {EXPECTED_RAW_PACKET_LENGTH}"
        )

    received_crc = struct.unpack(
        ">H",
        raw_packet[-2:]
    )[0]

    calculated_crc = crc16_ccitt(
        raw_packet[:-2]
    )

    if received_crc != calculated_crc:
        raise ValueError(
            f"CRC mismatch: received 0x{received_crc:04X}, "
            f"calculated 0x{calculated_crc:04X}"
        )

    unpack_format = (
        ">BBHB"
        + ("h" * EXPECTED_MEASUREMENT_COUNT)
        + "H"
    )

    unpacked = struct.unpack(
        unpack_format,
        raw_packet
    )

    start_marker = unpacked[0]
    payload_version = unpacked[1]
    weld_number = unpacked[2]
    rail_type = unpacked[3]

    scaled_measurements = list(
        unpacked[4:-1]
    )

    if start_marker != START_MARKER:
        raise ValueError(
            f"Invalid start marker 0x{start_marker:02X}; "
            f"expected 0x{START_MARKER:02X}"
        )

    if payload_version != FORMAT_VERSION:
        raise ValueError(
            f"Unsupported payload version 0x{payload_version:02X}; "
            f"expected 0x{FORMAT_VERSION:02X}"
        )

    if rail_type not in RAIL_TYPE_NAMES:
        raise ValueError(
            f"Unsupported rail type 0x{rail_type:02X}"
        )

    measurements = [
        unscale(value, scale)
        for value, scale in zip(
            scaled_measurements,
            SCALE_FACTORS
        )
    ]

    return map_measurements(
        weld_number=weld_number,
        rail_type=rail_type,
        payload_version=payload_version,
        measurements=measurements,
        raw_packet=raw_packet,
    )

# ============================================================
# MEASUREMENT MAPPING
# ============================================================

def map_measurements(
    weld_number,
    rail_type,
    payload_version,
    measurements,
    raw_packet,
):
    """
    Map the normalised list of 64 measurements into named fields.
    """

    if len(measurements) != 64:
        raise ValueError(
            f"Expected 64 measurements, received "
            f"{len(measurements)}"
        )

    decoded = {
        "weld_number": weld_number,
        "rail_type": rail_type,
        "rail_type_name": RAIL_TYPE_NAMES[rail_type],
        "payload_version": payload_version,
        "raw_payload": raw_packet,

        "fe_time": measurements[0],
        "fe_displacement": measurements[1],
        "fe_current": measurements[2],
        "fe_force": measurements[3],
        "preheat_cycle_count": measurements[4],
    }

    declared_cycle_count = int(
        decoded["preheat_cycle_count"]
    )

    if not 0 <= declared_cycle_count <= MAX_PREHEAT_CYCLES:
        raise ValueError(
            f"Decoded preheat cycle count "
            f"{declared_cycle_count} is invalid"
        )

    # Measurements 5-44 contain eight five-value cycle groups.
    preheat_cycles = []

    cycle_section_start = 5

    for cycle_index in range(MAX_PREHEAT_CYCLES):
        offset = (
            cycle_section_start
            + cycle_index * PREHEAT_VALUES_PER_CYCLE
        )

        cycle_number = int(measurements[offset])

        # Do not insert zero-filled padding cycles.
        if cycle_index >= declared_cycle_count:
            continue

        if cycle_number == 0:
            raise ValueError(
                f"Preheat cycle {cycle_index + 1} is declared "
                f"but has a zero cycle number"
            )

        preheat_cycles.append({
            "cycle_number": cycle_number,
            "on_time": measurements[offset + 1],
            "off_time": measurements[offset + 2],
            "current": measurements[offset + 3],
            "mean_force": measurements[offset + 4],
        })

    # Tail begins after 5 + 40 measurements.
    tail = 45

    decoded.update({
        "ff_time": measurements[tail + 0],
        "ff_displacement": measurements[tail + 1],
        "ff_begin_velocity": measurements[tail + 2],
        "ff_end_velocity": measurements[tail + 3],
        "ff_current": measurements[tail + 4],
        "ff_force": measurements[tail + 5],
        "ff_force_x_mm": measurements[tail + 6],
        "ff_x_mm": measurements[tail + 7],

        "up_on_time": measurements[tail + 8],
        "up_time": measurements[tail + 9],
        "up_displacement": measurements[tail + 10],
        "up_velocity": measurements[tail + 11],
        "up_current": measurements[tail + 12],
        "up_force": measurements[tail + 13],
        "up_displacement_drop": measurements[tail + 14],
        "up_force_drop": measurements[tail + 15],

        "postheat_cycle_count": int(
            measurements[tail + 16]
        ),

        "weld_time": measurements[tail + 17],
        "weld_displacement": measurements[tail + 18],

        "preheat_cycles": preheat_cycles,
    })

    return decoded

# ============================================================
# DATABASE INSERT
# ============================================================

def insert_weld(
    connection,
    decoded,
    device_id,
    received_at,
    f_port,
    frame_counter,
):
    """
    Insert the main weld and its preheat cycles in one transaction.

    Returns the new weld_records.id.
    """

    cursor = connection.cursor()

    try:
        connection.start_transaction()

        main_insert_sql = """
            INSERT INTO weld_records (
                device_id,
                weld_number,
                rail_type,
                received_at,

                fe_time,
                fe_displacement,
                fe_current,
                fe_force,

                preheat_cycle_count,

                ff_time,
                ff_displacement,
                ff_begin_velocity,
                ff_end_velocity,
                ff_current,
                ff_force,
                ff_force_x_mm,
                ff_x_mm,

                up_on_time,
                up_time,
                up_displacement,
                up_velocity,
                up_current,
                up_force,
                up_displacement_drop,
                up_force_drop,

                postheat_cycle_count,

                weld_time,
                weld_displacement,

                f_port,
                frame_counter,
                payload_version,
                raw_payload
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s,
                %s, %s,
                %s, %s, %s, %s
            )
        """

        main_values = (
            device_id,
            decoded["weld_number"],
            decoded["rail_type"],
            received_at.replace(tzinfo=None),

            decoded["fe_time"],
            decoded["fe_displacement"],
            decoded["fe_current"],
            decoded["fe_force"],

            decoded["preheat_cycle_count"],

            decoded["ff_time"],
            decoded["ff_displacement"],
            decoded["ff_begin_velocity"],
            decoded["ff_end_velocity"],
            decoded["ff_current"],
            decoded["ff_force"],
            decoded["ff_force_x_mm"],
            decoded["ff_x_mm"],

            decoded["up_on_time"],
            decoded["up_time"],
            decoded["up_displacement"],
            decoded["up_velocity"],
            decoded["up_current"],
            decoded["up_force"],
            decoded["up_displacement_drop"],
            decoded["up_force_drop"],

            decoded["postheat_cycle_count"],

            decoded["weld_time"],
            decoded["weld_displacement"],

            f_port,
            frame_counter,
            decoded["payload_version"],
            decoded["raw_payload"],
        )

        cursor.execute(
            main_insert_sql,
            main_values
        )

        weld_record_id = cursor.lastrowid

        preheat_insert_sql = """
            INSERT INTO weld_preheat_cycles (
                weld_record_id,
                cycle_number,
                on_time,
                off_time,
                current,
                mean_force
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """

        preheat_values = [
            (
                weld_record_id,
                cycle["cycle_number"],
                cycle["on_time"],
                cycle["off_time"],
                cycle["current"],
                cycle["mean_force"],
            )
            for cycle in decoded["preheat_cycles"]
        ]

        if preheat_values:
            cursor.executemany(
                preheat_insert_sql,
                preheat_values
            )

        connection.commit()

        return weld_record_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()

# ============================================================
# HTTP ROUTE
# ============================================================

@app.route(route="weld",methods=["POST"])
def receive_weld(req: func.HttpRequest) -> func.HttpResponse:
    """
    Receive a weld payload from The Things Stack or a manual test.
    """

    connection = None

    try:
        try:
            request_json = req.get_json()
        except ValueError as error:
            raise ValueError(
                "Request body must contain valid JSON"
            ) from error

        uplink = extract_uplink_details(
            request_json
        )

        raw_packet = decode_transport_payload(
            uplink["encoded_payload"]
        )

        decoded = decode_weld_packet(
            raw_packet
        )

        connection = get_connection()

        weld_record_id = insert_weld(
            connection=connection,
            decoded=decoded,
            device_id=uplink["device_id"],
            received_at=uplink["received_at"],
            f_port=uplink["f_port"],
            frame_counter=uplink["frame_counter"],
        )

        response_body = {
            "status": "stored",
            "weld_record_id": weld_record_id,
            "device_id": uplink["device_id"],
            "weld_number": decoded["weld_number"],
            "rail_type": decoded["rail_type"],
            "rail_type_name": decoded["rail_type_name"],
            "preheat_cycle_count": (
                decoded["preheat_cycle_count"]
            ),
            "preheat_rows_inserted": len(
                decoded["preheat_cycles"]
            ),
            "payload_version": (
                decoded["payload_version"]
            ),
            "raw_packet_length": len(raw_packet),
        }

        logging.info(
            "Stored weld %s from %s as record %s",
            decoded["weld_number"],
            uplink["device_id"],
            weld_record_id,
        )

        return func.HttpResponse(
            body=json.dumps(response_body),
            status_code=201,
            mimetype="application/json",
        )

    except ValueError as error:
        logging.warning(
            "Rejected weld payload: %s",
            error
        )

        return func.HttpResponse(
            body=json.dumps({
                "status": "rejected",
                "error": str(error),
            }),
            status_code=400,
            mimetype="application/json",
        )

    except mysql.connector.IntegrityError as error:
        logging.warning(
            "Database integrity error: %s",
            error
        )

        return func.HttpResponse(
            body=json.dumps({
                "status": "not_stored",
                "error": "The weld record conflicts with an "
                         "existing database record.",
                "database_error": str(error),
            }),
            status_code=409,
            mimetype="application/json",
        )

    except mysql.connector.Error as error:
        logging.exception(
            "MySQL error while storing weld"
        )

        return func.HttpResponse(
            body=json.dumps({
                "status": "error",
                "error": "Database operation failed",
                "database_error": str(error),
            }),
            status_code=500,
            mimetype="application/json",
        )

    except Exception as error:
        logging.exception(
            "Unexpected weld route error"
        )

        return func.HttpResponse(
            body=json.dumps({
                "status": "error",
                "error": str(error),
            }),
            status_code=500,
            mimetype="application/json",
        )

    finally:
        if connection is not None and connection.is_connected():
            connection.close()




@app.route(route="store", methods=["POST"])
def store(req: func.HttpRequest):

    try:

        recv_data = req.get_json()

        # Payload
        b64_payload_str = recv_data["uplink_message"]["frm_payload"]
        data_bytes = base64.b64decode(b64_payload_str)

        # Device info
        device_eui = recv_data["end_device_ids"]["dev_eui"]
        app_id = recv_data["end_device_ids"]["application_ids"]["application_id"]

        latitude_latest = None
        longitude_latest = None
        decoded = None
        f_port = (
            recv_data
            .get("uplink_message", {})
            .get("f_port", 0)
        )

        if app_id == 'nwr-rts':
            decoded = nwr_rts_decoder(data_bytes, f_port)
            latitude_latest = decoded.get("latitude")
            longitude_latest = decoded.get("longitude")

        if app_id == 'nwr-at101':
            decoded = at101_decoder(data_bytes)
            latitude_latest = decoded.get("latitude")
            longitude_latest = decoded.get("longitude")            


        recv_at = recv_data["received_at"]
        recv_at = recv_at[:19]

        f_cnt = (
            recv_data
            .get("uplink_message", {})
            .get("f_cnt", 0)
        )



        # Best gateway
        rx_metadata = (
            recv_data
            .get("uplink_message", {})
            .get("rx_metadata", [])
        )

        rssi = 0
        snr = 0

        if rx_metadata:

            sorted_rx = sorted(
                rx_metadata,
                key=lambda x: x.get("rssi", -999),
                reverse=True
            )

            rssi = sorted_rx[0].get("rssi", 0)
            snr = sorted_rx[0].get("snr", 0)

        conn = get_connection()

        cursor = conn.cursor()

        sql = """
        INSERT INTO device_data (
            app_id,
            device_eui,
            recv_at,
            encoded_payload,
            f_cnt,
            f_port,
            rssi,
            snr
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s
        )
        """

        latest_sql = """
        INSERT INTO device_latest (
            app_id,
            device_eui,
            recv_at,
            encoded_payload,
            f_cnt,
            f_port,
            rssi,
            snr
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s
        )
        ON DUPLICATE KEY UPDATE
            app_id = VALUES(app_id),
            recv_at = VALUES(recv_at),
            encoded_payload = VALUES(encoded_payload),
            f_cnt = VALUES(f_cnt),
            f_port = VALUES(f_port),
            rssi = VALUES(rssi),
            snr = VALUES(snr)
        """

        location_sql = """
        INSERT INTO device_location (
            device_eui,
            app_id,
            recv_at,
            latitude,
            longitude
        )
        VALUES (
            %s,%s,%s,%s,%s
        )
        ON DUPLICATE KEY UPDATE
            app_id = VALUES(app_id),
            recv_at = VALUES(recv_at),
            latitude = VALUES(latitude),
            longitude = VALUES(longitude)
        """

        cursor.execute(
            sql,
            (
                app_id,
                device_eui,
                recv_at,
                data_bytes,
                f_cnt,
                f_port,
                rssi,
                snr
            )
        )

        cursor.execute(
            latest_sql,
            (
                app_id,
                device_eui,
                recv_at,
                data_bytes,
                f_cnt,
                f_port,
                rssi,
                snr
            )
        )

        if latitude_latest:
            cursor.execute(
                location_sql,
                (
                    device_eui,
                    app_id,
                    recv_at,
                    latitude_latest,
                    longitude_latest
                )
            )

        conn.commit()

        cursor.close()
        conn.close()

        return func.HttpResponse(
            body='{"success":"success"}',
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:

        return func.HttpResponse(
            str(e),
            status_code=500
        )

@app.route(route="updateattributes", methods=["POST"])
def updateattributes(req: func.HttpRequest):

    try:

        recv_data = req.get_json()
        device_eui = recv_data.get("device_eui")
        app_id = recv_data.get("app_id")
        name = recv_data.get("name") if recv_data.get("name") not in ("",None) else None
        description = recv_data.get("description") if recv_data.get("description") not in ("",None) else None
        route = recv_data.get("route") if recv_data.get("route") not in ("",None) else None
        region = recv_data.get("region") if recv_data.get("region") not in ("",None) else None
        mdu = recv_data.get("mdu") if recv_data.get("mdu") not in ("",None) else None
        latitude = recv_data.get("latitude") if recv_data.get("latitude") not in ("",None) else None
        longitude = recv_data.get("longitude") if recv_data.get("longitude") not in ("",None) else None                                                      

        conn = get_connection()

        cursor = conn.cursor()

        sql = """
        INSERT INTO device_attributes (
            device_eui,
            app_id,
            name,
            description,
            route,
            region,
            mdu,
            latitude,
            longitude
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        ON DUPLICATE KEY UPDATE
            app_id = VALUES(app_id),
            name = VALUES(name),
            description = VALUES(description),
            route = VALUES(route),
            region = VALUES(region),
            mdu = VALUES(mdu),
            latitude = VALUES(latitude),
            longitude = VALUES(longitude)
        """

        cursor.execute(
            sql,
            (
                device_eui,
                app_id,
                name,
                description,
                route,
                region,
                mdu,
                latitude,
                longitude
            )
        )


        conn.commit()

        cursor.close()
        conn.close()

        return func.HttpResponse(
            json.dumps({
                "success": True,
                "device_eui": device_eui,
                "message": "Attributes updated"
            }),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:

        return func.HttpResponse(
            str(e),
            status_code=500
        )
    
@app.route(route="latest", methods=["GET"])
def latest(req: func.HttpRequest):

    app_id = req.params.get("app_id")

    conn = get_connection()

    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT
        latest.app_id,
        latest.device_eui,
        latest.recv_at,
        latest.encoded_payload,
        latest.f_cnt,
        latest.f_port,
        latest.rssi,
        latest.snr,

        attr.route,
        attr.region,
        attr.mdu,
        attr.name,
        attr.description,

        attr.latitude AS latitude_set,
        attr.longitude AS longitude_set,

        loc.latitude AS latitude_latest,
        loc.longitude AS longitude_latest

    FROM (

        SELECT *
        FROM device_latest
        WHERE 1=1
    """

    params = []

    if app_id:
        sql += " AND app_id = %s"
        params.append(app_id)

    sql += """
    ) latest

    LEFT JOIN device_attributes attr
        ON latest.device_eui = attr.device_eui

    LEFT JOIN device_location loc
        ON latest.device_eui = loc.device_eui
    """

    cursor.execute(sql, params)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    result = [
        process_row(row)
        for row in rows
    ]

    return func.HttpResponse(
        json.dumps(result, default=str),
        mimetype="application/json",
        status_code=200
    )

@app.route(route="apps", methods=["GET"])
def apps(req: func.HttpRequest):

    conn = get_connection()

    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT
        *

    FROM 
        vw_app_data
    """

    cursor.execute(sql)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return func.HttpResponse(
        json.dumps(rows, default=str),
        mimetype="application/json",
        status_code=200
    )

@app.route(route="data", methods=["GET"])
def data(req: func.HttpRequest):

    app_id = req.params.get("app_id")
    device_eui = req.params.get("device_eui")
    start = req.params.get("start")
    end = req.params.get("end")
    page_size = min(int(req.params.get("page_size", "5000")),10000)
    after_id = int(req.params.get("after_id"))

    conn = get_connection()

    cursor = conn.cursor(dictionary=True)

    params = []

    sql = """
    SELECT
        data.id,
        data.app_id,
        data.device_eui,
        data.recv_at,
        data.encoded_payload,
        data.f_cnt,
        data.f_port,
        data.rssi,
        data.snr,
        attr.route,
        attr.region,
        attr.mdu,
        attr.name,
        attr.description,
        attr.latitude AS latitude_set,
        attr.longitude AS longitude_set,
        loc.latitude AS latitude_latest,
        loc.longitude AS longitude_latest
    FROM (
        SELECT
            id,
            app_id,
            device_eui,
            recv_at,
            encoded_payload,
            f_cnt,
            f_port,
            rssi,
            snr
        FROM device_data
        WHERE 1=1
    """
    if after_id:
        sql += " AND id > %s"
        params.append(after_id)

    if app_id:
        sql += " AND app_id = %s"
        params.append(app_id)

    if device_eui:
        sql += " AND device_eui = %s"
        params.append(device_eui)

    sql += """
        AND recv_at >= %s
        AND recv_at < %s
        ORDER BY id ASC
        LIMIT %s
    ) data
    LEFT JOIN device_attributes attr
        ON data.device_eui = attr.device_eui
    LEFT JOIN device_location loc
        ON data.device_eui = loc.device_eui
    """

    params.append(start)
    params.append(end)
    params.append(page_size)

        

    cursor.execute(sql, params)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    result = [
        process_row(row)
        for row in rows
    ]
    next_after_id = result[-1]["id"] if result else None

    response = {
        "data": result,
        "next_after_id": next_after_id,
        "result_size": len(result),
        "has_more": len(result) == page_size
    }

    return func.HttpResponse(
        json.dumps(response, default=str),
        mimetype="application/json",
        status_code=200
    )

@app.route(route="gatewaylocation", methods=["GET"])
def gatewaylocation(req: func.HttpRequest):

    conn = get_connection()

    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT
        *
    FROM gateway_location
    """
    cursor.execute(sql)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return func.HttpResponse(
        json.dumps(rows, default=str),
        mimetype="application/json",
        status_code=200
    )

@app.route(route="exportcsv", methods=["GET"])
def exportcsv(req: func.HttpRequest):

    date = req.params.get("date")
    app_id = req.params.get("app_id")

    if not date:

        return func.HttpResponse(
            "A date parameters is required",
            status_code=400
        )

    conn = get_connection()

    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT
        id,
        app_id,
        device_eui,
        recv_at,
        encoded_payload,
        f_cnt,
        latitude,
        longitude,
        rssi,
        snr
    FROM device_data
    WHERE DATE(recv_at) = %s
    """

    params = [date]

    if app_id:

        sql += " AND app_id = %s"

        params.append(app_id)

    sql += """
    ORDER BY id DESC
    """

    cursor.execute(sql, params)

    rows = cursor.fetchall()

    cursor.close()
    conn.close()

    result = []

    for row in rows:

        payload_bytes = row["encoded_payload"]

        row["encoded_payload"] = (
            base64.b64encode(payload_bytes).decode("utf-8")
            if payload_bytes else None
        )

        row["latitude"] = (
            float(row["latitude"])
            if row["latitude"] is not None
            else None
        )

        row["longitude"] = (
            float(row["longitude"])
            if row["longitude"] is not None
            else None
        )

        row["rssi"] = (
            float(row["rssi"])
            if row["rssi"] is not None
            else None
        )

        row["snr"] = (
            float(row["snr"])
            if row["snr"] is not None
            else None
        )

        row.update(DEFAULT_SENSOR_FIELDS.copy())

        if row["rssi"] is not None and row["snr"] is not None:

            row["signal_quality"] = lorawan_signal_quality(
                row["rssi"],
                row["snr"]
            )

        decoded = decode_payload(
            row["app_id"],
            payload_bytes
        )

        if decoded:
            row.update(decoded)

        result.append(row)

    output = io.StringIO()

    fieldnames = list(result[0].keys()) if result else []

    writer = csv.DictWriter(
        output,
        fieldnames=fieldnames
    )

    writer.writeheader()

    writer.writerows(result)

    filename = (
        f"export_{date}.csv"
            .replace(':', '-')
    )

    return func.HttpResponse(
        body=output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
            f"attachment; filename={filename}"
        },
        status_code=200
    )

@app.route(route="alerts", methods=["GET"])
def get_alert_events(req: func.HttpRequest):
    latest_readings_sql = """
        SELECT
            device_eui,
            recv_at,
            encoded_payload
        FROM device_latest
        WHERE app_id = 'nwr-rts'
    """

    get_state_sql = """
        SELECT threshold, alert_enabled, alert_triggered, reading_id, reading_time
        FROM device_alert_state
        WHERE device_eui = %s AND alert_level = %s
        FOR UPDATE
    """

    insert_state_sql = """
        INSERT INTO device_alert_state (
            device_eui, alert_level, threshold, rail_temperature,
            alert_enabled, alert_triggered, reading_id, reading_time,
            state_changed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
    """

    update_state_changed_sql = """
        UPDATE device_alert_state
        SET threshold = %s,
            rail_temperature = %s,
            alert_enabled = %s,
            alert_triggered = %s,
            reading_id = %s,
            reading_time = %s,
            state_changed_at = NOW()
        WHERE device_eui = %s AND alert_level = %s
    """

    update_state_unchanged_sql = """
        UPDATE device_alert_state
        SET threshold = %s,
            rail_temperature = %s,
            alert_enabled = %s,
            alert_triggered = %s,
            reading_id = %s,
            reading_time = %s
        WHERE device_eui = %s AND alert_level = %s
    """

    insert_event_sql = """
        INSERT IGNORE INTO device_alert_events (
            device_eui, alert_level, event_type, reading_id, reading_time,
            threshold, rail_temperature, notification_status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
    """

    get_pending_events_sql = """
        SELECT id AS event_id, device_eui, alert_level, event_type,
               reading_id, reading_time, threshold, rail_temperature,
               notification_status, created_at
        FROM device_alert_events
        WHERE notification_status = 'pending'
        ORDER BY created_at ASC, id ASC
    """

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        conn.start_transaction()

        cursor.execute(
            latest_readings_sql,
            (EXPECTED_PAYLOAD_LENGTH, EXPECTED_PAYLOAD_LENGTH)
        )
        readings = cursor.fetchall()
        transitions_created = 0

        for reading in readings:
            if reading["encoded_payload"] is None:
                continue

            payload = bytes(reading["encoded_payload"])
            if len(payload) != EXPECTED_PAYLOAD_LENGTH:
                continue

            alert_enabled = 1 if payload[21] & 0x40 else 0

            temp_internal_combined = (
                ((payload[2] & 0x0F) * 16) + (payload[3] / 16)
            )
            internal_temperature = (
                temp_internal_combined - 4096
                if payload[2] > 127
                else temp_internal_combined
            )

            temp_copper_combined = (
                ((payload[0] & 0x0F) * 16) + (payload[1] / 16)
            )
            copper_temperature = (
                temp_copper_combined - 4096
                if payload[0] > 127
                else temp_copper_combined
            )

            k_value = payload[31] / 100
            rail_temperature = copper_temperature + k_value * (
                copper_temperature - internal_temperature
            )

            for alert_level, byte_position in ALERT_BYTE_POSITIONS.items():
                threshold = payload[byte_position] & 0x7F
                alert_triggered = 1 if rail_temperature > threshold else 0

                state_values = (
                    reading["device_eui"], alert_level, threshold,
                    rail_temperature, alert_enabled, alert_triggered,
                    reading["reading_id"], reading["recv_at"]
                )

                cursor.execute(
                    get_state_sql,
                    (reading["device_eui"], alert_level)
                )
                previous_state = cursor.fetchone()

                if previous_state is None:
                    cursor.execute(insert_state_sql, state_values)

                    if alert_enabled == 1 and alert_triggered == 1:
                        cursor.execute(
                            insert_event_sql,
                            (
                                reading["device_eui"], alert_level,
                                "triggered", reading["reading_id"],
                                reading["recv_at"], threshold,
                                rail_temperature
                            )
                        )
                        if cursor.rowcount == 1:
                            transitions_created += 1
                    continue

                previous_enabled = int(previous_state["alert_enabled"])
                previous_triggered = int(previous_state["alert_triggered"])

                state_changed = (
                    previous_enabled != alert_enabled
                    or previous_triggered != alert_triggered
                )

                event_type = None
                if (
                    previous_triggered == 0
                    and alert_triggered == 1
                    and alert_enabled == 1
                ):
                    event_type = "triggered"
                elif (
                    previous_triggered == 1
                    and alert_triggered == 0
                    and alert_enabled == 1
                ):
                    event_type = "cleared"

                if event_type is not None:
                    cursor.execute(
                        insert_event_sql,
                        (
                            reading["device_eui"], alert_level, event_type,
                            reading["reading_id"], reading["recv_at"],
                            threshold, rail_temperature
                        )
                    )
                    if cursor.rowcount == 1:
                        transitions_created += 1

                update_values = (
                    threshold, rail_temperature, alert_enabled,
                    alert_triggered, reading["reading_id"],
                    reading["recv_at"], reading["device_eui"], alert_level
                )

                cursor.execute(
                    update_state_changed_sql
                    if state_changed
                    else update_state_unchanged_sql,
                    update_values
                )

        conn.commit()

        cursor.execute(get_pending_events_sql)
        pending_events = cursor.fetchall()

        alerts = [
            {
                "event_id": event["event_id"],
                "device_eui": event["device_eui"],
                "alert_level": event["alert_level"],
                "event_type": event["event_type"],
                "reading_id": event["reading_id"],
                "reading_time": (
                    event["reading_time"].isoformat()
                    if event["reading_time"] is not None else None
                ),
                "threshold": event["threshold"],
                "rail_temperature": (
                    float(event["rail_temperature"])
                    if event["rail_temperature"] is not None else None
                ),
                "notification_status": event["notification_status"],
                "created_at": (
                    event["created_at"].isoformat()
                    if event["created_at"] is not None else None
                )
            }
            for event in pending_events
        ]

        return json_http_response({
            "processed_sensor_count": len(readings),
            "transitions_created": transitions_created,
            "count": len(alerts),
            "alerts": alerts
        })

    except mysql.connector.Error as e:
        if conn is not None:
            conn.rollback()
        return json_http_response({
            "error": "Unable to process sensor alerts",
            "details": str(e)
        }, 500)

    except Exception as e:
        if conn is not None:
            conn.rollback()
        return json_http_response({
            "error": "Unexpected error while processing sensor alerts",
            "details": str(e)
        }, 500)

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()

@app.route(route="alerts/{event_id:int}/sent", methods=["POST"])
def mark_alert_sent(req: func.HttpRequest):
    conn = None
    cursor = None

    try:
        event_id = int(req.route_params["event_id"])
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE device_alert_events
            SET notification_status = 'sent',
                sent_at = NOW(),
                attempt_count = attempt_count + 1,
                last_error = NULL
            WHERE id = %s AND notification_status <> 'sent'
            """,
            (event_id,)
        )

        updated = cursor.rowcount == 1
        conn.commit()

        if not updated:
            return json_http_response({
                "event_id": event_id,
                "updated": False,
                "message": "Event does not exist or was already marked as sent"
            })

        return json_http_response({
            "event_id": event_id,
            "updated": True,
            "notification_status": "sent"
        })

    except Exception as e:
        if conn is not None:
            conn.rollback()
        return json_http_response({
            "error": "Unable to update alert notification",
            "event_id": req.route_params.get("event_id"),
            "details": str(e)
        }, 500)

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()

@app.route(route="alerts/{event_id:int}/failed", methods=["POST"])
def mark_alert_failed(req: func.HttpRequest):
    conn = None
    cursor = None

    try:
        event_id = int(req.route_params["event_id"])

        try:
            request_data = req.get_json()
        except ValueError:
            request_data = {}

        if not isinstance(request_data, dict):
            request_data = {}

        error_message = str(request_data.get(
            "error",
            "Power Automate notification failed"
        ))[:1000]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE device_alert_events
            SET notification_status = 'failed',
                attempt_count = attempt_count + 1,
                last_error = %s
            WHERE id = %s AND notification_status <> 'sent'
            """,
            (error_message, event_id)
        )

        updated = cursor.rowcount == 1
        conn.commit()

        if not updated:
            return json_http_response({
                "event_id": event_id,
                "updated": False,
                "message": "Event does not exist or is already sent"
            })

        return json_http_response({
            "event_id": event_id,
            "updated": True,
            "notification_status": "failed"
        })

    except Exception as e:
        if conn is not None:
            conn.rollback()
        return json_http_response({
            "error": "Unable to update alert notification",
            "event_id": req.route_params.get("event_id"),
            "details": str(e)
        }, 500)

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()
