import os
import struct
import requests
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont
from io import BytesIO
import subprocess
import xml.etree.ElementTree as ET
import time
import textwrap
from dotenv import load_dotenv
import hashlib
import json

load_dotenv()

# Constants
FRAMEBUFFER_DEVICE = "/dev/fb0"
PLEX_URL = os.getenv("PLEX_URL")
PLEX_BASE_URL = os.getenv("PLEX_BASE_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")

# Global variables for caching
last_json_update_time = 0
cached_audio_info = {}

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'image_cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# Font paths
FONT_REGULAR = "/usr/share/fonts/truetype/sf-pro/SF-Pro-Display-Regular.otf"
FONT_BOLD = "/usr/share/fonts/truetype/sf-pro/SF-Pro-Display-Bold.otf"

# Icon paths
LOSSLESS_ICON_PATH = "lossless_blk.png"
HIRES_ICON_PATH = "hires.jpg"

# Fallback fonts
FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

# Global variables
current_track_id = None
current_album_id = None
last_display_update = 0
framebuffer_info = None
current_album_cache_files = []

def get_cache_path(url, suffix=''):
    filename = hashlib.md5(url.encode()).hexdigest() + suffix + '.png'
    return os.path.join(CACHE_DIR, filename)

def cache_image(url, image):
    global current_album_cache_files
    cache_path = get_cache_path(url)
    image.save(cache_path, 'PNG')
    current_album_cache_files.append(cache_path)

def get_cached_image(url):
    cache_path = get_cache_path(url)
    if os.path.exists(cache_path):
        return Image.open(cache_path)
    return None

def cache_blurred_background(url, image):
    global current_album_cache_files
    cache_path = get_cache_path(url, '_blurred')
    image.save(cache_path, 'PNG')
    current_album_cache_files.append(cache_path)

def get_cached_blurred_background(url):
    cache_path = get_cache_path(url, '_blurred')
    if os.path.exists(cache_path):
        return Image.open(cache_path)
    return None

def delete_cached_images():
    global current_album_cache_files
    for cache_file in current_album_cache_files:
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
                print(f"Deleted cached image: {cache_file}")
            except Exception as e:
                print(f"Error deleting cache file {cache_file}: {e}")
    current_album_cache_files = []

def get_font(preferred_path, size, fallback_paths=FALLBACK_FONTS):
    if os.path.exists(preferred_path):
        return ImageFont.truetype(preferred_path, size)
    for path in fallback_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    print(f"Warning: No suitable font found. Using default font.")
    return ImageFont.load_default()

def get_framebuffer_info():
    global framebuffer_info
    if framebuffer_info is None:
        try:
            output = subprocess.check_output("fbset", shell=True).decode()
            for line in output.splitlines():
                if "geometry" in line:
                    parts = line.split()
                    framebuffer_info = (int(parts[1]), int(parts[2]))
                    return framebuffer_info
        except Exception as e:
            print(f"Failed to get framebuffer info: {e}")
            return None, None
    return framebuffer_info

def resize_image_aspect_ratio(img, max_width, max_height):
    img_ratio = img.width / img.height
    target_ratio = max_width / max_height
    if img_ratio > target_ratio:
        new_width = max_width
        new_height = int(max_width / img_ratio)
    else:
        new_height = max_height
        new_width = int(max_height * img_ratio)
    return img.resize((new_width, new_height), Image.LANCZOS)

def convert_image_to_rgb565(img):
    img = img.convert('RGB')
    img_data = np.array(img)
    r = (img_data[:, :, 0] >> 3).astype(np.uint16)
    g = (img_data[:, :, 1] >> 2).astype(np.uint16)
    b = (img_data[:, :, 2] >> 3).astype(np.uint16)
    return ((r << 11) | (g << 5) | b).flatten()

def fetch_image_from_url(url):
    cached_image = get_cached_image(url)
    if cached_image:
        return cached_image

    try:
        response = requests.get(url)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            cache_image(url, img)
            return img
    except Exception as e:
        print(f"Error fetching image: {e}")
    return None

def create_blurred_background(img, width, height, url):
    cached_background = get_cached_blurred_background(url)
    if cached_background:
        return cached_background

    try:
        blurred_img = img.resize((width, height)).filter(ImageFilter.GaussianBlur(30))
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 128))
        result = Image.alpha_composite(blurred_img.convert('RGBA'), overlay).convert('RGB')
        cache_blurred_background(url, result)
        return result
    except Exception as e:
        print(f"Error creating blurred background: {e}")
    return None

