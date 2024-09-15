import pyaudiowpatch as pyaudio
import time
import wave
import tempfile
import os
from collections import deque
import whisper
import threading
import requests
import dotenv

DURATION = 1.0
CHUNK_SIZE = 512
FRAMES_BACK = 8

filename = "loopback_record"

def get_default_speakers(p: pyaudio.PyAudio):
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        exit()

    default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
    
    if not default_speakers["isLoopbackDevice"]:
        for loopback in p.get_loopback_device_info_generator():
            """
            Try to find loopback device with same name(and [Loopback suffix]).
            Unfortunately, this is the most adequate way at the moment.
            """
            if default_speakers["name"] in loopback["name"]:
                default_speakers = loopback
                break
        else:
            exit()

    return default_speakers

def record(p, thread, filename, default_speakers):
    wave_file = wave.open(filename, 'wb')
    wave_file.setnchannels(default_speakers["maxInputChannels"])
    wave_file.setsampwidth(pyaudio.get_sample_size(pyaudio.paInt16))
    wave_file.setframerate(int(default_speakers["defaultSampleRate"]))
    
    def callback(in_data, frame_count, time_info, status):
        """Write frames and return PA flag"""
        wave_file.writeframes(in_data)
        return (in_data, pyaudio.paContinue)
    
    with p.open(format=pyaudio.paInt16,
            channels=default_speakers["maxInputChannels"],
            rate=int(default_speakers["defaultSampleRate"]),
            frames_per_buffer=CHUNK_SIZE,
            input=True,
            input_device_index=default_speakers["index"],
            stream_callback=callback
    ) as stream:
        """
        Opena PA stream via context manager.
        After leaving the context, everything will
        be correctly closed(Stream, PyAudio manager)            
        """
        if (thread != None):
            thread.join()
        else:
            time.sleep(1)
    
    wave_file.close()
    
def concatenate_files(inputs, output):
    data = []
    for inp in inputs:
        w = wave.open(inp, "rb")
        data.append([w.getparams(), w.readframes(w.getnframes())])
        w.close()
    output = wave.open(output, "wb")
    output.setparams(data[0][0])
    for i in range(len(data)):
        output.writeframes(data[i][1])
    output.close()

def get_filepath(ns):
    return os.path.join(tempfile.gettempdir(), f'record_{ns}.wav')

def get_text(ns, current_times, key):
    current_times.append(ns)
    if (len(current_times) > FRAMES_BACK):
        old = current_times.popleft()
        os.remove(get_filepath(old))
    filenames = [get_filepath(i) for i in current_times]
    combined_filepath = os.path.join(tempfile.gettempdir(), 'combined.wav')
    concatenate_files(filenames, combined_filepath)
    text = model.transcribe(combined_filepath, language='pl')['text']
    if (len(text.strip()) == 0):
        time.sleep(1)
    else:
        translated = requests.post('https://api-free.deepl.com/v2/translate',
                                    headers = {
                                        "Authorization": f"DeepL-Auth-Key {key}",
                                        "Content-Type": "application/json"
                                    },
                                    json = {
                                        "text": [text], 
                                        "target_lang": "EN"
                                    })
        print(translated.json()['translations'][0]['text'], flush=True)
        
        

    
if __name__ == "__main__":
    model = whisper.load_model('base')
    dotenv.load_dotenv()
    key = os.getenv('DEEPL_API_KEY')
    with pyaudio.PyAudio() as p:
        default_speakers = get_default_speakers(p)

        current_times = deque()
        x = None

        while(True):
            ns = time.time_ns()
            record(p, x, get_filepath(ns), default_speakers)
            x = threading.Thread(target=get_text, args=(ns, current_times, key))
            x.start()