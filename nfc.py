import board
import busio
from adafruit_pn532.i2c import PN532_I2C
import time
import re
import sys
import urllib.request

# Define Key B (default for many cards is FFFFFFFFFFFF)
KEY_B = b'\xFF\xFF\xFF\xFF\xFF\xFF'

# TLV Tag Constants
TLV_TAG_NULL = 0x00
TLV_TAG_NDEF = 0x03
TLV_TAG_TERMINATOR = 0xFE

# I2C setup for Raspberry Pi
i2c = busio.I2C(board.SCL, board.SDA)

# PN532 setup
pn532 = PN532_I2C(i2c, debug=False)
pn532.SAM_configuration()

def read_ndef_data(uid):
    ndef_data = b''
    for block_num in range(4, 64):  # Read from block 4 to 63
        retry_count = 0
        while retry_count < 3:  # Retry up to 3 times
            try:
                if pn532.mifare_classic_authenticate_block(uid, block_num, 0x61, KEY_B):
                    block_data = pn532.mifare_classic_read_block(block_num)
                    if block_data is not None:
                        ndef_data += block_data
                        break  # Successfully read the block, move to the next
                    else:
                        retry_count += 1
                else:
                    retry_count += 1
            except Exception:
                retry_count += 1
            
            time.sleep(0.1)  # Short delay before retry
        
        if retry_count == 3:
            continue  # Skip this block if all retries failed
        
        # Check for NDEF message end
        if TLV_TAG_TERMINATOR in block_data:
            break

    return ndef_data

def parse_ndef_message(ndef_data):
    if ndef_data[0] != TLV_TAG_NDEF:
        return None

    # NDEF message length (skip TLV tag and length field)
    ndef_length = ndef_data[1]
    if ndef_length == 0xFF:  # 3-byte length
        ndef_start = 4
    else:
        ndef_start = 2

    # Extract the entire NDEF message
    ndef_message = ndef_data[ndef_start:]  # Read all data after length field

    # Parse the NDEF record
    return parse_ndef_record(ndef_message)

def parse_ndef_record(record):
    if len(record) < 3:
        return None
    
    type_length = record[1]
    
    if len(record) < 3 + type_length:
        return None
    
    record_type = record[3:3 + type_length]
    payload = record[3 + type_length:]  # Read all remaining data as payload
    
    if record_type == b'U':
        return decode_uri(payload)
    return None

def decode_uri(uri_bytes):
    uri_prefix_map = {
        0x00: '', 0x01: 'http://www.', 0x02: 'https://www.',
        0x03: 'http://', 0x04: 'https://',
    }
    prefix_code = uri_bytes[0]
    uri_body = uri_bytes[1:].decode('utf-8', errors='ignore')
    full_uri = uri_prefix_map.get(prefix_code, '') + uri_body
    
    # Remove all "@" symbols
    cleaned_uri = full_uri.replace("@", "")
    
    # Replace "listen.plex.tv" with "localhost:32500"
    final_uri = cleaned_uri.replace("https://listen.plex.tv", "http://localhost:32500")
    
    return final_uri

def clean_url(url):
    # Check and remove control characters like null characters and other non-printable characters
    cleaned_url = re.sub(r'[\x00-\x1f\x7f]', '', url)  # Remove control characters
    return cleaned_url

def main():
    print("Waiting for NFC card...", file=sys.stderr)
    
    while True:
        uid = pn532.read_passive_target(timeout=0.5)
        if uid is not None:
            ndef_data = read_ndef_data(uid)
            if ndef_data:
                decoded_uri = parse_ndef_message(ndef_data)
                if decoded_uri:
                    print(decoded_uri)  # Print only the final decoded URL
                    urlclean=clean_url(decoded_uri)
                    print (urlclean)
                    urllib.request.urlopen(urlclean)
                    break  # Exit the loop after processing one card
                else:
                    print("No valid NDEF message found or unable to decode URI.", file=sys.stderr)
                    break
            else:
                print("No NDEF data found.", file=sys.stderr)
                break
        time.sleep(0.1)

#def read_card_id():
#    # Initialize I2C bus and PN532 module
#    i2c = busio.I2C(board.SCL, board.SDA)
#    pn532 = PN532_I2C(i2c, debug=False)

#    # Configure the PN532 to use the NFC card reading mode
#    pn532.SAM_configuration()
#
#    print("Waiting for an NFC card...")
#
#    # Wait for a card to be presented
#    uid = None
#    while uid is None:
#        uid = pn532.read_passive_target()
#        time.sleep(0.5)  # Prevent excessive polling

    # Convert the UID to a hex string
#    card_id = ''.join(format(x, '02x') for x in uid)
#    print(f"Card ID: {card_id}")

#    # Store the card ID in a file
#    with open("card_id.txt", "w") as file:
#        file.write(card_id)
#        print("Card ID written to card_id.txt")


if __name__ == "__main__":
    main()
#    read_card_id()
