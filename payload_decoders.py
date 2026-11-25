import math



def read_int16_le(b0, b1):
    ####Reads a signed 16-bit int from two bytes (little endian)
    value = (b1 << 8) | b0
    return value - 0x10000 if value >= 0x8000 else value

def read_int32_le(b0, b1, b2, b3):
    ####Reads a signed 32-bit int from two bytes (little endian)
    value = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
    return value - 0x100000000 if value >= 0x80000000 else value

def readUInt32LE(b0,b1,b2,b3):
    value = (b3 << 24) | (b2 << 16) | (b1 << 8) | b0
    return value & 0xffffffff

def readUInt8(byte):
    # If byte is a 1-element list or bytes-like, extract its value
    if isinstance(byte, (list, bytes, bytearray)):
        byte = byte[0]
    return byte & 0xFF

def readInt8(byte):
    ref = readUInt8(byte)
    return ref - 0x100 if ref > 0x7F else ref

def readPositionType(type_):
    type_map = {
        0: "normal",
        1: "tilt"
    }
    return type_map.get(type_)

def readAlarmType(type_):
    type_map = {
        0: "threshold_alarm_release",
        1: "threshold_alarm"
    }
    return type_map.get(type_)

def calculate_angles(x, y, z, threshold=100):
    # Compute magnitude in XY plane
    horizontal_magnitude = math.sqrt(x**2 + y**2)
    total_magnitude = math.sqrt(x**2 + y**2 + z**2)

    # Only calculate theta if X and Y are significantly non-zero
    if horizontal_magnitude >= threshold:
        theta = math.atan2(y, x)
        theta_deg = round(math.degrees(theta),2)
    else:
        theta_deg = 0

    # Always calculate phi (vertical angle)
    phi = math.acos(z / total_magnitude) if total_magnitude != 0 else 0
    phi_deg = round(math.degrees(phi), 2)

    return theta_deg, phi_deg


def em_320_tilt_decoder(data_bytes):
    i = 0
    decoded = {}

    while i < len(data_bytes):
        channel_id = data_bytes[i]
        i += 1
        channel_type = data_bytes[i]
        i += 1
        if i >= len(data_bytes):
            break

        # BATTERY
        if channel_id == 0x01 and channel_type == 0x75:
            decoded['battery'] = data_bytes[i]
            i += 1

        # ANGLE
        elif channel_id == 0x03 and channel_type == 0xd4:
            decoded['angle_x'] = (read_int16_le(data_bytes[i], data_bytes[i+1]) >> 1) / 100
            decoded['angle_y'] = (read_int16_le(data_bytes[i+2], data_bytes[i+3]) >> 1) / 100
            decoded['angle_z'] = (read_int16_le(data_bytes[i+4], data_bytes[i+5]) >> 1) / 100
            #decoded['threshold_x'] = 1 if (data_bytes[i] & 1) == 1 else 0
            #decoded['threshold_y'] = 1 if ((data_bytes[i+2] >> 1) & 1) == 1 else 0
            #decoded['threshold_z'] = 1 if ((data_bytes[i+4] >> 2) & 1) == 1 else 0

            degrees_hoz, degrees_vert = calculate_angles(decoded['angle_x'],decoded['angle_y'],decoded['angle_z'], 5)
            decoded['degrees_hoz'] = degrees_hoz
            decoded['degrees_vert'] = degrees_vert
            i += 6

        else:
            break

    return decoded

def em_310_tilt_decoder(data_bytes):
    i = 0
    decoded = {}

    while i < len(data_bytes):
        channel_id = data_bytes[i]
        i += 1
        channel_type = data_bytes[i]
        i += 1
        if i >= len(data_bytes):
            break

        # BATTERY
        if channel_id == 0x01 and channel_type == 0x75:
            decoded['battery'] = data_bytes[i]
            i += 1

        # ANGLE
        elif channel_id == 0x03 and channel_type == 0xcf:
            decoded['angle_x'] = read_int16_le(data_bytes[i], data_bytes[i+1]) / 100
            decoded['angle_y'] = read_int16_le(data_bytes[i+2], data_bytes[i+3]) / 100
            decoded['angle_z'] = read_int16_le(data_bytes[i+4], data_bytes[i+5]) / 100
            #decoded['threshold_x'] = 1 if (data_bytes[i+6] & 1) == 1 else 0
            #decoded['threshold_y'] = 1 if ((data_bytes[i+6] >> 1) & 1) == 1 else 0
            #decoded['threshold_z'] = 1 if ((data_bytes[i+6] >> 2) & 1) == 1 else 0

            degrees_hoz, degrees_vert = calculate_angles(decoded['angle_x'],decoded['angle_y'],decoded['angle_z'], 5)
            decoded['degrees_hoz'] = degrees_hoz
            decoded['degrees_vert'] = degrees_vert
            i += 7

        else:
            break
    return decoded

