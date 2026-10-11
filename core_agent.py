import os
import asyncio
import speech_recognition as sr
import edge_tts
import pygame
from google import genai

# ==========================================
# CONFIGURATION
# ==========================================
WAKE_WORD = "system" # Wake word to trigger the agent
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Initialize Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)
recognizer = sr.Recognizer()

# Initialize audio playback
pygame.mixer.init()

# ==========================================
# CORE FUNCTIONS
# ==========================================

async def speak(text):
    """Converts text to speech using Edge-TTS and plays it."""
    print(f"🤖 System: {text}")
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save("response.mp3")
    
    pygame.mixer.music.load("response.mp3")
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
    
    # Cleanup audio file
    os.remove("response.mp3")

def listen_for_command():
    """Listens to the microphone and transcribes speech to text."""
    with sr.Microphone() as source:
        print("\n🎤 Adjusting for ambient noise... Please wait.")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("🟢 Listening...")
        
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
            # Using Google's free Web Speech API for fast V0 prototyping
            # We will upgrade this to local Whisper later for privacy/speed
            text = recognizer.recognize_google(audio)
            print(f"🗣️ You said: {text}")
            return text.lower()
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            print("⚠️ Could not understand audio.")
            return None
        except Exception as e:
            print(f"⚠️ Error: {e}")
            return None

def route_to_gemini(prompt):
    """Determines complexity and routes to the appropriate Gemini model."""
    # Simple semantic routing logic
    complex_keywords = ["refactor", "design", "architecture", "analyze", "deep dive"]
    is_complex = any(word in prompt for word in complex_keywords)
    
    model_name = "gemini-pro" if is_complex else "gemini-3.5-flash"
    print(f"🧠 Routing to: {model_name}")
    
    response = client.models.generate_content(
        model=model_name,
        contents=prompt
    )
    return response.text

# ==========================================
# MAIN LOOP
# ==========================================

async def main():
    print(f"🚀 AI Orchestrator Booting Up...")
    print(f"Waiting for wake word: '{WAKE_WORD}'")
    
    while True:
        command = listen_for_command()
        
        if command:
            if WAKE_WORD in command:
                await speak("I'm listening.")
                
                # Listen for the actual command after waking up
                action_command = listen_for_command()
                
                if action_command:
                    # Strip out asterisks or markdown that TTS might try to read
                    raw_response = route_to_gemini(action_command)
                    clean_response = raw_response.replace("*", "").replace("#", "")
                    await speak(clean_response)
            elif "shutdown orchestrator" in command:
                await speak("Shutting down. Goodbye.")
                break

if __name__ == "__main__":
    asyncio.run(main())