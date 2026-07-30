# arduino_api/serial_service.py
import serial
import time
import threading
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class ArduinoService:
    def __init__(self):
        self.port = getattr(settings, 'ARDUINO_PORT', 'COM3')
        self.baudrate = 115200
        self.connection = None
        self.lock = threading.Lock()
        self.last_sensor_readings = {
            'E_B': 1,  # Въезд перед шлагбаумом (0 = машина, 1 = свободно)
            'E_A': 1,  # Въезд после шлагбаума
            'X_B': 1,  # Выезд перед шлагбаумом
            'X_A': 1   # Выезд после шлагбаума
        }
        # Кэш для количества свободных мест (обновляется каждые 5 секунд)
        self._cached_free_spots = None
        self._cached_total_spots = None
        self._last_cache_update = 0
        self._cache_ttl = 5  # секунд
        
    def connect(self):
        """Подключиться к Arduino"""
        try:
            with self.lock:
                if self.connection and self.connection.is_open:
                    self.connection.close()
                
                self.connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    timeout=1,
                    write_timeout=1
                )
                time.sleep(2)
                
                self.connection.reset_input_buffer()
                self.connection.reset_output_buffer()
                
                time.sleep(0.1)
                while self.connection.in_waiting:
                    line = self.connection.readline().decode().strip()
                    logger.info(f"Arduino: {line}")
                
                logger.info(f"Подключились к Arduino на порту {self.port}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка подключения к Arduino: {e}")
            self.connection = None
            return False
    
    def _ensure_connection(self):
        """Убедиться, что соединение установлено"""
        if not self.connection or not self.connection.is_open:
            return self.connect()
        return True
    
    def send_command(self, command):
        """Отправить команду на Arduino"""
        try:
            if not self._ensure_connection():
                return False
            
            with self.lock:
                self.connection.reset_input_buffer()
                full_command = f"{command}\n"
                self.connection.write(full_command.encode())
                self.connection.flush()
                
                logger.debug(f"Отправлена команда: {command}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка отправки команды {command}: {e}")
            self.connection = None
            return False
    
    
    def get_free_spots(self, use_cache=True):
        
        current_time = time.time()
        
        # Проверяем кэш
        if use_cache and self._cached_free_spots is not None:
            if current_time - self._last_cache_update < self._cache_ttl:
                logger.debug(f"Используем кэш: free_spots={self._cached_free_spots}")
                return self._cached_free_spots
        
        try:
            if self.send_command("GET_FREE_SPOTS"):
                response = self.read_response(timeout=2)
                if response and response.startswith("FREE_SPOTS:"):
                    free_spots = int(response.split(":")[1])
                    
                    # Обновляем кэш
                    self._cached_free_spots = free_spots
                    self._last_cache_update = current_time
                    
                    logger.info(f"Получено свободных мест: {free_spots}")
                    return free_spots
        except Exception as e:
            logger.error(f"Ошибка получения свободных мест: {e}")
        
        return None
    
    def get_total_spots(self, use_cache=True):
      
        current_time = time.time()
        
        if use_cache and self._cached_total_spots is not None:
            if current_time - self._last_cache_update < self._cache_ttl:
                return self._cached_total_spots
        
        try:
            if self.send_command("GET_TOTAL_SPOTS"):
                response = self.read_response(timeout=2)
                if response and response.startswith("TOTAL_SPOTS:"):
                    total_spots = int(response.split(":")[1])
                    self._cached_total_spots = total_spots
                    logger.info(f"Общее количество мест: {total_spots}")
                    return total_spots
        except Exception as e:
            logger.error(f"Ошибка получения общего количества мест: {e}")
        
        return None
    
    def get_occupied_spots(self):
       
        try:
            if self.send_command("GET_OCCUPIED_SPOTS"):
                response = self.read_response(timeout=2)
                if response and response.startswith("OCCUPIED_SPOTS:"):
                    return int(response.split(":")[1])
        except Exception as e:
            logger.error(f"Ошибка получения занятых мест: {e}")
        
        return None
    
    def get_all_parking_stats(self):
        
        try:
            if self.send_command("GET_ALL_STATS"):
                response = self.read_response(timeout=2)
                if response and response.startswith("STATS:"):
                    data = response.replace("STATS:", "")
                    parts = data.split(",")
                    stats = {}
                    for part in parts:
                        if "=" in part:
                            key, val = part.split("=")
                            stats[key.lower()] = int(val)
                    
                    logger.info(f"Получена статистика: {stats}")
                    return stats
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
        
        return None
    
    def reset_parking_counter(self):
        
        try:
            if self.send_command("RESET_COUNTER"):
                response = self.read_response(timeout=2)
                if response and "COUNTER_RESET" in response:
                    # Сбрасываем кэш
                    self._cached_free_spots = None
                    self._cached_total_spots = None
                    logger.info("Счетчик парковки сброшен")
                    return True
        except Exception as e:
            logger.error(f"Ошибка сброса счетчика: {e}")
        
        return False

    def read_response(self, timeout=1):
        """Прочитать ответ от Arduino"""
        try:
            if not self._ensure_connection():
                return None
            
            with self.lock:
                response = self.connection.readline().decode().strip()
                if response:
                    logger.debug(f"Получен ответ: {response}")
                return response if response else None
                
        except Exception as e:
            logger.error(f"Ошибка чтения ответа: {e}")
            return None
    
    def update_sensors(self):
        """Обновить показания датчиков"""
        try:
            if self.send_command("SENSORS"):
                response = self.read_response()
                if response and response.startswith("SENSORS:"):
                    data = response.replace("SENSORS:", "")
                    parts = data.split(",")
                    
                    for part in parts:
                        if "=" in part:
                            key, value = part.split("=")
                            if key in self.last_sensor_readings:
                                self.last_sensor_readings[key] = int(value)
                    
                    logger.debug(f"Датчики: {self.last_sensor_readings}")
                    return True
        except Exception as e:
            logger.error(f"Ошибка обновления датчиков: {e}")
        
        return False
    
    def check_entry_sensor(self):
        """Проверить, стоит ли машина перед шлагбаумом на въезде"""
        self.update_sensors()
        
        # E_B = датчик перед шлагбаумом на въезде
        # 0 = машина обнаружена (стоит и ждет)
        # 1 = свободно (никого нет)
        has_car_waiting = self.last_sensor_readings['E_B'] == 0
        message = "Машина ждет на въезде" if has_car_waiting else "Нет машин на въезде"
        
        logger.info(f"Проверка въезда: машина ждет={has_car_waiting} (E_B={self.last_sensor_readings['E_B']})")
        return has_car_waiting, message
    
    def check_exit_sensor(self):
        """Проверить, стоит ли машина перед шлагбаумом на выезде"""
        self.update_sensors()
        
        # X_B = датчик перед шлагбаумом на выезде
        has_car_waiting = self.last_sensor_readings['X_B'] == 0
        message = "Машина ждет на выезде" if has_car_waiting else "Нет машин на выезде"
        
        return has_car_waiting, message
    
    def can_open_entry_barrier(self):
        """
        Можно ли открыть шлагбаум на въезде?
        Возвращает True только если машина стоит и ждет (E_B=0)
        """
        self.update_sensors()
        
        # Проверяем несколько условий:
        # 1. Машина должна стоять перед шлагбаумом (E_B=0)
        # 2. После шлагбаума должно быть свободно (E_A=1) - чтобы не было аварии
        car_waiting = self.last_sensor_readings['E_B'] == 0
        path_clear = self.last_sensor_readings['E_A'] == 1
        
        can_open = car_waiting and path_clear
        
        logger.info(f"Можно открыть въезд?: {can_open} "
                   f"(ожидание: {car_waiting}, путь свободен: {path_clear})")
        
        return can_open
    
    def can_open_exit_barrier(self):
        """Можно ли открыть шлагбаум на выезде?"""
        self.update_sensors()
        
        car_waiting = self.last_sensor_readings['X_B'] == 0
        path_clear = self.last_sensor_readings['X_A'] == 1
        
        can_open = car_waiting and path_clear
        
        return can_open
    
    def get_sensor_readings(self):
        """Получить все показания датчиков"""
        self.update_sensors()
        return self.last_sensor_readings.copy()
    
    def get_status(self):
        """Получить статус от Arduino"""
        if self.send_command("STATUS"):
            return self.read_response()
        return None
    
    def open_entry_barrier(self):
        """Открыть шлагбаум на въезде (только если можно)"""
        # Сначала проверяем, можно ли открыть
        if not self.can_open_entry_barrier():
            logger.warning("Попытка открыть шлагбаум когда нельзя!")
            return False
        
        success = self.send_command("OPEN_ENTRY")
        if success:
            time.sleep(0.1)
            response = self.read_response()
            logger.info(f"Открытие въезда: {response}")
        return success
    
    def open_exit_barrier(self):
        """Открыть шлагбаум на выезде (только если можно)"""
        if not self.can_open_exit_barrier():
            logger.warning("Попытка открыть выезд когда нельзя!")
            return False
        
        success = self.send_command("OPEN_EXIT")
        if success:
            time.sleep(0.1)
            response = self.read_response()
            logger.info(f"Открытие выезда: {response}")
        return success
    
    def close_entry_barrier(self):
        """Закрыть шлагбаум на въезде"""
        success = self.send_command("CLOSE_ENTRY")
        if success:
            time.sleep(0.1)
            response = self.read_response()
            logger.info(f"Закрытие въезда: {response}")
        return success
    
    def close_exit_barrier(self):
        """Закрыть шлагбаум на выезде"""
        success = self.send_command("CLOSE_EXIT")
        if success:
            time.sleep(0.1)
            response = self.read_response()
            logger.info(f"Закрытие выезда: {response}")
        return success
    
    def force_open_entry_barrier(self):
        """Принудительно открыть шлагбаум на въезде (без проверок)"""
        logger.warning("ПРИНУДИТЕЛЬНОЕ открытие въезда!")
        success = self.send_command("OPEN_ENTRY")
        if success:
            time.sleep(0.1)
            response = self.read_response()
            logger.info(f"Принудительное открытие: {response}")
        return success
    
    def reset_arduino(self):
        """Сбросить Arduino"""
        success = self.send_command("RESET")
        if success:
            time.sleep(1)
            self._ensure_connection()
        return success

arduino_service = ArduinoService()