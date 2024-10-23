#!/usr/bin/env python3
		  
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageEnhance
import fcntl
import struct
import os
import time
from datetime import datetime, timedelta
import unidecode
from dotenv import load_dotenv
import pytz
import ephem
import math
from io import BytesIO
import geocoder
import tzlocal
import hashlib
import json

load_dotenv()

# Constants
API_KEY = os.getenv("OPENWEATHER_API_KEY")
FRAMEBUFFER = "/dev/fb0"
FONT_PATH = "/home/jay/led.ttf" #"/usr/share/fonts/truetype/sf-pro/SF-Pro-Display-Regular.otf" 
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# Cache expiration times
WEATHER_CACHE_EXPIRY = 600  # 10 minutes
WALLPAPER_CACHE_EXPIRY = 86400  # 24 hours

# Global variables for caching
cached_weather = None
cached_weather_time = 0
cached_wallpaper = None
cached_wallpaper_time = 0
cached_framebuffer_info = None

error_log_file = 'nfc_errors.json'

def get_latest_nfc_error():
    try:
        with open(error_log_file, 'r') as f:
            # Read each line and load as JSON
            error_logs = [json.loads(line) for line in f.readlines()]
            
        if not error_logs:
            return None, None

        # Find the log entry with the latest timestamp
        latest_log = max(error_logs, key=lambda x: datetime.strptime(x['timestamp'], '%Y-%m-%d %H:%M:%S'))
        return latest_log['status'], latest_log['timestamp']
    
    except FileNotFoundError:
        return None, None  # File does not exist
    except json.JSONDecodeError:
        return None, None  # Malformed JSON file
    except Exception as e:
        return f"Error while reading log file: {str(e)}", None



def get_cache_path(prefix, identifier):
    return os.path.join(CACHE_DIR, f"{prefix}_{hashlib.md5(identifier.encode()).hexdigest()}.png")

def cache_image(prefix, identifier, image):
    cache_path = get_cache_path(prefix, identifier)
    image.save(cache_path, 'PNG')
    return cache_path

def get_cached_image(prefix, identifier):
    cache_path = get_cache_path(prefix, identifier)
    if os.path.exists(cache_path):
        return Image.open(cache_path)
    return None

def trim_transparent(image):
    bbox = image.getbbox()
    return image.crop(bbox) if bbox else image