def em_500_udl_decoder(data_bytes):
    i = 0
    decoded = {}

    while i < len(data_bytes):
        channel_id = data_bytes[i]
        i += 1
        channel_type = data_bytes[i]
        i += 1
        if i >= len(data_bytes):
            break

       # BATTERY
        elif channel_id == 0x01 and channel_type == 0x75:
            decoded["battery"] = readInt8(data_bytes[i])
            i += 1

        # DISTANCE
        elif channel_id == 0x03 and channel_type == 0x82:
            decoded["distance"] = read_int16_le(data_bytes[i],data_bytes[i+1])
            i += 2
        else:
            break
    return decoded

def nwr_rts_decoder(data_bytes, f_port):
        decoded = {}
        if f_port == 1:
            # Temp Rail
            #temp_rail_combined = ((data_bytes[0] & 0x0F) * 16) + (data_bytes[1] / 16)
            #decoded['temp_rail'] = temp_rail_combined - 4096 if data_bytes[0] > 127 else temp_rail_combined
            if (data_bytes[0] & 0xF0 == 0xF0):
                decoded['temp_rail'] = data_bytes[0] * 16 + (data_bytes[1] / 16) - 4096 # <0 )
            else:
                decoded['temp_rail']= data_bytes[0] * 16 + (data_bytes[1] / 16) # >0

            # Temp Internal
            #temp_int_combined = ((data_bytes[2] & 0x0F) * 16) + (data_bytes[3] / 16)
            #decoded['temp_internal'] = temp_int_combined - 4096 if data_bytes[2] > 127 else temp_int_combined

            if (data_bytes[2] & 0xF0 == 0xF0):
                decoded['temp_internal'] = data_bytes[2] * 16 + (data_bytes[3] / 16) - 4096 # <0 )
            else:
                decoded['temp_internal']= data_bytes[2] * 16 + (data_bytes[3] / 16) # >0

            # battery
            decoded['batt_perc'] = ((data_bytes[4] << 8) + data_bytes[5])/100
            decoded['batt_volt'] = ((data_bytes[6] << 8) + data_bytes[7])/1000
            decoded['batt_day_remain'] = (data_bytes[8] << 8) + data_bytes[9]

            decoded['sys_time'] = f"{str(data_bytes[11]).zfill(2)}:{str(data_bytes[12]).zfill(2)}:00"

            # GPS
            lat = data_bytes[13] + (data_bytes[14] + data_bytes[15]/100 + data_bytes[16]/10000)/60
            lon = (data_bytes[17] + (data_bytes[18] + data_bytes[19]/100 + data_bytes[20]/10000)/60) * -1
            decoded['latitude'] = round(lat, 4) if lat != 0 else None
            decoded['longitude'] = round(lon, 4) if lon != 0 else None

            #angles
            Xcombined = (data_bytes[22] << 8) + data_bytes[23]
            Ycombined = (data_bytes[24] << 8) + data_bytes[25]
            Zcombined = (data_bytes[26] << 8) + data_bytes[27]

            x = Xcombined - 4096 if Xcombined > 2048 else Xcombined
            y = Ycombined - 4096 if Ycombined > 2048 else Ycombined
            z = Zcombined - 4096 if Zcombined > 2048 else Zcombined

            degrees_hoz, degrees_vert = calculate_angles(x, y, z)

            decoded['degrees_hoz'] = degrees_hoz
            decoded['degrees_vert'] = degrees_vert

            decoded['on_track'] = 80 <= degrees_vert <= 110
        
        if f_port == 2:

            status = data_bytes[0]
            decoded['a_enable'] = True if (status & 0x40) == 0x40 else False 
            decoded['on_track'] = True if (status & 0x08) == 0x08 else False

            firmware_data = data_bytes[1]
            # Extract nibbles
            major_version = (firmware_data & 0xF0) >> 4  # High nibble
            minor_version = firmware_data & 0x0F         # Low nibble
            decoded['firmware_str'] = f"v{major_version}.{minor_version:02d}"

            decoded['batt_volt'] = (data_bytes[2] << 8) + data_bytes[3]
            decoded['batt_perc'] = ((data_bytes[4]<<8) + data_bytes[5])/100
            decoded['batt_day_remain'] = (data_bytes[6] << 8) + data_bytes[7]

            decoded['k_value'] = data_bytes[8]

            if (data_bytes[9] & 0xF0 == 0xF0):
                decoded['temp_copper'] = data_bytes[9] * 16 + (data_bytes[10] / 16) - 4096 # < )
            else:
                decoded['temp_copper'] = data_bytes[9] * 16 + (data_bytes[10] / 16) # >0 

            # Temp Internal
            if (data_bytes[11] & 0xF0 == 0xF0):
                decoded['temp_int'] = data_bytes[11] * 16 + (data_bytes[12] / 16) - 4096 # < )
            else:
                decoded['temp_int'] = data_bytes[11] * 16 + (data_bytes[12] / 16) # >0 

            if (data_bytes[13] & 0xF0 == 0xF0):
                decoded['temp_rail'] = data_bytes[13] * 16 + (data_bytes[14] / 16) - 4096 # < )
            else:
                decoded['temp_rail']= data_bytes[13] * 16 + (data_bytes[14] / 16) # >0 

            if decoded['a_enable']:

                decoded['a_1_threshold'] = data_bytes[15] & 0x7F
                decoded['a_2_threshold'] = data_bytes[16] & 0x7F
                decoded['a_3_threshold'] = data_bytes[17] & 0x7F

                decoded['a_1_triggered'] = False
                decoded['a_2_triggered'] = False
                decoded['a_3_triggered'] = False

                if (data_bytes[15] & 0x80) > 0:
                    decoded['a_1_triggered'] = True

                if (data_bytes[16] & 0x80) > 0:
                    decoded['a_2_triggered'] = True

                if (data_bytes[17] & 0x80) > 0:
                    decoded['a_3_triggered'] = True  


        if f_port == 3:       
            status = data_bytes[0]
            decoded['a_enable'] = True if (status & 0x40) == 0x40 else False 
            decoded['on_track'] = True if (status & 0x08) == 0x08 else False

            firmware_data = data_bytes[1]
            # Extract nibbles
            major_version = (firmware_data & 0xF0) >> 4  # High nibble
            minor_version = firmware_data & 0x0F         # Low nibble
            decoded['firmware_str'] = f"v{major_version}.{minor_version:02d}"

            decoded['batt_volt'] = (data_bytes[2] << 8) + data_bytes[3]
            decoded['batt_perc'] = ((data_bytes[4]<<8) + data_bytes[5])/100
            decoded['batt_day_remain'] = (data_bytes[6] << 8) + data_bytes[7]

            decoded['k_value'] = data_bytes[8]

            if (data_bytes[9] & 0xF0 == 0xF0):
                decoded['temp_copper'] = data_bytes[9] * 16 + (data_bytes[10] / 16) - 4096 # < )
            else:
                decoded['temp_copper'] = data_bytes[9] * 16 + (data_bytes[10] / 16) # >0 

            # Temp Internal
            if (data_bytes[11] & 0xF0 == 0xF0):
                decoded['temp_int'] = data_bytes[11] * 16 + (data_bytes[12] / 16) - 4096 # < )
            else:
                decoded['temp_int'] = data_bytes[11] * 16 + (data_bytes[12] / 16) # >0 

            if (data_bytes[13] & 0xF0 == 0xF0):
                decoded['temp_rail'] = data_bytes[13] * 16 + (data_bytes[14] / 16) - 4096 # < )
            else:
                decoded['temp_rail']= data_bytes[13] * 16 + (data_bytes[14] / 16) # >0 

            #angles
            Xcombined = (data_bytes[15] << 8) + data_bytes[16]
            Ycombined = (data_bytes[17] << 8) + data_bytes[18]
            Zcombined = (data_bytes[19] << 8) + data_bytes[20]

            x = Xcombined - 4096 if Xcombined > 2048 else Xcombined
            y = Ycombined - 4096 if Ycombined > 2048 else Ycombined
            z = Zcombined - 4096 if Zcombined > 2048 else Zcombined

            degrees_hoz, degrees_vert = calculate_angles(x, y, z)

            decoded['degrees_hoz'] = degrees_hoz
            decoded['degrees_vert'] = degrees_vert

            # GPS
            lat = data_bytes[21] + (data_bytes[22] + data_bytes[23]/100 + data_bytes[24]/10000)/60
            lon = (data_bytes[25] + (data_bytes[26] + data_bytes[27]/100 + data_bytes[28]/10000)/60) * -1
            decoded['latitude'] = round(lat, 4) if lat != 0 else None
            decoded['longitude'] = round(lon, 4) if lon != 0 else None


            if decoded['a_enable']:

                decoded['a_1_threshold'] = data_bytes[29] & 0x7F
                decoded['a_2_threshold'] = data_bytes[30] & 0x7F
                decoded['a_3_threshold'] = data_bytes[31] & 0x7F

                decoded['a_1_triggered'] = False
                decoded['a_2_triggered'] = False
                decoded['a_3_triggered'] = False

                if (data_bytes[29] & 0x80) > 0:
                    decoded['a_1_triggered'] = True

                if (data_bytes[30] & 0x80) > 0:
                    decoded['a_2_triggered'] = True

                if (data_bytes[31] & 0x80) > 0:
                    decoded['a_3_triggered'] = True  

        return decoded