def is_lossless(codec):
    lossless_codecs = ['alac', 'flac', 'wav', 'ape', 'dsd']
    return codec.lower() in lossless_codecs

def is_hires(bit_depth, sample_rate):
    return int(bit_depth) > 16 or int(sample_rate) > 48000

def get_track_info_from_plex():
    global last_json_update_time, cached_audio_info

    try:
        # Check if currentlyplaying.json has been modified
        json_file_path = 'currentlyplaying.json'
        current_json_time = os.path.getmtime(json_file_path)

        # Read data from currentlyplaying.json
        with open(json_file_path, 'r') as f:
            current_playing = json.load(f)

        # Extract relevant information from the JSON
        metadata = current_playing.get('metadata', {})
        player = current_playing.get('player', {})

        new_track_id = metadata.get('ratingKey')
        thumb = metadata.get('thumb')
        title = metadata.get('title', 'Unknown Title')
        albartist = metadata.get('grandparentTitle', 'Unknown Artist')
        artist = metadata.get('originalTitle', albartist)
        album = metadata.get('parentTitle', 'Unknown Album')
        album_id = metadata.get('parentRatingKey')

        # Check if we need to update the audio info
        if current_json_time > last_json_update_time or new_track_id not in cached_audio_info:
            # Fetch XML data for bit depth and sample rate
            response = requests.get(f"{PLEX_URL}", timeout=5)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                for track in root.findall("Track"):
                    if track.get("ratingKey") == new_track_id:
                        media = track.find("Media")
                        if media is not None:
                            part = media.find("Part")
                            if part is not None:
                                stream = part.find("Stream")
                                
                                audio_codec = part.get("container", "Unknown")
                                if stream is not None:
                                    
                                    bit_depth = stream.get("bitDepth", "16")
                                    sample_rate = stream.get("samplingRate", "44100")
                                    audio_data = f"{bit_depth}bit/{int(sample_rate)/1000:.1f}kHz"
                                    cached_audio_info[new_track_id] = {
                                        "audio_data": audio_data,
                                        "audio_codec": audio_codec,
                                        "bit_depth": bit_depth,
                                        "sample_rate": sample_rate
                                    }
                                    break
            last_json_update_time = current_json_time
        else:
            # Use cached audio info
            audio_info = cached_audio_info.get(new_track_id, {})
            audio_data = audio_info.get("audio_data", "Unknown Format")
            audio_codec = audio_info.get("audio_codec", "Unknown")
            bit_depth = audio_info.get("bit_depth", "16")
            sample_rate = audio_info.get("sample_rate", "44100")
        print(audio_codec)
        is_lossless_audio = is_lossless(audio_codec)
        is_hires_audio = is_hires(bit_depth, sample_rate)

        if thumb:
            thumb_url = f"{PLEX_BASE_URL}{thumb}?X-Plex-Token={PLEX_TOKEN}"
        else:
            thumb_url = None

        return {
            "track_id": new_track_id,
            "album_id": album_id,
            "thumb_url": thumb_url,
            "title": title,
            "artist": artist,
            "album": album,
            "audioData": audio_data,
            "isLossless": is_lossless_audio,
            "isHiRes": is_hires_audio
        }
    except Exception as e:
        print(f"Error fetching or parsing Plex data: {e}")
    return None


def load_icon(icon_path, size=(20, 20)):
    try:
        icon = Image.open(icon_path).convert("RGBA")
        return icon.resize(size, Image.LANCZOS)
    except Exception as e:
        print(f"Error loading icon {icon_path}: {e}")
        return None

def wrap_text(text, font, max_width):
    if not text:
        return []
    lines = []
    words = text.split()
    while words:
        line = ''
        while words and font.getbbox(line + words[0])[2] <= max_width:
            line += (words.pop(0) + ' ')
        lines.append(line.strip())
    return lines

def add_corners(im, rad):
    circle = Image.new('L', (rad * 2, rad * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, rad * 2, rad * 2), fill=255)
    alpha = Image.new('L', im.size, 255)
    w, h = im.size
    alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
    alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
    alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
    alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
    im.putalpha(alpha)
    return im

