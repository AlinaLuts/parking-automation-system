import cv2
import easyocr
import requests
import time
import ssl
import threading
from collections import deque
from flask import Flask, request, jsonify
from flask_cors import CORS

# Отключаем SSL для загрузки моделей
ssl._create_default_https_context = ssl._create_unverified_context

# --- настройки ---
DJANGO_URL = "http://127.0.0.1:8000/parking/api/set_plate/"
RECOGNITION_TIMEOUT = 10  # секунд

# Flask сервер
app = Flask(__name__)
CORS(app)

# Глобальные переменные
camera = None
is_recognizing = False
recognition_start_time = 0
last_sent_plate = None
last_time = 0
plate_buffer = deque(maxlen=3)
reader = None
recognition_result = None  # Добавляем переменную для результата

def init_reader():
    """Инициализация EasyOCR (один раз)"""
    global reader
    if reader is None:
        print("🟡 Загрузка EasyOCR...")
        reader = easyocr.Reader(['en'], gpu=False)
        print("✅ EasyOCR загружен")

def init_camera():
    """Инициализация камеры"""
    global camera
    if camera is None:
        print("🟡 Инициализация камеры...")
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            print("❌ Не удалось открыть камеру")
            return False
        print("✅ Камера готова")
    return True

def release_camera():
    """Освобождение камеры"""
    global camera
    if camera is not None:
        camera.release()
        camera = None
        print("🔴 Камера отключена")

def recognize_plate(frame):
    """Распознавание номера на кадре"""
    if reader is None:
        return None
    
    # Уменьшаем размер для скорости
    small = cv2.resize(frame, (640, 480))
    
    # Распознавание
    results = reader.readtext(small)
    
    for (bbox, text, prob) in results:
        text = text.upper().replace(" ", "").replace("-", "")
        
        if len(text) >= 3 and prob > 0.5:
            return text
    
    return None

def recognition_worker():
    """Фоновый поток для распознавания"""
    global is_recognizing, last_sent_plate, last_time, plate_buffer, camera, recognition_result
    
    print("🟡 Поток распознавания запущен")
    
    while True:
        if is_recognizing and camera is not None:
            ret, frame = camera.read()
            if ret:
                # Распознаем номер
                plate = recognize_plate(frame)
                
                if plate:
                    plate_buffer.append(plate)
                    print(f"📸 Кадр: {plate} (буфер: {list(plate_buffer)})")
                    
                    # Проверяем стабильность (3 одинаковых кадра)
                    if len(plate_buffer) >= 3 and all(p == plate for p in plate_buffer):
                        if plate != last_sent_plate or time.time() - last_time > 10:
                            print(f"🚗 СТАБИЛЬНЫЙ НОМЕР: {plate}")
                            try:
                                response = requests.post(DJANGO_URL, json={"plate": plate}, timeout=1)
                                if response.status_code == 200:
                                    print(f"✅ Отправлено в Django: {plate}")
                                    last_sent_plate = plate
                                    last_time = time.time()
                                    recognition_result = plate  # Сохраняем результат
                                    plate_buffer.clear()
                                    
                                    # Автоматически останавливаем после успеха
                                    is_recognizing = False
                                    release_camera()
                                    print("🟢 Распознавание завершено, камера отключена")
                                else:
                                    print(f"❌ Ошибка Django: {response.status_code}")
                            except Exception as e:
                                print(f"❌ Ошибка отправки: {e}")
                
                # Проверка таймаута
                if time.time() - recognition_start_time > RECOGNITION_TIMEOUT:
                    print(f"⏰ Таймаут {RECOGNITION_TIMEOUT} секунд")
                    is_recognizing = False
                    release_camera()
                    
                    # 🔴 УБИРАЕМ отправку TIMEOUT в Django
                    print("⏰ Таймаут - номер не распознан")
                    recognition_result = None  # Явно указываем что результат не получен
        
        time.sleep(0.1)

@app.route('/start', methods=['POST', 'OPTIONS'])
def start_recognition():
    """Запуск распознавания по кнопке"""
    if request.method == 'OPTIONS':
        return '', 200
        
    global is_recognizing, recognition_start_time, plate_buffer, last_sent_plate, recognition_result
    
    init_reader()
    
    # Инициализируем камеру
    if not init_camera():
        return jsonify({"success": False, "error": "Camera not available"})
    
    # Сбрасываем буфер и результат
    plate_buffer.clear()
    last_sent_plate = None
    recognition_result = None
    
    # Запускаем распознавание
    is_recognizing = True
    recognition_start_time = time.time()
    
    print(f"\n{'='*50}")
    print("🎥 РАСПОЗНАВАНИЕ ЗАПУЩЕНО ПО КНОПКЕ")
    print(f"⏰ Таймаут: {RECOGNITION_TIMEOUT} секунд")
    print(f"{'='*50}\n")
    
    return jsonify({
        "success": True, 
        "message": "Recognition started",
        "timeout": RECOGNITION_TIMEOUT
    })

@app.route('/stop', methods=['POST', 'OPTIONS'])
def stop_recognition():
    """Остановка распознавания"""
    if request.method == 'OPTIONS':
        return '', 200
        
    global is_recognizing
    is_recognizing = False
    release_camera()
    print("🛑 Распознавание остановлено")
    return jsonify({"success": True, "message": "Recognition stopped"})

@app.route('/status', methods=['GET', 'OPTIONS'])
def get_status():
    """Статус распознавания"""
    if request.method == 'OPTIONS':
        return '', 200
        
    return jsonify({
        "is_recognizing": is_recognizing,
        "timeout": RECOGNITION_TIMEOUT,
        "time_left": max(0, RECOGNITION_TIMEOUT - (time.time() - recognition_start_time)) if is_recognizing else 0,
        "camera_active": camera is not None,
        "result": recognition_result  # Добавляем результат в статус
    })

@app.route('/result', methods=['GET', 'OPTIONS'])
def get_result():
    """Получить результат распознавания"""
    if request.method == 'OPTIONS':
        return '', 200
        
    global recognition_result
    return jsonify({
        "success": recognition_result is not None,
        "plate": recognition_result
    })

if __name__ == '__main__':
    print("🟡 Сервер распознавания запускается...")
    
    # Запускаем поток распознавания
    recognition_thread = threading.Thread(target=recognition_worker, daemon=True)
    recognition_thread.start()
    
    print("✅ Сервер готов на порту 5001")
    print("   POST /start - запустить камеру и распознавание")
    print("   POST /stop - остановить и отключить камеру")
    print("   GET /status - статус")
    print("   GET /result - получить результат")
    print("\n⚠️ Камера сейчас ВЫКЛЮЧЕНА. Включится только по кнопке!")
    
    # Запускаем Flask
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)