def em_320_th_decoder(data_bytes):
    i = 0
    decoded = {}

    while i < len(data_bytes):
        channel_id = data_bytes[i]
        i += 1
        channel_type = data_bytes[i]
        i += 1
        if i >= len(data_bytes):
            break

        # BATTERY
        if channel_id == 0x01 and channel_type == 0x75:
            decoded['battery'] = data_bytes[i]
            i += 1

        # TEMPERATURE
        elif channel_id == 0x03 and channel_type == 0x67:
            decoded['temperature'] = ((data_bytes[i+1] << 8) + data_bytes[i]) / 10
            i += 2

        # HUMIDITY
        elif channel_id == 0x04 and channel_type == 0x68:
            decoded['humidity'] = data_bytes[i] / 2
            i += 1

        else:
            break

    return decoded



def em_300_th_decoder(data_bytes):
    i = 0
    decoded = {}

    while i < len(data_bytes):
        channel_id = data_bytes[i]
        i += 1
        channel_type = data_bytes[i]
        i += 1
        if i >= len(data_bytes):
            break

            # BATTERY
        elif (channel_id == 0x01 and channel_type == 0x75):
            decoded["battery"] = readInt8(data_bytes[i])
            i += 1

        # TEMPERATURE
        elif (channel_id == 0x03 and channel_type == 0x67):
            decoded["temperature"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
            i += 2

        # HUMIDITY
        elif (channel_id == 0x04 and channel_type == 0x68):
            decoded["humidity"] = data_bytes[i] / 2
            i += 1

        else:
            break

    return decoded

def wts_506_decoder(data_bytes):
    decoded = {}
    i = 0

    while i < len(data_bytes):
        channel_id = data_bytes[i]
        i += 1
        channel_type = data_bytes[i]
        i += 1
        if i >= len(data_bytes):
            break

        # BATTERY
        elif channel_id == 0x01 and channel_type == 0x75:
            decoded["battery"] = readInt8(data_bytes[i])
            i += 1

        # TEMPERATURE
        elif (channel_id == 0x03 and channel_type == 0x67):
            decoded["temperature"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
            i += 2

        # HUMIDITY
        elif (channel_id == 0x04 and channel_type == 0x68):
            decoded["humidity"] = readUInt8(data_bytes[i]) / 2
            i += 1

        # WIND DIRECTION
        elif (channel_id == 0x05 and channel_type == 0x84):
            decoded["wind_direction"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
            i += 2

        # PRESSURE this should really be unisgned 16bit value
        elif (channel_id == 0x06 and channel_type == 0x73):
            decoded["pressure"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
            i += 2

        # WIND SPEED this is also an unisgned 16 bit value
        elif (channel_id == 0x07 and channel_type == 0x92):
            decoded["wind_speed"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
            i += 2

        # RAINFALL
        elif (channel_id == 0x08 and channel_type == 0xec):
            decoded["rainfall_total"] = readUInt32LE(data_bytes[i],data_bytes[i+1],data_bytes[i+2],data_bytes[i+3]) / 100
            decoded["rainfall_counter"] = readUInt8(data_bytes[i+4])
            i += 5

        else:
            break
    return decoded

def ct_101_decoder(data_bytes):

        decoded = {}
        i = 0

        while i < len(data_bytes):
            channel_id = data_bytes[i]
            i += 1
            channel_type = data_bytes[i]
            i += 1
            if i >= len(data_bytes):
                break

            # Total Current
            if channel_id == 0x03 and channel_type == 0x97:
                decoded['total_current'] = read_int32_le(data_bytes[i], data_bytes[i+1], data_bytes[i+2], data_bytes[i+3]) / 100
                i += 4

            # CURRENT
            elif channel_id == 0x04 and channel_type == 0x98:
                decoded['current'] = read_int16_le(data_bytes[i], data_bytes[i+1]) / 100
                i += 2

            # Temperature
            elif channel_id == 0x09 and channel_type == 0x67:
                decoded['temperature'] = read_int16_le(data_bytes[i], data_bytes[i+1]) / 10
                i += 2

            else:
                break

        return decoded

def em_500_swl_decoder(data_bytes):

        decoded = {}
        i = 0
        while i < len(data_bytes):
            channel_id = data_bytes[i]
            i += 1
            channel_type = data_bytes[i]
            i += 1
            if i >= len(data_bytes):
                break

            # BATTERY
            elif channel_id == 0x01 and channel_type == 0x75:
                decoded["battery"] = readInt8(data_bytes[i])
                i += 1

            # Water level
            elif (channel_id == 0x03 and channel_type == 0x77):
                decoded["water_level"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
                i += 2

            else:
                break

        return decoded

def em_400_mud_decoder(data_bytes):

        decoded = {}
        i = 0
        while i < len(data_bytes):
            channel_id = data_bytes[i]
            i += 1
            channel_type = data_bytes[i]
            i += 1
            if i >= len(data_bytes):
                break

            # BATTERY
            elif channel_id == 0x01 and channel_type == 0x75:
                decoded["battery"] = readInt8(data_bytes[i])
                i += 1

            # TEMPERATURE
            elif channel_id == 0x03 and channel_type == 0x67:
                decoded["temperature"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
                i += 2

            # DISTANCE
            elif channel_id == 0x04 and channel_type == 0x82:
                decoded["distance"] = read_int16_le(data_bytes[i],data_bytes[i+1])
                i += 2

            # POSITION
            elif channel_id == 0x05 and channel_type == 0x00:
                #decoded["position"] = readPositionType(data_bytes[i])
                i += 1

            # TEMPERATURE WITH ABNORMAL
            elif channel_id == 0x83 and channel_type == 0x67:
                #decoded["temperature"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
                #decoded["temperature_alarm"] = readAlarmType(data_bytes[i+2])
                i += 3

            # DISTANCE WITH ALARMING
            elif channel_id == 0x84 and channel_type == 0x82:
                #decoded["distance"] = read_int16_le(data_bytes[i],data_bytes[i+1])
                #decoded["distance_alarm"] = readAlarmType(data_bytes[i+2])
                i += 3

            else:
                break

        return decoded

def dl_pyr_decoder(data_bytes):
    # check to see if the protocol version matches the data structure from the device.
    version = data_bytes[0] # not used
    #PROTOCOL_VERSION = 2
    #if version != PROTOCOL_VERSION:
    #    raise ValueError(f"Protocol version {version} doesn't match v2")

    device_id = (data_bytes[1] << 8) + data_bytes[2] # not used

    flags = (data_bytes[3] << 8) + data_bytes[4] # sets which sensors are decoded

    decoded = {}
     # starting byte position

    # --- Sensor 1: Total Solar Radiation ---
    if flags & 1:
        total_radiation_raw = (data_bytes[5] << 8) + data_bytes[6]
        decoded['total_radiation'] = 3 * (total_radiation_raw / 32768 - 1) * 1000 * 5

    # --- Sensor 2: Battery Voltage ---
    if flags & 2:
        batt_v_raw = (data_bytes[7] << 8) + data_bytes[8]
        decoded['batt_volt'] = batt_v_raw / 1000

    return decoded

def dl_sth35_decoder(data_bytes):
    # check to see if the protocol version matches the data structure from the device.
    version = data_bytes[0] # not used
    #PROTOCOL_VERSION = 2
    #if version != PROTOCOL_VERSION:
    #    raise ValueError(f"Protocol version {version} doesn't match v2")
    device_id = (data_bytes[1] << 8) + data_bytes[2] # not used

    flags = (data_bytes[3] << 8) + data_bytes[4] # sets which sensors are decoded

    decoded = {}
     # starting byte position

    # --- Sensor 1: Total Solar Radiation ---
    if flags & 1:
        temperature_raw = (data_bytes[5] << 8) + data_bytes[6]
        decoded['temperature'] = round((175 * temperature_raw / 65535 - 45),1)
        humidity_raw = (data_bytes[7] << 8) + data_bytes[8]
        decoded['humidity'] = round(100 * humidity_raw / 65535,1)

    # --- Sensor 2: Battery Voltage ---
    if flags & 2:
        batt_v_raw = (data_bytes[9] << 8) + data_bytes[10]
        decoded['batt_volt'] = batt_v_raw / 1000

    return decoded

def arf_ftd_decoder(data_bytes):

    status = data_bytes[0]

    temperature_reported = (status >> 7) & 1
    gps_reported = (status >> 4) & 1
    uplink_counter_reported = (status >> 3) & 1
    downlink_counter_reported = (status >> 2) & 1
    battery_level_reported = (status >> 1) & 1
    rssi_snr_reported = (status >> 0) & 1

    pos = 1
    decoded = {}

    if temperature_reported:
        if data_bytes[pos] >> 7 & 1:
            decoded['temperature']  = (data_bytes[pos] & 127)
        else:
            decoded['temperature'] = (data_bytes[pos] & 127) - 128
        pos += 1

    if gps_reported:
        for name, data, is_latitude in (
            ("latitude", data_bytes[pos:pos + 4], True),
            ("longitude", data_bytes[pos + 4:pos + 8], False),
        ):
            digits = []

            for digit in range(7):
                byte_idx = digit // 2
                bit = 4 - (digit % 2) * 4
                digits.append(str((data[byte_idx] >> bit) & 0x0F))

            coordinate = "".join(digits) + "0"

            sign = -1 if data[3] & 0x01 else 1

            if is_latitude:
                degrees = int(coordinate[:2])
                minutes = float(coordinate[2:4] + "." + coordinate[4:])
            else:
                degrees = int(coordinate[:3])
                minutes = float(coordinate[3:5] + "." + coordinate[5:])

            decoded[name] = round(sign * (degrees + minutes / 60.0),6)

        pos += 9

    if uplink_counter_reported:
        decoded["uplink_cnt"] = data_bytes[pos]
        pos += 1

    if downlink_counter_reported:
        decoded["downlink_cnt"] = data_bytes[pos]
        pos += 1

    if battery_level_reported:
        battery_mv = (data_bytes[pos] << 8) | data_bytes[pos + 1]
        decoded["batt_volt"] = battery_mv / 1000.0
        pos += 2

    if rssi_snr_reported:
        decoded["dl_rssi"] = data_bytes[pos] *-1
        pos += 1
        decoded["dl_snr"] = data_bytes[pos]
        pos += 1

    return decoded

def at101_decoder(data_bytes):

        decoded = {}
        i = 0
        while i < len(data_bytes):
            channel_id = data_bytes[i]
            i += 1
            channel_type = data_bytes[i]
            i += 1
            if i >= len(data_bytes):
                break

            # BATTERY
            elif channel_id == 0x01 and channel_type == 0x75:
                decoded["battery"] = readInt8(data_bytes[i])
                i += 1

            # TEMPERATURE
            elif channel_id == 0x03 and channel_type == 0x67:
                decoded["temperature"] = read_int16_le(data_bytes[i],data_bytes[i+1]) / 10
                i += 2

            # LOCATION
            elif (channel_id == 0x04 or channel_id == 0x84) and channel_type == 0x88:
                decoded["latitude"] = read_int32_le(data_bytes[i], data_bytes[i+1], data_bytes[i+2], data_bytes[i+3]) / 1000000
                decoded["longitude"] = read_int32_le(data_bytes[i+4], data_bytes[i+5], data_bytes[i+6], data_bytes[i+7]) / 1000000
                decoded["status"] = data_bytes[i+8]
                i += 9

            # POSITION
            elif channel_id == 0x05 and channel_type == 0x00:
                i += 1

            # WIFI SCAN RESULT
            elif channel_id == 0x06 and channel_type == 0xd9:
                i += 9

             # TAMPER STATUS
            elif channel_id == 0x07 and channel_type == 0x00:
                i += 1

             # TEMP WITH ABNORMAL
            elif channel_id == 0x83 and channel_type == 0x67:
                i += 3
            else:
                break

        return decoded
