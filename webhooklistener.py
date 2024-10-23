import json
import logging
from collections import defaultdict
from datetime import datetime
from flask import Flask, request
from werkzeug.serving import run_simple

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CURRENT_PLAYING_FILE = 'currentlyplaying.json'
TARGET_PLAYER = "Your_Headless_plexamp_player_name"

# Use in-memory storage for stats to reduce disk writes
stats = {
    'total_requests': 0,
    'successful_requests': 0,
    'error_requests': 0,
    'events': defaultdict(int),
    'last_reset': datetime.now()
}

def write_current_playing(data):
    player = data.get('Player', {})
    if player.get('title') != TARGET_PLAYER:
        return

    current_playing = {
        'event': data.get('event'),
        'player': player,
        'metadata': data.get('Metadata', {}),
        'timestamp': datetime.now().isoformat()
    }

    with open(CURRENT_PLAYING_FILE, 'w') as f:
        json.dump(current_playing, f, indent=2)
    
    app.logger.info(f"Updated {CURRENT_PLAYING_FILE} for {TARGET_PLAYER}")

@app.route('/webhook', methods=['POST'])
def webhook():
    stats['total_requests'] += 1
    
    if request.method == 'POST':
        try:
            payload = request.form.get('payload')
            if not payload:
                raise ValueError("No payload found in the form data")

            data = json.loads(payload)
            event_type = data.get('event')
            if not event_type:
                raise ValueError("No event type in the received data")

            stats['events'][event_type] += 1
            
            if event_type in ['media.play', 'media.resume', 'media.pause', 'media.stop']:
                write_current_playing(data)
            
            stats['successful_requests'] += 1
            return 'OK', 200
        
        except (json.JSONDecodeError, ValueError) as e:
            app.logger.error(str(e))
            stats['error_requests'] += 1
            return 'Bad Request: ' + str(e), 400
        except Exception as e:
            app.logger.error(f"An unexpected error occurred: {str(e)}")
            stats['error_requests'] += 1
            return 'Internal Server Error', 500

@app.route('/stats', methods=['GET'])
def get_stats():
    return json.dumps(stats, indent=2, default=str), 200, {'Content-Type': 'application/json'}

if __name__ == '__main__':
    app.logger.info("Starting Plex webhook listener...")
    run_simple('0.0.0.0', 33500, app, use_reloader=False, threaded=True)
