# management/commands/test_arduino2.py
from django.core.management.base import BaseCommand
from arduino_api.serial_service import arduino_service
import time

class Command(BaseCommand):
    help = 'Тестирование нового скетча'
    
    def handle(self, *args, **kwargs):
        if arduino_service.connect():
            # 1. Проверяем датчик
            arduino_service.send_command("CHECK_ENTRY_SENSOR")
            time.sleep(0.5)
            response = arduino_service.read_response()
            self.stdout.write(f"Датчик въезда: {response}")
            
            # 2. Пробуем открыть без машины
            arduino_service.send_command("OPEN_ENTRY")
            time.sleep(0.5)
            response = arduino_service.read_response()
            self.stdout.write(f"Попытка открыть без машины: {response}")
            
            # 3. Покажи инструкцию
            arduino_service.send_command("HELP")
            time.sleep(0.5)
            while True:
                response = arduino_service.read_response()
                if response:
                    self.stdout.write(response)
                else:
                    break