import time
import subprocess
import requests
import json
import logging
from pathlib import Path
import board
import busio
from adafruit_pn532.i2c import PN532_I2C

# Set up logging
logging.basicConfig(filename='nfc_plex_integration.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# JSON file to log NFC errors
error_log_file = 'nfc_errors.json'

# Function to log messages into a JSON file
def log_nfc_status(status_message, is_error=False):
    log_data = {
        "status": status_message,
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    }
    log_type = "error" if is_error else "info"
    
    try:
        with open(error_log_file, 'a') as f:
            f.write(json.dumps(log_data) + '\n')
        if is_error:
            logging.error(f"NFC {log_type} logged: {status_message}")
        else:
            logging.info(f"NFC {log_type} logged: {status_message}")
    except Exception as e:
        logging.error(f"Failed to log NFC {log_type}: {str(e)}")

# Initialize PN532 with error handling and logging success
def init_nfc_module():
    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        pn532 = PN532_I2C(i2c, debug=False)
        # Configure PN532
        pn532.SAM_configuration()
        log_nfc_status("NFC is up!")
        return pn532
    except Exception as e:
        error_message = f"NFC is down!: {str(e)}"
        log_nfc_status(error_message, is_error=True)
        return None


def check_nfc_card(pn532):
    # Check if a card is available to read
    if pn532 is not None:
        try:
            uid = pn532.read_passive_target(timeout=0.1)
            return ':'.join([hex(i)[2:].zfill(2) for i in uid]) if uid else None
        except Exception as e:
            error_message = f"Error reading NFC card: {str(e)}"
            log_nfc_error(error_message)
            return None
    return None

def run_script(script_name, use_venv=False):
    cmd = [".venv/bin/python" if use_venv else "python", script_name]
    logging.info(f"Starting script: {' '.join(cmd)}")
    return subprocess.Popen(cmd)

def open_url(url):
    try:
        response = requests.get(url, timeout=1)
        logging.info(f"Opened URL: {url}, Status: {response.status_code}")
    except requests.RequestException as e:
        logging.error(f"Failed to open URL: {url}, Error: {str(e)}")

def check_media_status():
    try:
        with open('currentlyplaying.json', 'r') as f:
            data = json.load(f)
        status = data.get('event')
        logging.debug(f"Current media status: {status}")
        return status
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Error reading media status: {str(e)}")
        return None

def ensure_script_running(process, script_name):
    if process is None or process.poll() is not None:
        logging.info(f"{script_name} is not running, starting it now")
        return run_script(script_name)
    return process

def handle_nfc_card(current_card_id, last_card_id, time_process, fb_process):
    if current_card_id != last_card_id:
        logging.info(f"New card detected: {current_card_id}")
        Path("card_id.txt").write_text(current_card_id)
        subprocess.run([".venv/bin/python", "nfc.py"])
        if time_process:
            logging.info("Stopping Time.py")
            time_process.terminate()
            time_process.wait()
        fb_process = ensure_script_running(fb_process, "fb.py")
        time_process = None
    return current_card_id, time_process, fb_process

def main():
    last_card_id = None
    card_removed_time = None
    time_process = run_script("Time.py")
    fb_process = None
    last_media_status = None

    webhook_process = run_script("webhooklistener.py")

    # Initialize NFC module
    pn532 = init_nfc_module()

    while True:
        try:
            current_card_id = check_nfc_card(pn532)
            media_status = check_media_status()

            if current_card_id:
                last_card_id, time_process, fb_process = handle_nfc_card(
                    current_card_id, last_card_id, time_process, fb_process
                )
                card_removed_time = None
            elif last_card_id:
                logging.info("NFC card removed")
                open_url("http://localhost:32500/player/playback/pause")
                if fb_process:
                    logging.info("Stopping fb.py")
                    fb_process.terminate()
                    fb_process.wait()
                time_process = ensure_script_running(time_process, "Time.py")
                card_removed_time = time.time()
                last_card_id = None

            if media_status != last_media_status:
                logging.info(f"Media status changed from {last_media_status} to {media_status}")
                last_media_status = media_status
                if media_status in ['media.play', 'media.resume']:
                    if time_process:
                        logging.info("Stopping Time.py")
                        time_process.terminate()
                        time_process.wait()
                    fb_process = ensure_script_running(fb_process, "fb.py")
                elif media_status in ['media.pause', 'media.stop'] and not current_card_id:
                    if fb_process:
                        logging.info("Stopping fb.py")
                        fb_process.terminate()
                        fb_process.wait()
                    time_process = ensure_script_running(time_process, "Time.py")

            if card_removed_time and time.time() - card_removed_time <= 180:
                new_card_id = check_nfc_card(pn532)
                if new_card_id == Path("card_id.txt").read_text().strip():
                    logging.info(f"Card re-presented within 3 minutes: {new_card_id}")
                    last_card_id = new_card_id
                    card_removed_time = None
                    if media_status == 'media.play':
                        if time_process:
                            time_process.terminate()
                            time_process.wait()
                        fb_process = ensure_script_running(fb_process, "fb.py")
                    else:
                        open_url("http://localhost:32500/player/playback/play")

            time.sleep(0.1)

        except Exception as e:
            logging.error(f"An error occurred: {str(e)}")
            time.sleep(1)

if __name__ == "__main__":
    subprocess.run(["fbset", "-fb", "/dev/fb0", "-g", "800", "480", "800", "480", "16"], check=True)
    logging.info("Starting NFC and Plex integration script")
    main()
