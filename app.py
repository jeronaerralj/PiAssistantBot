import os
import uuid
import threading
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
import pyttsx3
from better_profanity import profanity
from textblob import TextBlob
from datetime import datetime

BUZZER_PIN = 18

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    print("✓ Hardware: Raspberry Pi GPIO detected.")
except (ImportError, RuntimeError):
    print("⚠ Hardware: GPIO not detected. Using Mock Mode (Safe for Windows).")
    class MockGPIO:
        BCM = 'BCM'
        OUT = 'OUT'
        LOW = 0
        HIGH = 1
        def setmode(self, mode): pass
        def setup(self, pin, mode): pass
        def output(self, pin, state): print(f"[MOCK GPIO] Pin {pin} set to {state}")
        def cleanup(self): pass
    GPIO = MockGPIO()

app = Flask(__name__)
tts_lock = threading.Lock()

# Ensure audio directory exists
AUDIO_DIR = os.path.join('static', 'audio')
if not os.path.exists(AUDIO_DIR):
    os.makedirs(AUDIO_DIR)

# --- NLP & CONTEXT LOGIC ---
def get_bot_response(text):
    """Simple rule-based NLP for contextual responses."""
    text = text.lower()
    blob = TextBlob(text)
    
    # Contextual Triggers
    if "hello" in text or "hi" in text:
        return "Greetings! I am your Raspberry Pi voice assistant. How can I help?"
    elif "time" in text:
        return f"The current time is {datetime.now().strftime('%I:%M %p')}."
    elif "date" in text:
        return f"Today's date is {datetime.now().strftime('%A, %B %d, %Y')}."
    elif "who are you" in text:
        return "I am a Python script running on a Raspberry Pi using Flask and PyTTSx3."
    
    if blob.sentiment.polarity > 0.5:
        return "I am glad to hear such positive words!"
    elif blob.sentiment.polarity < -0.5:
        return "You sound upset. I hope your day gets better."
    
    return text

def trigger_buzzer():
    """Activates the hardware buzzer for 0.5 seconds."""
    def buzz():
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        time.sleep(0.5)
        GPIO.output(BUZZER_PIN, GPIO.LOW)
    
    threading.Thread(target=buzz).start()

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_voices', methods=['GET'])
def get_voices():
    """Returns available system voices."""
    try:
        # FORCE the 'espeak' driver here
        engine = pyttsx3.init('espeak') 
        voices = engine.getProperty('voices')
        voice_list = [{'id': v.id, 'name': v.name} for v in voices]
        del engine
        return jsonify(voice_list)
    except Exception as e:
        print("Error getting voices:", e)
        return jsonify([])

@app.route('/process_speech', methods=['POST'])
def process_speech():
    data = request.json
    user_text = data.get('text', '')
    rate = int(data.get('rate', 150))
    volume = float(data.get('volume', 1.0))
    voice_id = data.get('voice_id', None)
    
    if profanity.contains_profanity(user_text):
        trigger_buzzer()
        return jsonify({
            'success': False,
            'message': 'Profanity detected! Hardware buzzer activated.',
            'is_profane': True
        })

    final_text = get_bot_response(user_text)

    filename = f"{uuid.uuid4()}.wav"
    filepath = os.path.join(AUDIO_DIR, filename)
    
    with tts_lock:
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', rate)
            engine.setProperty('volume', volume)
            if voice_id:
                engine.setProperty('voice', voice_id)
            
            # Save to file
            engine.save_to_file(final_text, filepath)
            engine.runAndWait()
            del engine
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({
        'success': True,
        'audio_url': f"/static/audio/{filename}",
        'bot_response': final_text,
        'original_input': user_text
    })

if __name__ == '__main__':
    profanity.load_censor_words()
    try:

        app.run(host='0.0.0.0', port=5000, debug=True)
    finally:
        GPIO.cleanup()