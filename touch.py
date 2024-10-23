import evdev
import time
import requests

TOUCHSCREEN_DEVICE = '/dev/input/event0'
DOUBLE_TAP_MAX_DELAY = 0.3
DOUBLE_TAP_MIN_DELAY = 0.05
SWIPE_THRESHOLD = 100
SWIPE_TIME = 0.5
ACTION_COOLDOWN = 0.5

last_action_time = 0
touch_points = {}
is_playing = False

class TouchPoint:
    def __init__(self, id, x=None, y=None):
        self.id = id
        self.start_x = x
        self.start_y = y
        self.end_x = x
        self.end_y = y
        self.start_time = time.time()
        self.end_time = self.start_time
        self.tap_count = 0
        self.last_tap_time = None

    def update_position(self, x, y):
        if self.start_x is None and x is not None:
            self.start_x = x
        if self.start_y is None and y is not None:
            self.start_y = y
        if x is not None:
            self.end_x = x
        if y is not None:
            self.end_y = y
        self.end_time = time.time()

    def reset(self):
        self.start_x = self.end_x
        self.start_y = self.end_y
        self.start_time = self.end_time
        self.tap_count = 0
        self.last_tap_time = None

def open_url(url):
    try:
        print(f"Attempting to open URL: {url}")
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        print(f"URL opened successfully. Status code: {response.status_code}")
        print(f"Response content: {response.text[:100]}...")
    except requests.exceptions.RequestException as e:
        print(f"Failed to open URL: {e}")
        print(f"Error type: {type(e).__name__}")
        if hasattr(e, 'response'):
            print(f"Response status code: {e.response.status_code}")
            print(f"Response content: {e.response.text[:100]}...")

def handle_gestures(touch_point):
    global last_action_time, is_playing
    current_time = time.time()

    print(f"Handling gesture for touch ID: {touch_point.id}")
    print(f"Start position: ({touch_point.start_x}, {touch_point.start_y})")
    print(f"End position: ({touch_point.end_x}, {touch_point.end_y})")
    print(f"Gesture duration: {touch_point.end_time - touch_point.start_time:.2f} seconds")

    if current_time - last_action_time < ACTION_COOLDOWN:
        print("Cooldown active. Skipping gesture.")
        return

    # Swipe detection
    if touch_point.start_x is not None and touch_point.start_y is not None and \
       touch_point.end_x is not None and touch_point.end_y is not None:
        delta_x = touch_point.end_x - touch_point.start_x
        delta_y = touch_point.end_y - touch_point.start_y
        gesture_time = touch_point.end_time - touch_point.start_time

        print(f"Delta X: {delta_x}, Delta Y: {delta_y}")
        print(f"Gesture time: {gesture_time:.2f} seconds")

        if abs(delta_x) > SWIPE_THRESHOLD and gesture_time < SWIPE_TIME:
            if delta_x > 0:
                print("Swipe right detected")
                open_url("http://localhost:32500/player/playback/skipPrevious")
            else:
                print("Swipe left detected")
                open_url("http://localhost:32500/player/playback/skipNext")
            last_action_time = current_time
            return

    # Single tap detection (play/pause toggle)
    if touch_point.last_tap_time is None or (current_time - touch_point.last_tap_time > DOUBLE_TAP_MAX_DELAY):
        print("Single tap detected")
        is_playing = not is_playing
        if is_playing:
            open_url("http://localhost:32500/player/playback/playPause")
        else:
            open_url("http://localhost:32500/player/playback/playPause")
        last_action_time = current_time
        touch_point.last_tap_time = current_time
        return

    # Double tap detection
    if DOUBLE_TAP_MIN_DELAY < current_time - touch_point.last_tap_time < DOUBLE_TAP_MAX_DELAY:
        print("Double tap detected")
        open_url("http://localhost:32500/player/playback/skipNext")
        last_action_time = current_time
        touch_point.reset()
        return

    touch_point.last_tap_time = current_time

def main():
    global touch_points
    current_touch_id = None

    try:
        device = evdev.InputDevice(TOUCHSCREEN_DEVICE)
        print(f"Listening for touch events on {device.name} ({TOUCHSCREEN_DEVICE})")

        for event in device.read_loop():
            if event.type == evdev.ecodes.EV_ABS:
                if event.code == evdev.ecodes.ABS_MT_SLOT:
                    current_touch_id = event.value
                elif event.code == evdev.ecodes.ABS_MT_TRACKING_ID:
                    if event.value == -1 and current_touch_id is not None:
                        if current_touch_id in touch_points:
                            print(f"Touch ID {current_touch_id} lifted")
                            handle_gestures(touch_points[current_touch_id])
                            del touch_points[current_touch_id]
                    else:
                        if event.value not in touch_points:
                            touch_points[event.value] = TouchPoint(event.value)
                        current_touch_id = event.value
                elif event.code == evdev.ecodes.ABS_MT_POSITION_X:
                    if current_touch_id is not None and current_touch_id in touch_points:
                        touch_points[current_touch_id].update_position(event.value, None)
                elif event.code == evdev.ecodes.ABS_MT_POSITION_Y:
                    if current_touch_id is not None and current_touch_id in touch_points:
                        touch_points[current_touch_id].update_position(None, event.value)
            
            # Print current state of touch points for debugging
            print("Current touch points:")
            for tp_id, tp in touch_points.items():
                print(f"  ID: {tp_id}, Start: ({tp.start_x}, {tp.start_y}), End: ({tp.end_x}, {tp.end_y})")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