def fetch_weather_icon(icon_code, size=(20, 20)):
    cached_icon = get_cached_image("weather_icon", icon_code)
    if cached_icon:
        return cached_icon

    url = f"http://openweathermap.org/img/wn/{icon_code}@4x.png"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            original_icon = Image.open(BytesIO(response.content)).convert('RGBA')
            trimmed_icon = trim_transparent(original_icon)
            scale_factor = min(size[0] / trimmed_icon.width, size[1] / trimmed_icon.height)
            new_size = (int(trimmed_icon.width * scale_factor), int(trimmed_icon.height * scale_factor))
            resized_icon = trimmed_icon.resize(new_size, Image.LANCZOS)
            background = Image.new('RGBA', size, (255, 255, 255, 0))
            position = ((size[0] - new_size[0]) // 2, (size[1] - new_size[1]) // 2)
            background.paste(resized_icon, position, resized_icon)
            cache_image("weather_icon", icon_code, background)
            return background
    except Exception as e:
        print(f"Error fetching weather icon: {e}")
    return None

def get_weather(lat, lon, api_key):
    global cached_weather, cached_weather_time
    current_time = time.time()
    
    if cached_weather and (current_time - cached_weather_time) < WEATHER_CACHE_EXPIRY:
        return cached_weather

    try:
        response = requests.get(f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric')
        data = response.json()
        temperature = data['main']['temp']
        weather_description = data['weather'][0]['description']
        weather_icon_code = data['weather'][0]['icon']
        sunrise = data['sys']['sunrise']
        sunset = data['sys']['sunset']
        
        timezone_str = tzlocal.get_localzone_name()
        local_sunrise = unix_to_local(sunrise, timezone_str)
        local_sunset = unix_to_local(sunset, timezone_str)
        
        cached_weather = (temperature, weather_description, weather_icon_code, local_sunrise, local_sunset)
        cached_weather_time = current_time
        return cached_weather
    except:
        return 'N/A', 'N/A', '01d', None, None

def get_location():
    return os.getenv("LAT"), os.getenv("LON"), os.getenv("CITY")

def unix_to_local(utc_timestamp, timezone_str):
    local_timezone = pytz.timezone(timezone_str)
    utc_time = datetime.utcfromtimestamp(utc_timestamp).replace(tzinfo=pytz.utc)
    return utc_time.astimezone(local_timezone)

def get_solar_elevation_angle(latitude, longitude):
    observer = ephem.Observer()
    observer.lat, observer.lon = str(latitude), str(longitude)
    observer.date = datetime.utcnow()
    sun = ephem.Sun(observer)
    return math.degrees(sun.alt)

def get_bing_wallpaper():
    global cached_wallpaper, cached_wallpaper_time
    current_time = time.time()
    now = datetime.now()
    is_midnight = now.hour == 0 and now.minute == 0
    
    if cached_wallpaper and ((current_time - cached_wallpaper_time) < WALLPAPER_CACHE_EXPIRY) and not is_midnight:
        return cached_wallpaper

    try:
        bing_url = "https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=1"
        response = requests.get(bing_url)
        data = response.json()
        wallpaper_url = "https://www.bing.com" + data["images"][0]["url"]
        wallpaper_image = requests.get(wallpaper_url, stream=True)
        wallpaper = Image.open(wallpaper_image.raw)
        cached_wallpaper = wallpaper
        cached_wallpaper_time = current_time
        return wallpaper
    except:
        return Image.new("RGB", (800, 480), "black")

def adjust_brightness(image, brightness_factor):
    enhancer = ImageEnhance.Brightness(image)
    return enhancer.enhance(brightness_factor)

def get_framebuffer_info(fbdev):
    global cached_framebuffer_info
    if cached_framebuffer_info:
        return cached_framebuffer_info

    with open(fbdev, "rb") as fb:
        fmt = "8I12I36I"
        FBIOGET_VSCREENINFO = 0x4600
        screen_info = fcntl.ioctl(fb, FBIOGET_VSCREENINFO, b"\0" * struct.calcsize(fmt))
        data = struct.unpack(fmt, screen_info)
        cached_framebuffer_info = (data[0], data[1], data[6])
        return cached_framebuffer_info

def calculate_font_size(width, height):
    max_font_size = 100
    optimal_height = int(height * 0.9)
    optimal_width = int(width * 0.9)

    for font_size in range(max_font_size, 0, -1):
        font = ImageFont.truetype(FONT_PATH, font_size)
        text_bbox = font.getbbox("00:00:00")
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        if text_height <= optimal_height and text_width <= optimal_width:
            return font_size

    return 12

def calculate_contrast_color(image):
    stat = ImageStat.Stat(image)
    r, g, b = stat.mean[:3]
    return (0, 0, 0) if (r * 0.299 + g * 0.587 + b * 0.114) > 186 else (255, 255, 255)

def add_radial_vignette(image, center_perc=(0.8, 0.8), radius_perc=0.5, intensity=0.8):
    width, height = image.size
    center = (int(width * center_perc[0]), int(height * center_perc[1]))
    radius = int(min(width, height) * radius_perc)

    mask = Image.new('L', (width, height), 255)
    draw = ImageDraw.Draw(mask)

    for r in range(radius, -1, -1):
        alpha = int(255 * (1 - (r / radius) ** 2) * intensity)
        draw.ellipse([center[0] - r, center[1] - r, center[0] + r, center[1] + r], fill=255-alpha)

    return Image.composite(image, Image.new('RGB', image.size, 'black'), mask)

def create_time_image(width, height):
    wallpaper = get_bing_wallpaper()
    wallpaper = wallpaper.resize((width, height))
    wallpaper = add_radial_vignette(wallpaper, center_perc=(0.8, 1.0), radius_perc=0.7, intensity=0.6)

    image = wallpaper.copy()

    current_time = time.strftime("%H:%M")
    today = datetime.today()
    current_day = today.strftime("%a, %b %d, %Y")

    lat, lon, city = get_location()
    try:
        lat, lon = float(lat), float(lon)
    except ValueError:
        print("Invalid latitude or longitude values.")
        lat, lon = 0.0, 0.0

    temperature, weather_description, weather_icon_code, local_sunrise, local_sunset = get_weather(lat, lon, API_KEY)

    local_timezone = local_sunrise.tzinfo if local_sunrise else pytz.utc
    nowtime = datetime.now(local_timezone)

    if local_sunrise and local_sunset and not (local_sunrise <= nowtime <= local_sunset):
        wallpaper = adjust_brightness(wallpaper, 0.15)

    rounded_temperature = round(temperature) if isinstance(temperature, (int, float)) else 'N/A'
    formatted_temperature = f"{rounded_temperature}{chr(176)}C" if rounded_temperature != 'N/A' else "N/A"

    # Fetch the latest NFC error and timestamp
    error, timestamp = get_latest_nfc_error()

    if "NFC is down!" in error:
        nfcerror=f"{error}"
    if "NFC is up!" in error:
        nfcerror=" "

    sun_elevation = get_solar_elevation_angle(lat, lon)
    pluto_time_status = "Pluto Time!" if -1.5 <= sun_elevation <= 1.5 else f"{nfcerror}" #To display either Pluto Time or NFC status

    image = wallpaper.copy()
    draw = ImageDraw.Draw(image)

    font_color = calculate_contrast_color(image)

    font_size = calculate_font_size(width, height)
    font = ImageFont.truetype(FONT_PATH, size=font_size)

    day_font_size = int(font_size * 0.40)
    day_font = ImageFont.truetype(FONT_PATH, size=day_font_size)

    temp_font_size = int(font_size * 0.35)
    temp_font = ImageFont.truetype(FONT_PATH, size=temp_font_size)

    pluto_font_size = int(font_size * 0.20)
    pluto_font = ImageFont.truetype(FONT_PATH, size=pluto_font_size)

    padding = 10

    time_bbox = font.getbbox(current_time)
    time_width = time_bbox[2] - time_bbox[0]
    time_height = time_bbox[3] - time_bbox[1]
    time_x = width - time_width - padding
    time_y = height - time_height - padding

    day_bbox = day_font.getbbox(current_day)
    day_width = day_bbox[2] - day_bbox[0]
    day_height = day_bbox[3] - day_bbox[1]
    day_x = width - day_width - padding
    day_y = time_y - day_height - padding

    pluto_time_bbox = pluto_font.getbbox(pluto_time_status)
    pluto_time_width = pluto_time_bbox[2] - pluto_time_bbox[0]
    pluto_time_x = (width - pluto_time_width) - padding
    pluto_time_y = day_y - pluto_time_bbox[3] - padding

    icon_size = (50, 50)
    weather_icon = fetch_weather_icon(weather_icon_code, size=icon_size)
    icon_x = day_x + 20
    icon_y = time_y + 30

    temp_bbox = temp_font.getbbox(formatted_temperature)
    temp_width = temp_bbox[2] - temp_bbox[0]
    temp_height = temp_bbox[3] - temp_bbox[1]
    temp_x = icon_x + (icon_size[0] - temp_width) // 2
    temp_y = icon_y - temp_height - padding // 1.5

    draw.text((pluto_time_x, pluto_time_y), pluto_time_status, font=pluto_font, fill=font_color)
    draw.text((day_x, day_y), current_day, font=day_font, fill=font_color)
    draw.text((time_x, time_y), current_time, font=font, fill=font_color)
    draw.text((temp_x, temp_y), formatted_temperature, font=temp_font, fill=font_color)

    if weather_icon:
        image.paste(weather_icon, (icon_x, icon_y), weather_icon)
    
    return image

def display_time_on_framebuffer(fbdev):
    fb_width, fb_height, fb_bpp = get_framebuffer_info(fbdev)
    image = create_time_image(fb_width, fb_height)

    img_data = np.array(image, dtype=np.uint8)
    r, g, b = img_data[:, :, 0], img_data[:, :, 1], img_data[:, :, 2]

    if fb_bpp == 32:
        fb_data = (r.astype(np.uint32) << 16) | (g.astype(np.uint32) << 8) | b.astype(np.uint32)
    elif fb_bpp == 16:
        fb_data = ((r.astype(np.uint16) & 0xF8) << 8) | ((g.astype(np.uint16) & 0xFC) << 3) | (b.astype(np.uint16) >> 3)
    else:
        raise ValueError(f"Unsupported bits per pixel: {fb_bpp}")

    fb_data = np.array(fb_data, dtype=np.uint32 if fb_bpp == 32 else np.uint16)

    with open(fbdev, "wb") as fb:
        fb.write(fb_data.tobytes())

def time_until_next_minute():
    current_time = time.localtime()
    return 60 - current_time.tm_sec


def main():
    print("Starting Time.")
    print(f"API Key from env: {API_KEY}")
    if not API_KEY:
        print("API key not found. Please check your .env file or environment variables.")
        return

    error_count = 0
    max_errors = 5
    error_delay = 60  # seconds

    while True:
        try:
            display_time_on_framebuffer(FRAMEBUFFER)
            sleep_duration = time_until_next_minute()
            time.sleep(sleep_duration)
            error_count = 0  # Reset error count on successful execution
        except Exception as e:
            error_count += 1
            print(f"Error occurred: {e}")
            print(f"Error count: {error_count}")
            
            if error_count >= max_errors:
                print(f"Max errors reached. Sleeping for {error_delay} seconds before retrying.")
                time.sleep(error_delay)
                error_count = 0  # Reset error count after delay
            else:
                print("Retrying in 5 seconds...")
                time.sleep(5)

def cleanup_cache():
    """Remove old cache files."""
    current_time = time.time()
    for filename in os.listdir(CACHE_DIR):
        file_path = os.path.join(CACHE_DIR, filename)
        if os.path.isfile(file_path):
            file_age = current_time - os.path.getmtime(file_path)
            if file_age > WALLPAPER_CACHE_EXPIRY:
                os.remove(file_path)
                print(f"Removed old cache file: {filename}")

if __name__ == "__main__":
    cleanup_cache()  # Clean up old cache files before starting
    main()