def display_image_with_track_details(track_info):
    width, height = get_framebuffer_info()
    if not width or not height:
        print("Invalid framebuffer size.")
        return None

    if track_info["thumb_url"]:
        img = fetch_image_from_url(track_info["thumb_url"])
    else:
        img = Image.new('RGB', (300, 300), color='black')
    
    if not img:
        print("Failed to fetch image or create default.")
        return None

    blurred_background = create_blurred_background(img, width, height, track_info["thumb_url"])
    if not blurred_background:
        print("Failed to create blurred background.")
        return None

    draw = ImageDraw.Draw(blurred_background)

    title_font = get_font(FONT_BOLD, 36)
    artist_font = get_font(FONT_REGULAR, 28)
    details_font = get_font(FONT_REGULAR, 20)

    padding = 20
    left_side_width = width // 2
    album_art_size = int(min(left_side_width, height) * 0.9)
    album_art_x = (left_side_width - album_art_size) // 2
    album_art_y = (height - album_art_size) // 2

    resized_img = resize_image_aspect_ratio(img, album_art_size, album_art_size)
    resized_img = resized_img.convert("RGBA")
    rounded_img = add_corners(resized_img, 20)
    blurred_background.paste(rounded_img, (album_art_x, album_art_y), rounded_img)

    text_area_x = left_side_width + padding
    text_area_width = width - text_area_x - padding
    text_area_center = text_area_x + (text_area_width // 2)

    def draw_centered_text(text, font, y, color):
        lines = wrap_text(text, font, text_area_width)
        for line in lines:
            line_width = font.getbbox(line)[2]
            x = text_area_center - (line_width // 2)
            draw.text((x, y), line, font=font, fill=color)
            y += font.size + 5
        return y

    text_y = padding + (height // 4)
    text_y = draw_centered_text(track_info["title"], title_font, text_y, (255, 255, 255))
    text_y += 20
    text_y = draw_centered_text(track_info["artist"], artist_font, text_y, (200, 200, 200))
    text_y += 20
    text_y = draw_centered_text(track_info["album"], details_font, text_y, (150, 150, 150))
    text_y += 10

    draw_centered_text(track_info["audioData"], details_font, text_y, (150, 150, 150))

    lossless_icon_size = (50, 30)
    hires_icon_size = (30, 30)
    icon_padding = 10
    icon_y = height - max(lossless_icon_size[1], hires_icon_size[1]) - icon_padding

    lossless_icon = None
    hires_icon = None

    if track_info["isLossless"]:
        lossless_icon = load_icon(LOSSLESS_ICON_PATH, size=lossless_icon_size)

    if track_info["isHiRes"]:
        hires_icon = load_icon(HIRES_ICON_PATH, size=hires_icon_size)

    if lossless_icon and hires_icon:
        lossless_x = width - lossless_icon_size[0] - icon_padding
        hires_x = lossless_x - hires_icon_size[0] - icon_padding
    elif lossless_icon:
        lossless_x = width - lossless_icon_size[0] - icon_padding
    elif hires_icon:
        hires_x = width - hires_icon_size[0] - icon_padding

    if lossless_icon:
        blurred_background.paste(lossless_icon, (lossless_x, icon_y), lossless_icon)

    if hires_icon:
        blurred_background.paste(hires_icon, (hires_x, icon_y), hires_icon)
    return blurred_background

def write_image_to_framebuffer(rgb565_image):
    try:
        with open(FRAMEBUFFER_DEVICE, "wb") as fb:
            fb.write(struct.pack("H" * len(rgb565_image), *rgb565_image))
    except Exception as e:
        print(f"Error writing to framebuffer: {e}")

def main_loop():
    global current_track_id, current_album_id, last_display_update, current_album_cache_files
    check_interval = 1

    while True:
        try:
            # Check if the JSON file has been modified before calling get_track_info_from_plex
            json_file_path = 'currentlyplaying.json'
            current_json_time = os.path.getmtime(json_file_path)
            
            if current_json_time > last_json_update_time:
                track_info = get_track_info_from_plex()
                
                if track_info:
                    new_track_id = track_info["track_id"]
                    new_album_id = track_info.get("album_id")
                    
                    if new_album_id != current_album_id:
                        if current_album_id is not None:
                            delete_cached_images()
                        current_album_id = new_album_id
                        current_album_cache_files = []

                    if new_track_id != current_track_id or (time.time() - last_display_update > 300) or current_json_time > last_json_update_time:
                        current_track_id = new_track_id
                        image = display_image_with_track_details(track_info)
                        if image:
                            rgb565_image = convert_image_to_rgb565(image)
                            write_image_to_framebuffer(rgb565_image)
                            last_display_update = time.time()
                            print(f"Display updated for track: {track_info['title']} by {track_info['artist']}")
                        else:
                            print("Failed to create display image.")
                else:
                    print("No track info available or error in fetching data.")
            else:
                # No change in JSON, no need to update display
                pass
        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
        
        time.sleep(check_interval)

if __name__ == "__main__":
    main_loop()
