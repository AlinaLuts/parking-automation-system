import cv2
import numpy as np
import easyocr
import os
import re
from datetime import datetime

# --- Конфигурация ---
DEBUG_DIR = "debug_plates"
os.makedirs(DEBUG_DIR, exist_ok=True)

reader = None

def init_reader():
    global reader
    if reader is None:
        print("🟡 Загрузка EasyOCR...")
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        print("✅ EasyOCR загружен")

def capture_from_camera(camera_id=0):
    print("\n📸 Захват изображения с камеры...")
    
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"❌ Не удалось открыть камеру {camera_id}")
        return None
    
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    print("📷 Нажмите 'ПРОБЕЛ' для захвата или 'ESC' для выхода...")
    
    frame_to_save = None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        preview = frame.copy()
        cv2.putText(preview, "Press SPACE to capture, ESC to exit", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("Camera", preview)
        
        key = cv2.waitKey(1) & 0xFF
        if key == 32:
            frame_to_save = frame.copy()
            print("✅ Кадр захвачен!")
            break
        elif key == 27:
            break
    
    cap.release()
    cv2.destroyAllWindows()
    return frame_to_save

# ============================================================
# ЭТАП 1: ПОВЫШЕНИЕ РЕЗКОСТИ
# ============================================================
def step1_sharpen(frame, save_path):
    print("\n📌 ЭТАП 1: Повышение резкости")
    blurred = cv2.GaussianBlur(frame, (0, 0), 3)
    sharpened = cv2.addWeighted(frame, 1.5, blurred, -0.5, 0)
    cv2.imwrite(save_path, sharpened)
    print(f"   ✅ Сохранено: {save_path}")
    return sharpened

# ============================================================
# ЭТАП 2: CLAHE
# ============================================================
def step2_clahe(sharpened, save_path):
    print("\n📌 ЭТАП 2: CLAHE (выравнивание контраста)")
    gray = cv2.cvtColor(sharpened, cv2.COLOR_BGR2GRAY)
    cv2.imwrite(save_path.replace("_clahe", "_gray"), gray)
    
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    
    cv2.imwrite(save_path, enhanced)
    print(f"   ✅ Сохранено: {save_path}")
    return enhanced

# ============================================================
# ЭТАП 3: БИНАРИЗАЦИЯ
# ============================================================
def step3_binarization(enhanced, save_path):
    print("\n📌 ЭТАП 3: Бинаризация")
    _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cv2.imwrite(save_path, binary)
    print(f"   ✅ Сохранено: {save_path}")
    return binary

# ============================================================
# ЭТАП 4: КОНТУРНЫЙ АНАЛИЗ
# ============================================================
def step4_find_contours(binary_image, original_frame, save_path):
    """
    Находит контуры и возвращает лучший кандидат
    """
    print("\n📌 ЭТАП 4: Поиск контуров номерного знака")
    
    contours, _ = cv2.findContours(binary_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    debug_img = original_frame.copy()
    candidates = []
    
    for contour in contours:
        area = cv2.contourArea(contour)
        
        if area > 500:  # Минимальная площадь
            x, y, w, h = cv2.boundingRect(contour)
            aspect_ratio = w / h if h > 0 else 0
            
            # Проверяем пропорции номера
            if 1.5 <= aspect_ratio <= 6.0:
                candidates.append((contour, (x, y, w, h), area))
                
                # Рисуем ВСЕ кандидаты СИНИМ
                cv2.rectangle(debug_img, (x, y), (x+w, y+h), (255, 0, 0), 2)
                cv2.putText(debug_img, f"area:{int(area)}", (x, y-5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
    
    # Выбираем лучший (с наибольшей площадью)
    best = None
    if candidates:
        candidates.sort(key=lambda c: c[2], reverse=True)
        best = candidates[0]
        
        # Рисуем лучший ЗЕЛЁНЫМ
        contour, (x, y, w, h), area = best
        cv2.rectangle(debug_img, (x, y), (x+w, y+h), (0, 255, 0), 3)
        cv2.putText(debug_img, f"BEST (area:{int(area)})", (x, y-15), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    
    cv2.imwrite(save_path, debug_img)
    print(f"   ✅ Найдено кандидатов: {len(candidates)}")
    
    if best:
        _, (x, y, w, h), area = best
        print(f"   ✅ Лучший: {w}x{h}, площадь={int(area)}")
    
    return best

# ============================================================
# ЭТАП 5: ВЫРЕЗАЕМ ПО КОНТУРУ (ПРАВИЛЬНО!)
# ============================================================
def step5_extract_by_contour(frame, contour, bbox, save_path):
    """
    Вырезает номер по контуру, оставляя ТОЛЬКО номер
    """
    print("\n📌 ЭТАП 5: Вырезаем номер по контуру")
    
    if contour is None:
        print("   ❌ Нет контура")
        return None
    
    x, y, w, h = bbox
    
    # СОЗДАЁМ МАСКУ: белое - это номер, чёрное - фон
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)  # Заливаем контур БЕЛЫМ
    
    # Применяем маску: оставляем ТОЛЬКО то, что внутри контура
    result = cv2.bitwise_and(frame, frame, mask=mask)
    
    # Обрезаем по bounding box
    plate_cropped = result[y:y+h, x:x+w]
    
    # Сохраняем маску для презентации
    mask_for_display = mask[y:y+h, x:x+w]
    cv2.imwrite(save_path.replace("_plate", "_mask"), mask_for_display)
    
    # Если получилось пустое изображение - пробуем без маски
    if np.sum(plate_cropped) == 0:
        print("   ⚠️ Маска дала пустое изображение, берём bounding box")
        plate_cropped = frame[y:y+h, x:x+w]
    
    # Увеличиваем для OCR
    scale = 2.5
    new_w = int(plate_cropped.shape[1] * scale)
    new_h = int(plate_cropped.shape[0] * scale)
    plate_resized = cv2.resize(plate_cropped, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    
    cv2.imwrite(save_path, plate_resized)
    print(f"   ✅ Сохранено: {save_path}")
    print(f"   📐 Размер: {plate_resized.shape[1]}x{plate_resized.shape[0]}")
    
    return plate_resized

# ============================================================
# ЭТАП 6: УЛУЧШЕНИЕ ДЛЯ OCR
# ============================================================
def step6_enhance_for_ocr(plate_roi, save_path):
    """
    Специальное улучшение для распознавания символов
    """
    print("\n📌 ЭТАП 6: Улучшение для OCR")
    
    if plate_roi is None:
        return None
    
    # Конвертация в серый
    if len(plate_roi.shape) == 3:
        gray = cv2.cvtColor(plate_roi, cv2.COLOR_BGR2GRAY)
    else:
        gray = plate_roi
    
    # Увеличение контраста
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
    contrast = clahe.apply(gray)
    
    # Бинаризация
    _, binary = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Инвертируем если нужно (чтобы буквы были белыми на чёрном)
    white_pixels = np.sum(binary == 255)
    black_pixels = np.sum(binary == 0)
    
    if white_pixels > black_pixels:
        binary = cv2.bitwise_not(binary)
    
    # Удаление шума
    kernel = np.ones((2, 2), np.uint8)
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=1)
    
    cv2.imwrite(save_path, cleaned)
    print(f"   ✅ Сохранено: {save_path}")
    
    return cleaned

# ============================================================
# ЭТАП 7: РАСПОЗНАВАНИЕ ПО МАСКЕ АА1234АА
# ============================================================
def step7_recognize_with_mask(image, save_path):
    """
    Распознавание с проверкой по маске AA1234AA
    """
    print("\n📌 ЭТАП 7: Распознавание (маска AA1234AA)")
    
    global reader
    
    if reader is None:
        init_reader()
    
    # Пробуем разные варианты изображения
    test_images = []
    
    # Оригинал
    test_images.append(("original", image))
    
    # Если цветное, пробуем каждый канал
    if len(image.shape) == 3:
        for i, channel in enumerate(['B', 'G', 'R']):
            test_images.append((f"{channel}_channel", image[:,:,i]))
    
    best_result = None
    best_confidence = 0
    
    for name, img in test_images:
        # Убеждаемся что灰度
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        
        # Пробуем разные пороги
        for thresh_type in ['otsu', 'adaptive']:
            if thresh_type == 'otsu':
                _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            else:
                binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                              cv2.THRESH_BINARY, 11, 2)
            
            # Распознавание
            results = reader.readtext(
                binary,
                allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                paragraph=False,
                detail=1
            )
            
            if results:
                # Собираем все символы
                all_text = []
                avg_prob = 0
                for (bbox, text, prob) in results:
                    text_clean = text.upper().replace(" ", "")
                    if prob > 0.3:
                        all_text.append(text_clean)
                        avg_prob += prob
                
                if all_text:
                    avg_prob /= len(all_text)
                    full_text = "".join(all_text)
                    
                    print(f"   [{name}/{thresh_type}]: '{full_text}' (conf={avg_prob:.2%})")
                    
                    # Проверяем по маске
                    if validate_plate_mask(full_text):
                        if avg_prob > best_confidence:
                            best_result = full_text
                            best_confidence = avg_prob
                            
                            # Сохраняем лучшее изображение
                            cv2.imwrite(save_path, binary)
                            print(f"   ✅ Сохранено лучшее для OCR: {save_path}")
    
    if best_result:
        print(f"\n   🎯 РАСПОЗНАНО ПО МАСКЕ: {best_result} (уверенность: {best_confidence:.2%})")
    else:
        print("\n   ❌ Не найдено соответствие маске AA1234AA")
    
    return best_result

def validate_plate_mask(plate):
    """
    Валидация: AA1234AA (2 буквы, 4 цифры, 2 буквы)
    """
    plate = plate.upper().strip()
    
    # Украинский номер
    pattern = r'^[A-Z]{2}\d{4}[A-Z]{2}$'
    
    if re.match(pattern, plate):
        return True
    
    # Исправляем частые ошибки
    corrected = plate
    corrections = {
        '0': 'O', 'O': '0',
        '1': 'I', 'I': '1',
        '5': 'S', 'S': '5',
        '8': 'B', 'B': '8',
        '2': 'Z', 'Z': '2'
    }
    
    for wrong, right in corrections.items():
        corrected = corrected.replace(wrong, right)
    
    if re.match(pattern, corrected):
        print(f"   🔄 Исправлено: {plate} -> {corrected}")
        return True
    
    return False

# ============================================================
# ФИНАЛЬНАЯ ВИЗУАЛИЗАЦИЯ
# ============================================================
def final_visualization(original_frame, bbox, recognized_plate, save_path):
    print("\n📌 ФИНАЛЬНАЯ ВИЗУАЛИЗАЦИЯ")
    
    result_img = original_frame.copy()
    
    if bbox:
        x, y, w, h = bbox
        cv2.rectangle(result_img, (x, y), (x+w, y+h), (0, 255, 0), 3)
    
    if recognized_plate:
        cv2.putText(result_img, f"RECOGNIZED: {recognized_plate}", (10, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    else:
        cv2.putText(result_img, "NO MATCH: AA1234AA", (10, 40),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    cv2.imwrite(save_path, result_img)
    print(f"   ✅ Сохранено: {save_path}")

# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================
def process_frame(frame, session_dir):
    print("\n" + "="*60)
    print("🔬 РАСПОЗНАВАНИЕ НОМЕРА (МАСКА AA1234AA)")
    print("="*60)
    
    # Оригинал
    cv2.imwrite(os.path.join(session_dir, "00_ORIGINAL.jpg"), frame)
    
    # Этапы предобработки
    sharpened = step1_sharpen(frame, os.path.join(session_dir, "01_SHARPENED.jpg"))
    enhanced = step2_clahe(sharpened, os.path.join(session_dir, "02_CLAHE.jpg"))
    binary = step3_binarization(enhanced, os.path.join(session_dir, "03_BINARY.jpg"))
    
    # Поиск контуров
    best = step4_find_contours(binary, frame, os.path.join(session_dir, "04_CONTOURS.jpg"))
    
    recognized = None
    if best:
        contour, bbox, area = best
        
        # Вырезаем по контуру
        plate_roi = step5_extract_by_contour(frame, contour, bbox,
                                             os.path.join(session_dir, "05_PLATE_ROI.jpg"))
        
        if plate_roi is not None:
            # Улучшаем для OCR
            ocr_ready = step6_enhance_for_ocr(plate_roi,
                                              os.path.join(session_dir, "06_OCR_READY.jpg"))
            
            if ocr_ready is not None:
                # Распознаём
                recognized = step7_recognize_with_mask(ocr_ready,
                                                       os.path.join(session_dir, "07_BEST_OCR.jpg"))
    
    # Финальный результат
    final_visualization(frame, bbox if best else None, recognized,
                       os.path.join(session_dir, "08_FINAL_RESULT.jpg"))
    
    print("\n" + "="*60)
    print("📊 РЕЗУЛЬТАТ")
    print("="*60)
    print(f"📁 Папка: {session_dir}")
    print(f"🎯 Номер: {recognized if recognized else 'НЕ РАСПОЗНАН'}")
    print("="*60 + "\n")
    
    return recognized

# ============================================================
# ЗАПУСК
# ============================================================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🟢 ТЕСТ С КАМЕРЫ - УКРАИНСКИЙ НОМЕР AA1234AA")
    print("="*60)
    
    init_reader()
    
    frame = capture_from_camera()
    
    if frame is None:
        print("\n❌ Нет изображения")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = os.path.join(DEBUG_DIR, f"plate_{timestamp}")
        os.makedirs(session_dir, exist_ok=True)
        
        result = process_frame(frame, session_dir)
        
        print(f"\n✅ Все файлы сохранены в: {session_dir}")
        if result:
            print(f"🎉 РАСПОЗНАНО: {result}")