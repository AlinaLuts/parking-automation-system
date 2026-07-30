# arduino_api/management/commands/test_arduino.py
from django.core.management.base import BaseCommand
from arduino_api.serial_service import arduino_service

class Command(BaseCommand):
    help = 'Тестирование подключения к Arduino'
    
    def handle(self, *args, **kwargs):
        self.stdout.write("Проверка подключения к Arduino...")
        
        if arduino_service.connect():
            self.stdout.write(self.style.SUCCESS("✅ Подключение успешно!"))
            
            # Тестируем команду STATUS
            self.stdout.write("Отправляем команду STATUS...")
            arduino_service.send_command("STATUS")
            
            # Читаем ответ
            import time
            time.sleep(0.5)
            response = arduino_service.read_response()
            
            if response:
                self.stdout.write(f"Ответ от Arduino: {response}")
            else:
                self.stdout.write("Нет ответа от Arduino")
        else:
            self.stdout.write(self.style.ERROR("❌ Не удалось подключиться"))