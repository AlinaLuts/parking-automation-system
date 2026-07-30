# Parking automation system

Система автоматичного керування паркінгом для бізнес-центру з торговими площами. Поєднує веб-застосунок на Django, апаратну частину на Arduino та автоматичне розпізнавання номерних знаків на основі EasyOCR.
____
**Система забезпечує** 

- Авторизацію та розмежування доступу для 3 ролей: працівник, гість, сторонній відвідувач
- Автоматичне розпізнавання номерних знаків (ANPR) через камеру + EasyOCR
- Керування шлагбаумами через Arduino (інфрачервоні датчики + сервоприводи)
- Фінансову статистику та історію паркувань
- Веб-інтерфейс з панелями для кожної ролі

## Структура програмно-апаратного комплексу
<img width="1671" height="891" alt="image" src="https://github.com/user-attachments/assets/36eddc31-bee9-4c22-9592-46aef52c5c2e" />

## Стек технологій
<img width="500" height="400" alt="image" src="https://github.com/user-attachments/assets/f27da667-db8e-4491-9692-576a2f861125" />

### Backend

| Технологія | Призначення |
|------------|-------------|
| **Python** | Основна мова програмування |
| **Django** | Веб-фреймворк (серверна логіка, API, адмін-панель) |
| **Flask** | Мікросервіс для розпізнавання номерних знаків |
| **PostgreSQL** | Реляційна база даних |

### Computer Vision

| Технологія | Призначення |
|------------|-------------|
| **OpenCV** | Обробка зображень (CLAHE, бінаризація, контурний аналіз) |
| **EasyOCR** | Нейромережеве розпізнавання текстів |
| **NumPy** | Робота з матрицями та масивами |
___
### Апаратна частина
Фізичний макет системи складається з мікроконтролера Arduino Uno (А), чотирьох інфрачервоних датчиків (Б), двох сервоприводів SG90 (В) для керування шлагбаумами та LCD-дисплея (Г) для відображення кількості вільних місць.
<img width="646" height="541" alt="image" src="https://github.com/user-attachments/assets/b460ccec-e14d-4064-8332-6d3dcf64df82" />

## Скріншоти
| Панель працівника | Форма в'їзду | Розпізнавання номера |
|:---:|:---:|:---:|
| <img width="300" alt="image" src="https://github.com/user-attachments/assets/bd778dea-b39d-4e88-a69b-4d3f0aedee80" /> | <img width="300" alt="image" src="https://github.com/user-attachments/assets/bdc08d25-a945-4c9d-81bc-6fadc07fd7f9" /> | <img width="400" alt="image" src="https://github.com/user-attachments/assets/032ee247-d0cc-49ad-a2fc-3b2121b8d20c" /> |

| Створення запрошення | Адмін-статистика | Історія паркувань |
|:---:|:---:|:---:|
| <img width="300" alt="image" src="https://github.com/user-attachments/assets/bd8b8439-c340-402c-8f85-467c62306c40" /> | <img width="300" alt="image" src="https://github.com/user-attachments/assets/efa056c8-5759-47da-b8bf-976dfc6a8f97" /> | <img width="400" alt="image" src="https://github.com/user-attachments/assets/10463425-86ed-4ae3-8154-622be8a8aa3a" /> |
___
## Демонстрація роботи
 **[Дивитись на YouTube](https://youtu.be/FfFf5HRLPGk)**
<img width="975" height="665" alt="image" src="https://github.com/user-attachments/assets/02f7d402-a22d-4ebd-b8e6-4b2dbca233a2" />
___
## Автор
`Аліна Луценко`
- Дипломна робота бакалавра зі спеціальності "Комп'ютерна інженерія"
- Одеський національний університет імені І.І.Мечнікова
- Факультет математики, фізики та інформаційних технологій
- *alucenko068@gmail.com*
- www.linkedin.com/in/alina-lutsenko-923581333





