from datetime import timedelta

from django.utils import timezone as django_timezone 
import math
from django.shortcuts import render
from arduino_api.serial_service import arduino_service
import time

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
import json
from django.utils import timezone
import pytz
from datetime import datetime
from django.contrib import messages

import logging


def home(request):
    """Главная страница"""
    return render(request, 'parking_app/home.html')

def login_view(request):
    """Универсальная страница входа"""
    if request.method == 'POST':
        identifier = request.POST.get('identifier')
        password = request.POST.get('password')
        
        try:
            with request.db_conn.cursor() as cursor:
                cursor.execute("SELECT * FROM admin_login(%s, %s)", [identifier, password])
                admin_result = cursor.fetchone()
            
            if admin_result and admin_result[0]:  # успех
                request.session['user_id'] = admin_result[1]
                request.session['first_name'] = admin_result[2]
                request.session['last_name'] = admin_result[3]
                request.session['is_admin'] = True
                request.session['user_role'] = 'admin_role'
                return redirect('parking_app:home')  # ИЗМЕНИТЬ
        except Exception as e:
            print(f"Admin login error: {e}")
            pass
        
        try:
            with request.db_conn.cursor() as cursor:
                cursor.execute("SELECT * FROM staff_login(%s, %s)", [identifier, password])
                staff_result = cursor.fetchone()
            
            if staff_result and staff_result[0]:
                request.session['user_id'] = staff_result[1]
                request.session['first_name'] = staff_result[2]
                request.session['last_name'] = staff_result[3]
                request.session['is_admin'] = staff_result[4]
                request.session['user_role'] = 'admin_role' if staff_result[4] else 'staff_role'
                return redirect('parking_app:dashboard')  # ИЗМЕНИТЬ
        except Exception as e:
            print(f"Staff login error: {e}")
            pass
        
        # Если не удалось войти
        return render(request, 'parking_app/login.html', {'error': 'Невірний логін або пароль'})
    
    return render(request, 'parking_app/login.html')

def logout_view(request):
    """Выход из системы"""
    request.session.flush()
    return redirect('home')

    
def dashboard(request):
    """Панель управления в зависимости от роли"""
    user_role = request.session.get('user_role', 'visitor_role')
    
    if user_role == 'admin_role':
        return admin_dashboard(request)
    elif user_role == 'staff_role':
        return staff_dashboard(request)
    elif user_role == 'guest_role':
        return guest_dashboard(request)
    else:
        # Если не авторизован - на главную
        return redirect('parking_app:home')

# =============================================
# АДМИНИСТРАТОР
# =============================================

def admin_dashboard(request):
    """Панель администратора"""
    if request.session.get('user_role') != 'admin_role':
        return redirect('login')
    
    admin_id = request.session.get('user_id')
    
    with request.db_conn.cursor() as cursor:
        # Получаем статистику
        cursor.execute("""
            SELECT 
                (SELECT COUNT(*) FROM staff WHERE is_fired = FALSE) as active_staff,
                (SELECT COUNT(*) FROM guests) as total_guests,
                (SELECT COUNT(*) FROM vehicles) as total_vehicles,
                (SELECT COUNT(*) FROM parking_paid WHERE exit_time IS NULL) as active_paid_parking
        """)
        stats = cursor.fetchone()
        
        cursor.execute("SELECT * FROM get_staff_vehicles(%s)", [admin_id])
        
        columns = [desc[0] for desc in cursor.description]
        my_vehicles = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
        print(f"DEBUG: Admin vehicles: {my_vehicles}")
        
        cursor.execute("SELECT * FROM get_active_invitations(%s)", [admin_id])
        
        columns = [desc[0] for desc in cursor.description]
        active_invitations = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
        print(f"DEBUG: Admin invitations: {active_invitations}")
    
    return render(request, 'parking_app/admin_dashboard.html', {
        'stats': stats,
        'my_vehicles': my_vehicles,
        'active_invitations': active_invitations,
        'first_name': request.session.get('first_name'),
        'last_name': request.session.get('last_name'),
    })

def admin_register_staff(request):
    """A2: Реєстрація нового працівника"""
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        corporation = request.POST.get('corporation')
        is_admin = request.POST.get('is_admin') == 'on'
        
        with request.db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM register_staff(%s, %s, %s, %s, %s, %s)",
                [first_name, last_name, phone, email, corporation, is_admin]
            )
            result = cursor.fetchone()
        
        if result and result[0]:
            return redirect('parking_app:admin_staff_list')
        else:
            return render(request, 'parking_app/admin_register_staff.html', {
                'error': result[2] if result else 'Помилка реєстрації'
            })
    
    return render(request, 'parking_app/admin_register_staff.html')

def admin_staff_list(request):
    """Список працівників"""
    with request.db_conn.cursor() as cursor:
        cursor.execute("""
            SELECT s.id, s.first_name, s.last_name, s.phone_number, 
                   s.email, c.name as corporation, s.is_admin, s.is_fired
            FROM staff s
            JOIN corporation c ON s.corporation = c.id
            ORDER BY s.id
        """)
        staff_list = cursor.fetchall()
    
    return render(request, 'parking_app/admin_staff_list.html', {
        'staff_list': staff_list
    })

def admin_create_price(request):
    """A5: Створення тарифного плану"""
    if request.method == 'POST':
        price = request.POST.get('price')
        start_time_str = request.POST.get('start_time')
        end_time_str = request.POST.get('end_time')
        
        # Валидация
        if not price or not start_time_str or not end_time_str:
            return render(request, 'parking_app/admin_create_price.html', {
                'error': 'Всі поля обовʼязкові',
                'default_start': timezone.now().strftime('%Y-%m-%dT%H:%M'),
                'default_end': (timezone.now() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')
            })
        
        try:
            price_float = float(price)
 
            start_time_utc = start_time_str + ':00+02:00'  # Киев UTC+2
            end_time_utc = end_time_str + ':00+02:00'
            
            with request.db_conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM create_price(%s, %s::timestamp with time zone, %s::timestamp with time zone)",
                    [price_float, start_time_utc, end_time_utc]
                )
                result = cursor.fetchone()
            
            if result and result[0]:  # success = True
                return redirect('parking_app:admin_price_list')
            else:
                error_msg = result[2] if result and len(result) > 2 else 'Невідома помилка'
                return render(request, 'parking_app/admin_create_price.html', {
                    'error': error_msg,
                    'form_data': {
                        'price': price,
                        'start_time': start_time_str,
                        'end_time': end_time_str
                    },
                    'default_start': timezone.now().strftime('%Y-%m-%dT%H:%M'),
                    'default_end': (timezone.now() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')
                })
                
        except ValueError:
            return render(request, 'parking_app/admin_create_price.html', {
                'error': 'Невірний формат ціни',
                'form_data': {
                    'price': price,
                    'start_time': start_time_str,
                    'end_time': end_time_str
                },
                'default_start': timezone.now().strftime('%Y-%m-%dT%H:%M'),
                'default_end': (timezone.now() + timedelta(days=30)).strftime('%Y-%m-dT%H:%M')
            })
        except Exception as e:
            return render(request, 'parking_app/admin_create_price.html', {
                'error': f'Помилка: {str(e)}',
                'form_data': {
                    'price': price,
                    'start_time': start_time_str,
                    'end_time': end_time_str
                },
                'default_start': timezone.now().strftime('%Y-%m-%dT%H:%M'),
                'default_end': (timezone.now() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')
            })

    return render(request, 'parking_app/admin_create_price.html', {
        'default_start': '',  
        'default_end': ''   
    })

def admin_price_list(request):
    """Список тарифов"""
    # Устанавливаем киевскую временную зону
    kiev_tz = pytz.timezone('Europe/Kiev')
    current_time = timezone.now().astimezone(kiev_tz)
    
    with request.db_conn.cursor() as cursor:
        # Получаем все тарифы с конвертацией времени
        cursor.execute("""
            SELECT id, price, 
                   start_time as start_time_local,
                   end_time as end_time_local,
                   CASE 
                       WHEN %s BETWEEN start_time AND end_time THEN 'current'
                       WHEN %s < start_time THEN 'future'
                       ELSE 'past'
                   END as status
            FROM price_history 
            ORDER BY start_time DESC
        """, [current_time, current_time])
        price_list = cursor.fetchall()
        
        # Получаем текущий тариф
        cursor.execute("""
            SELECT id, price, 
                   start_time  as start_time_local,
                   end_time  as end_time_local
            FROM price_history 
            WHERE %s BETWEEN start_time AND end_time
            ORDER BY start_time DESC
            LIMIT 1
        """, [current_time])
        current_price = cursor.fetchone()
    
    # Статистика
    current_count = sum(1 for p in price_list if p[4] == 'current')
    future_count = sum(1 for p in price_list if p[4] == 'future')
    past_count = sum(1 for p in price_list if p[4] == 'past')
    
    return render(request, 'parking_app/admin_price_list.html', {
        'price_list': price_list,
        'current_price': current_price,
        'current_count': current_count,
        'future_count': future_count,
        'past_count': past_count,
        'current_time': current_time
    })

def admin_edit_price(request, price_id):
    """Упрощенное редактирование тарифа"""
    if request.method == 'POST':
        end_time = request.POST.get('end_time')
        start_time = request.POST.get('start_time')
        
        try:
            # Простая валидация - сравниваем как строки
            if start_time >= end_time:
                return render(request, 'parking_app/admin_edit_price.html', {
                    'error': 'Дата початку має бути раніше за дату закінчення',
                    'price_id': price_id
                })
            
            with request.db_conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE price_history 
                    SET start_time = %s, end_time = %s 
                    WHERE id = %s 
                    RETURNING id
                """, [start_time, end_time, price_id])
                
                result = cursor.fetchone()
                
                if result:
                    return redirect('parking_app:admin_price_list')
                else:
                    return render(request, 'parking_app/admin_edit_price.html', {
                        'error': 'Тариф не знайдено',
                        'price_id': price_id
                    })
                    
        except Exception as e:
            return render(request, 'parking_app/admin_edit_price.html', {
                'error': f'Помилка: {str(e)}',
                'price_id': price_id
            })
    
    # GET запрос
    with request.db_conn.cursor() as cursor:
        cursor.execute("""
            SELECT id, price, 
                   start_time AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Kiev' as start_time_local,
                   end_time AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Kiev' as end_time_local
            FROM price_history 
            WHERE id = %s
        """, [price_id])
        price = cursor.fetchone()
    
    if not price:
        return redirect('parking_app:admin_price_list')
    
    # Форматируем для input
    def format_dt(dt):
        if hasattr(dt, 'strftime'):
            return dt.strftime('%Y-%m-%dT%H:%M')
        return str(dt)[:16] if dt else ''
    
    return render(request, 'parking_app/admin_edit_price.html', {
        'price': price,
        'price_formatted': (
            price[0], 
            price[1], 
            format_dt(price[2]), 
            format_dt(price[3])
        ),
        'price_id': price_id
    })


def admin_delete_price(request, price_id):
    """Удаление тарифа (только будущие)"""
    try:
        with request.db_conn.cursor() as cursor:
            # Удаляем только будущие тарифы
            cursor.execute("""
                DELETE FROM price_history 
                WHERE id = %s AND start_time > %s
                RETURNING id
            """, [price_id, timezone.now()])
            
            # Даже если не удалили (не будущий тариф), все равно редиректим
            return redirect('parking_app:admin_price_list')
            
    except Exception as e:
        print(f"Delete price error: {e}")
        return redirect('parking_app:admin_price_list')
    

    
def admin_edit_staff(request, staff_id):
    """Редактирование информации о сотруднике"""
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        corporation = request.POST.get('corporation')
        is_admin = request.POST.get('is_admin') == 'on'
        
        try:
            with request.db_conn.cursor() as cursor:
                # Находим или создаем корпорацию
                cursor.execute(
                    "SELECT id FROM corporation WHERE name = %s",
                    [corporation]
                )
                corp_result = cursor.fetchone()
                
                if corp_result:
                    corp_id = corp_result[0]
                else:
                    cursor.execute(
                        "INSERT INTO corporation (name) VALUES (%s) RETURNING id",
                        [corporation]
                    )
                    corp_id = cursor.fetchone()[0]
                
                # Обновляем сотрудника
                cursor.execute("""
                    UPDATE staff 
                    SET first_name = %s, last_name = %s, phone_number = %s,
                        email = %s, corporation = %s, is_admin = %s
                    WHERE id = %s
                    RETURNING id
                """, [first_name, last_name, phone, email, corp_id, is_admin, staff_id])
                
                result = cursor.fetchone()
                
                if result:
                    return redirect('parking_app:admin_staff_list')
                else:
                    return render(request, 'parking_app/admin_edit_staff.html', {
                        'error': 'Співробітник не знайдений',
                        'staff_id': staff_id
                    })
                    
        except Exception as e:
            error_msg = str(e)
            if 'unique' in error_msg.lower():
                error_msg = 'Користувач з таким телефоном або email вже існує'
            
            return render(request, 'parking_app/admin_edit_staff.html', {
                'error': error_msg,
                'staff_id': staff_id,
                'form_data': {
                    'first_name': first_name,
                    'last_name': last_name,
                    'phone': phone,
                    'email': email,
                    'corporation': corporation,
                    'is_admin': is_admin
                }
            })
    
    # GET запрос - получаем данные сотрудника
    try:
        with request.db_conn.cursor() as cursor:
            cursor.execute("""
                SELECT s.id, s.first_name, s.last_name, s.phone_number, 
                       s.email, c.name as corporation, s.is_admin, s.is_fired
                FROM staff s
                JOIN corporation c ON s.corporation = c.id
                WHERE s.id = %s
            """, [staff_id])
            
            staff = cursor.fetchone()
            
            if not staff:
                return redirect('parking_app:admin_staff_list')
            
            return render(request, 'parking_app/admin_edit_staff.html', {
                'staff': staff,
                'staff_id': staff_id
            })
            
    except Exception as e:
        return redirect('parking_app:admin_staff_list')

def admin_fire_staff(request, staff_id):
    """Увольнение сотрудника - работает через GET"""
    try:
        with request.db_conn.cursor() as cursor:
            cursor.execute("""
                UPDATE staff 
                SET is_fired = TRUE 
                WHERE id = %s
            """, [staff_id])
            
        return redirect('parking_app:admin_staff_list')
            
    except Exception as e:
        print(f"Fire staff error: {e}")
        return redirect('parking_app:admin_staff_list')

def admin_restore_staff(request, staff_id):
    """Восстановление уволенного сотрудника - работает через GET"""
    try:
        with request.db_conn.cursor() as cursor:
            cursor.execute("""
                UPDATE staff 
                SET is_fired = FALSE 
                WHERE id = %s
            """, [staff_id])
            
        return redirect('parking_app:admin_staff_list')
            
    except Exception as e:
        print(f"Restore staff error: {e}")
        return redirect('parking_app:admin_staff_list')
    
def admin_parking_history(request):
    """A6: История парковок"""
    # Получаем параметры фильтрации
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    user_type = request.GET.get('user_type')
    plate_number = request.GET.get('plate_number')
    
    # Устанавливаем дефолтные даты (последние 7 дней)
    from datetime import datetime, timedelta
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    # Преобразуем параметры для SQL
    sql_user_type = user_type if user_type and user_type != "all" else None
    sql_plate_number = plate_number.strip() if plate_number and plate_number.strip() else None
    
    print(f"\nФильтры для истории:")
    print(f"  start_date: {start_date}")
    print(f"  end_date: {end_date}")
    print(f"  user_type: {sql_user_type}")
    print(f"  plate_number: {sql_plate_number}")
    
    try:
        with request.db_conn.cursor() as cursor:
            # Получаем историю через улучшенную функцию
            cursor.execute("""
                SELECT * FROM get_parking_history_v2(%s, %s, %s, %s)
            """, [start_date, end_date, sql_user_type, sql_plate_number])
            
            history = cursor.fetchall()
            print(f"  Найдено записей: {len(history)}")
            
            # Статистика
            staff_count = sum(1 for row in history if row[3] == 'Співробітник')
            guest_count = sum(1 for row in history if row[3] == 'Запрошений гість')
            visitor_count = sum(1 for row in history if row[3] == 'Платний відвідувач')
            total_revenue = sum(row[5] for row in history if row[5] is not None)
            
            stats = (staff_count, guest_count, visitor_count, total_revenue)
            
    except Exception as e:
        print(f"\n❌ ОШИБКА при получении истории: {e}")
        import traceback
        traceback.print_exc()
        history = []
        stats = (0, 0, 0, 0)
    
    return render(request, 'parking_app/admin_parking_history.html', {
        'history': history,
        'stats': stats,
        'filters': {
            'start_date': start_date,
            'end_date': end_date,
            'user_type': user_type or "all",
            'plate_number': plate_number or ""
        }
    })

def admin_current_parking(request):
    """Просмотр машин на парковке в данный момент"""
    search_query = request.GET.get('search', '').strip()
    
    try:
        with request.db_conn.cursor() as cursor:
            if search_query:
                # Поиск по номеру машины (частичное совпадение)
                cursor.execute("""
                    SELECT * FROM get_current_parking() 
                    WHERE plate_number ILIKE %s
                    ORDER BY entry_time DESC
                """, [f'%{search_query}%'])
            else:
                cursor.execute("SELECT * FROM get_current_parking()")
            
            current_parking = cursor.fetchall()
            
            # Статистика (только для найденных машин при поиске)
            staff_count = sum(1 for row in current_parking if 'Співробітник' in row[2])
            guest_count = sum(1 for row in current_parking if 'Запрошений гість' in row[2])
            visitor_count = sum(1 for row in current_parking if 'Платний відвідувач' in row[2])
            total_expected = sum(row[4] for row in current_parking if row[4] is not None)
            
            stats = {
                'total_cars': len(current_parking),
                'staff_count': staff_count,
                'guest_count': guest_count,
                'visitor_count': visitor_count,
                'total_expected': total_expected
            }
            
            
    except Exception as e:
        print(f"\n❌ ОШИБКА при получении текущих машин: {e}")
        import traceback
        traceback.print_exc()
        current_parking = []
        stats = {
            'total_cars': 0,
            'staff_count': 0,
            'guest_count': 0,
            'visitor_count': 0,
            'total_expected': 0
        }
    
    return render(request, 'parking_app/admin_current_parking.html', {
        'current_parking': current_parking,
        'stats': stats,
        'search_query': search_query
    })

def admin_financial_report(request):
    """A7: Финансовая статистика"""
    # Получаем параметры фильтрации
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Устанавливаем дефолтные даты (текущий месяц)
    from datetime import datetime
    if not start_date:
        start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    with request.db_conn.cursor() as cursor:
        # Финансовый отчет
        cursor.execute("""
            SELECT * FROM get_financial_report(%s, %s)
        """, [start_date, end_date])
        
        financial_report = cursor.fetchone()
        
        # Детализация по дням
        cursor.execute("""
            SELECT 
                pp.entry_time::DATE as date,
                COUNT(*) as sessions_count,
                SUM(pp.total_price) as daily_revenue,
                AVG(pp.total_price) as avg_price
            FROM parking_paid pp
            WHERE pp.exit_time IS NOT NULL
                AND pp.is_paid = TRUE
                AND pp.entry_time::DATE BETWEEN %s AND %s
            GROUP BY pp.entry_time::DATE
            ORDER BY date DESC
        """, [start_date, end_date])
        
        daily_stats = cursor.fetchall()
    
    return render(request, 'parking_app/admin_financial_report.html', {
        'report': financial_report,
        'daily_stats': daily_stats,
        'filters': {
            'start_date': start_date,
            'end_date': end_date
        }
    })
    
# =============================================
# ПРАЦІВНИК
# =============================================

def staff_dashboard(request):
    """Панель працівника"""
    staff_id = request.session.get('user_id')
    
    with request.db_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM get_staff_vehicles(%s)", [staff_id])
        
        # Преобразуем в список словарей
        columns = [desc[0] for desc in cursor.description]
        my_vehicles = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
        print(f"DEBUG: Got vehicles: {my_vehicles}")
        
        cursor.execute("SELECT * FROM get_active_invitations(%s)", [staff_id])
        
        # Преобразуем в список словарей
        columns = [desc[0] for desc in cursor.description]
        active_invitations = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
        print(f"DEBUG: Got invitations: {active_invitations}")
    
    return render(request, 'parking_app/staff_dashboard.html', {
        'my_vehicles': my_vehicles,
        'active_invitations': active_invitations,
        'first_name': request.session.get('first_name'),
        'last_name': request.session.get('last_name'),
    })

def staff_add_vehicle(request):
    """P2: Додавання транспортного засобу"""
    staff_id = request.session.get('user_id')
    
    if request.method == 'POST':
        plate_number = request.POST.get('plate_number')
        model = request.POST.get('model')
        
        print(f"DEBUG: Adding vehicle - plate: {plate_number}, model: {model}, staff: {staff_id}")
        
        with request.db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM add_staff_vehicle(%s, %s, %s)",
                [staff_id, plate_number, model]
            )
            result = cursor.fetchone()
            print(f"DEBUG: Result from DB: {result}")
        
        if result and result[0]:  # result[0] - success (boolean)
            return redirect('parking_app:dashboard')
        else:
            error_msg = result[2] if result and len(result) > 2 else 'Невідома помилка'
            print(f"DEBUG: Error: {error_msg}")
            
            # При ошибке также показываем текущие автомобили
            with request.db_conn.cursor() as cursor:
                cursor.execute("SELECT * FROM get_staff_vehicles(%s)", [staff_id])
                columns = [desc[0] for desc in cursor.description]
                my_vehicles = [
                    dict(zip(columns, row))
                    for row in cursor.fetchall()
                ]
            
            return render(request, 'parking_app/staff_add_vehicle.html', {
                'error': error_msg,
                'my_vehicles': my_vehicles,
                'plate_number': plate_number,
                'model': model
            })
    
    with request.db_conn.cursor() as cursor:
        cursor.execute("SELECT * FROM get_staff_vehicles(%s)", [staff_id])
        columns = [desc[0] for desc in cursor.description]
        my_vehicles = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
    
    return render(request, 'parking_app/staff_add_vehicle.html', {
        'my_vehicles': my_vehicles
    })

def staff_create_invitation(request):
    """Создание приглашения для гостя (номер телефона опционально)"""
    if request.method == 'POST':
        vehicle_plate = request.POST.get('vehicle_plate', '').strip()
        guest_phone = request.POST.get('guest_phone', '').strip()
        guest_first_name = request.POST.get('guest_first_name', '').strip()
        guest_last_name = request.POST.get('guest_last_name', '').strip()
        vehicle_model = request.POST.get('vehicle_model', '').strip()
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        staff_id = request.session.get('user_id')
        
        print(f"DEBUG: Creating invitation")
        print(f"  Vehicle plate: {vehicle_plate}")
        print(f"  Guest phone: {guest_phone}")
        print(f"  Guest first name: {guest_first_name}")
        print(f"  Guest last name: {guest_last_name}")
        print(f"  Vehicle model: {vehicle_model}")
        print(f"  Start: {start_time}")
        print(f"  End: {end_time}")
        print(f"  Staff ID: {staff_id}")
        
        try:
            with request.db_conn.cursor() as cursor:
                # Если указана модель, создаем/обновляем авто
                if vehicle_model:
                    cursor.execute("""
                        INSERT INTO vehicles (number_plate, model)
                        VALUES (%s, %s)
                        ON CONFLICT (number_plate) 
                        DO UPDATE SET model = EXCLUDED.model
                        WHERE vehicles.number_plate = EXCLUDED.number_plate
                        RETURNING id
                    """, [vehicle_plate.upper(), vehicle_model])
                
                # Создаем приглашение
                cursor.execute(
                    "SELECT * FROM create_invitation(%s, %s, %s, %s, %s, %s, %s)",
                    [
                        staff_id, 
                        vehicle_plate.upper(),  # Приводим к верхнему регистру
                        start_time, 
                        end_time,
                        guest_phone if guest_phone else None,
                        guest_first_name if guest_first_name else None,
                        guest_last_name if guest_last_name else None
                    ]
                )
                result = cursor.fetchone()
                print(f"DEBUG: Result from DB: {result}")
            
            if result and result[0]:  # result[0] - success
                print("DEBUG: Invitation created successfully")
                messages.success(request, 'Запрошення успішно створено!')
                return redirect('parking_app:dashboard')
            else:
                # Получаем сообщение об ошибке
                error_msg = "Невідома помилка"
                if result and len(result) > 4:
                    error_msg = result[4]  # message
                
                print(f"DEBUG: Error: {error_msg}")
                messages.error(request, error_msg)
                return render(request, 'parking_app/staff_create_invitation.html', {
                    'vehicle_plate': vehicle_plate,
                    'guest_phone': guest_phone,
                    'guest_first_name': guest_first_name,
                    'guest_last_name': guest_last_name,
                    'vehicle_model': vehicle_model,
                    'start_time': start_time,
                    'end_time': end_time
                })
                
        except Exception as e:
            print(f"DEBUG: Exception: {e}")
            messages.error(request, f'Помилка бази даних: {str(e)}')
            return render(request, 'parking_app/staff_create_invitation.html', {
                'vehicle_plate': vehicle_plate,
                'guest_phone': guest_phone,
                'guest_first_name': guest_first_name,
                'guest_last_name': guest_last_name,
                'vehicle_model': vehicle_model,
                'start_time': start_time,
                'end_time': end_time
            })
    
    # GET запрос
    return render(request, 'parking_app/staff_create_invitation.html')

def staff_invitations(request):
    """Список всех приглашений сотрудника"""
    staff_id = request.session.get('user_id')
    
    with request.db_conn.cursor() as cursor:
        # Вместо сырого SQL используем вызов функции
        cursor.execute("""
            SELECT * FROM get_staff_invitations(%s)
        """, [staff_id])
        
        # Преобразуем в словари для удобства
        columns = [desc[0] for desc in cursor.description]
        invitations = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
    
    # Подсчет статистики
    active_count = sum(1 for invite in invitations if invite['status'] == 'Активне')
    
    return render(request, 'parking_app/staff_invitations.html', {
        'invitations': invitations,
        'active_count': active_count,
        'total_count': len(invitations),
        'first_name': request.session.get('first_name'),
        'last_name': request.session.get('last_name'),
    })

def staff_edit_vehicle(request, plate_number):
    """Редактирование автомобиля сотрудника"""
    if request.method == 'POST':
        new_plate_number = request.POST.get('new_plate_number')
        new_model = request.POST.get('new_model')
        staff_id = request.session.get('user_id')
        
        with request.db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM edit_staff_vehicle(%s, %s, %s, %s)",
                [staff_id, plate_number, new_plate_number, new_model]
            )
            result = cursor.fetchone()
        
        if result and result[0]:  # success
            return redirect('parking_app:dashboard')
        else:
            error_msg = result[1] if result else 'Невідома помилка'
            return render(request, 'parking_app/staff_edit_vehicle.html', {
                'error': error_msg,
                'old_plate_number': plate_number
            })
    
    return render(request, 'parking_app/staff_edit_vehicle.html', {
        'plate_number': plate_number
    })

def staff_delete_vehicle(request, plate_number):
    """Удаление автомобиля сотрудника"""
    if request.method == 'POST':
        staff_id = request.session.get('user_id')
        
        with request.db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_staff_vehicle(%s, %s)",
                [staff_id, plate_number]
            )
            result = cursor.fetchone()
        
        if result and result[0]:  # success
            return redirect('parking_app:dashboard')
        else:
            error_msg = result[1] if result else 'Невідома помилка'
            return render(request, 'parking_app/staff_delete_vehicle.html', {
                'error': error_msg,
                'plate_number': plate_number
            })
    
    # GET запрос - показываем форму подтверждения
    return render(request, 'parking_app/staff_delete_vehicle.html', {
        'plate_number': plate_number
    })

def staff_parking_history(request):
    """История парковок сотрудника"""
    staff_id = request.session.get('user_id')
    days_back = request.GET.get('days', 30)  # По умолчанию за 30 дней
    
    with request.db_conn.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM get_staff_parking_history(%s, %s)",
            [staff_id, days_back]
        )
        # Преобразуем в словари
        columns = [desc[0] for desc in cursor.description]
        parking_history = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]
    
    return render(request, 'parking_app/staff_parking_history.html', {
        'parking_history': parking_history,
        'days_back': days_back,
        'first_name': request.session.get('first_name'),
        'last_name': request.session.get('last_name'),
    })

# =============================================
# ГОСТЬ
# =============================================
logger = logging.getLogger(__name__)
def guest_login(request):
    """Вход с проверкой пароля"""
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip() or None
        show_password_field = request.POST.get('show_password', 'false') == 'true'
        
        if not phone:
            messages.error(request, 'Введіть номер телефону')
            return render(request, 'parking_app/guest_login.html')
        
        # Простая валидация
        if not phone.startswith('+380') or len(phone) != 13 or not phone[4:].isdigit():
            messages.error(request, 'Невірний формат. Використовуйте: +380XXXXXXXXX')
            return render(request, 'parking_app/guest_login.html', {
                'phone': phone,
                'show_password': show_password_field
            })
        
        try:
            with request.db_conn.cursor() as cursor:
                cursor.execute("SELECT * FROM login_by_phone_with_password(%s, %s)", 
                             [phone, password])
                result = cursor.fetchone()
            
            if result and result[0]:  # success
                # Сохраняем в сессии
                request.session['user_id'] = result[1]
                request.session['user_type'] = result[2]  # 'guest' или 'visitor'
                request.session['first_name'] = result[3]
                request.session['last_name'] = result[4]
                request.session['phone'] = phone
                
                messages.success(request, result[5])
                
                # Редирект на нужную панель
                if result[2] == 'guest':
                    return redirect('parking_app:guest_dashboard')
                else:
                    return redirect('parking_app:visitor_dashboard')
            else:
                error_msg = result[5] if result else 'Помилка авторизації'
                requires_password = result[6] if result else False
                
                if requires_password and not password:
                    # Нужно показать поле пароля
                    messages.warning(request, error_msg)
                    return render(request, 'parking_app/guest_login.html', {
                        'phone': phone,
                        'show_password': True
                    })
                else:
                    messages.error(request, error_msg)
                    return render(request, 'parking_app/guest_login.html', {
                        'phone': phone,
                        'show_password': show_password_field or requires_password
                    })
        
        except Exception as e:
            print(f"Login error: {e}")
            messages.error(request, 'Технічна помилка')
            return render(request, 'parking_app/guest_login.html', {
                'phone': phone,
                'show_password': show_password_field
            })
    
    # GET запрос
    return render(request, 'parking_app/guest_login.html')

def guest_dashboard(request):
    """Обновленная панель гостя"""
    if request.session.get('user_type') != 'guest':
        messages.warning(request, 'У вас немає активних запрошень')
        return redirect('parking_app:guest_login')
    
    user_id = request.session['user_id']
    
    try:
        with request.db_conn.cursor() as cursor:
            # Активное приглашение
            cursor.execute("SELECT * FROM get_invitation_info(%s)", [user_id])
            invitation = cursor.fetchone()
            
            # Автомобили
            cursor.execute("SELECT * FROM get_user_vehicles(%s)", [user_id])
            vehicles = cursor.fetchall()
            
            # Текущая парковка
            cursor.execute("SELECT * FROM get_current_parking(%s)", [user_id])
            current_parking = cursor.fetchone()
            
            # Последние парковки
            cursor.execute("SELECT * FROM get_parking_history(%s, 5)", [user_id])
            recent_history = cursor.fetchall()
    
    except Exception as e:
        print(f"Dashboard error: {e}")
        invitation = (False, None, None, None)
        vehicles = []
        current_parking = (False, None, None, None, None)
        recent_history = []
    
    return render(request, 'parking_app/guest_dashboard.html', {
        'invitation': {
            'exists': invitation[0],
            'start_time': invitation[1],
            'end_time': invitation[2],
            'host_name': invitation[3]
        },
        'vehicles': vehicles,
        'current_parking': current_parking,
        'recent_history': recent_history,
        'user_info': {
            'first_name': request.session.get('first_name'),
            'last_name': request.session.get('last_name'),
            'phone': request.session.get('phone')
        }
    })

def visitor_dashboard(request):
    """Обновленная панель посетителя"""
    if request.session.get('user_type') != 'visitor':
        return redirect('parking_app:guest_dashboard')
    
    user_id = request.session['user_id']
    
    try:
        with request.db_conn.cursor() as cursor:
            # Текущий тариф
            cursor.execute("SELECT * FROM get_current_price()")
            price_info = cursor.fetchone()
            
            # Автомобили
            cursor.execute("SELECT * FROM get_user_vehicles(%s)", [user_id])
            vehicles = cursor.fetchall()
            
            # Текущая парковка
            cursor.execute("SELECT * FROM get_current_parking(%s)", [user_id])
            current_parking = cursor.fetchone()
            
            # Последние парковки
            cursor.execute("SELECT * FROM get_parking_history(%s, 5)", [user_id])
            recent_history = cursor.fetchall()
    
    except Exception as e:
        print(f"Visitor dashboard error: {e}")
        price_info = (50, None, None)
        vehicles = []
        current_parking = (False, None, None, None, None)
        recent_history = []
    
    return render(request, 'parking_app/visitor_dashboard.html', {
        'price': {
            'amount': price_info[0],
            'start_time': price_info[1],
            'end_time': price_info[2]
        },
        'vehicles': vehicles,
        'current_parking': current_parking,
        'recent_history': recent_history,
        'user_info': {
            'first_name': request.session.get('first_name'),
            'phone': request.session.get('phone')
        }
    })

# ========== ВЫХОД ==========
def guest_logout(request):
    """Выход из системы"""
    request.session.flush()
    messages.success(request, 'Ви успішно вийшли з системи')
    return redirect('parking_app:guest_login')


def guest_edit_profile(request):
    """Редактирование профиля для гостей и посетителей"""
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('parking_app:guest_login')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip() or None
        password = request.POST.get('password', '').strip() or None
        password_confirm = request.POST.get('password_confirm', '').strip() or None
        
        # Проверка пароля
        if password and password != password_confirm:
            messages.error(request, 'Паролі не співпадають')
            return render(request, 'parking_app/guest_edit_profile.html', {
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': request.session.get('phone')
            })
        
        try:
            with request.db_conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM update_user_profile(%s, %s, %s, %s, %s)",
                    [user_id, first_name, last_name, email, password]
                )
                result = cursor.fetchone()
            
            if result and result[0]:  # success
                # Обновляем сессию
                request.session['first_name'] = result[2]
                request.session['last_name'] = result[3]
                
                messages.success(request, result[1])
                
                # Редирект в зависимости от типа пользователя
                if request.session.get('user_type') == 'guest':
                    return redirect('parking_app:guest_dashboard')
                else:
                    return redirect('parking_app:visitor_dashboard')
            else:
                error_msg = result[1] if result else 'Помилка оновлення'
                messages.error(request, error_msg)
        
        except Exception as e:
            print(f"Edit profile error: {e}")
            messages.error(request, 'Технічна помилка')
    
    # GET запрос - показываем текущие данные
    return render(request, 'parking_app/guest_edit_profile.html', {
        'first_name': request.session.get('first_name'),
        'last_name': request.session.get('last_name'),
        'email': request.session.get('email', ''),
        'phone': request.session.get('phone')
    })

def guest_add_vehicle(request):
    """Добавление автомобиля"""
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('parking_app:guest_login')
    
    if request.method == 'POST':
        plate = request.POST.get('plate', '').strip().upper()
        model = request.POST.get('model', '').strip() or None
        
        if not plate:
            messages.error(request, 'Введіть номерний знак')
            return render(request, 'parking_app/guest_add_vehicle.html')
        
        try:
            with request.db_conn.cursor() as cursor:
                cursor.execute("SELECT * FROM add_user_vehicle(%s, %s, %s)", 
                             [user_id, plate, model])
                result = cursor.fetchone()
            
            if result and result[0]:
                messages.success(request, result[1])
            else:
                messages.error(request, result[1] if result else 'Помилка')
        
        except Exception as e:
            print(f"Add vehicle error: {e}")
            messages.error(request, 'Технічна помилка')
        
        # Редирект в зависимости от типа
        if request.session.get('user_type') == 'guest':
            return redirect('parking_app:guest_dashboard')
        else:
            return redirect('parking_app:visitor_dashboard')
    
    return render(request, 'parking_app/guest_add_vehicle.html')

def guest_parking_history(request):
    """История парковок"""
    user_id = request.session.get('user_id')
    if not user_id:
        return redirect('parking_app:guest_login')
    
    try:
        with request.db_conn.cursor() as cursor:
            cursor.execute("SELECT * FROM get_parking_history(%s, 20)", [user_id])
            history = cursor.fetchall()
            
            # Статистика
            total_parkings = len(history)
            total_cost = sum(float(h[4]) for h in history if h[4])
            active_parkings = sum(1 for h in history if h[5] == 'На парковці')
    
    except Exception as e:
        print(f"History error: {e}")
        history = []
        total_parkings = 0
        total_cost = 0
        active_parkings = 0
    
    return render(request, 'parking_app/guest_parking_history.html', {
        'history': history,
        'stats': {
            'total': total_parkings,
            'cost': total_cost,
            'active': active_parkings
        },
        'user_type': request.session.get('user_type')
    })



from django.http import JsonResponse
import json
from arduino_api.serial_service import arduino_service
import time

def check_sensors_view(request):
    """Проверка состояния датчиков"""
    if request.method == 'GET':
        try:
            # Проверяем датчик въезда
            entry_has_car, entry_msg = arduino_service.check_entry_sensor()
            
            # Проверяем датчик выезда
            exit_has_car, exit_msg = arduino_service.check_exit_sensor()
            
            # Получаем полный статус
            full_status = arduino_service.get_status()
            print("=== check_sensors_view вызвана ===")
            return JsonResponse({
                'success': True,
                'sensors': {
                    'entry': {
                        'has_car': entry_has_car,
                        'message': entry_msg
                    },
                    'exit': {
                        'has_car': exit_has_car,
                        'message': exit_msg
                    }
                },
                'status': full_status,
                'timestamp': time.time()
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            })
    
    return JsonResponse({'error': 'Invalid method'}, status=400)

def test_sensors_view(request):
    """Тестовая страница для проверки датчиков"""
    try:
        # Тестируем соединение
        connected = arduino_service._ensure_connection()
        
        if not connected:
            return JsonResponse({
                'success': False,
                'error': 'Не удалось подключиться к Arduino'
            })
        
        # Получаем статус
        arduino_service.send_command("STATUS")
        status = arduino_service.read_response()
        
        # Получаем датчики
        arduino_service.send_command("SENSORS")
        sensors = arduino_service.read_response()
        
        # Прямое чтение датчиков
        sensor_readings = arduino_service.get_sensor_readings()
        
        return JsonResponse({
            'success': True,
            'connected': connected,
            'status': status,
            'sensors_raw': sensors,
            'sensors_parsed': sensor_readings,
            'entry_has_car': sensor_readings['E_B'] == 0,
            'timestamp': time.time()
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

import time
from django.http import JsonResponse
from django.shortcuts import render

def normalize_plate_number(plate_number):
    """
    Нормализует номер автомобиля:
    - переводит кириллицу (укр/рус) в латиницу
    - удаляет все пробелы и спецсимволы
    - приводит к верхнему регистру
    
    Пример: "АА 1234 ВЕ" -> "AA1234BE"
    """
    if not plate_number:
        return ""
    
    # Словарь замены кириллицы на латиницу (русские и украинские буквы)
    translit_map = {
        # Русские буквы
        'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M', 'Н': 'H', 
        'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T', 'У': 'Y', 'Х': 'X',
        
        'І': 'I', 
        # Строчные буквы (будут переведены в заглавные после замены)
        'а': 'A', 'б': 'B', 'в': 'B', 'г': 'G', 'д': 'D', 'е': 'E',
        'ё': 'E', 'ж': 'ZH', 'з': 'Z', 'и': 'I', 'й': 'Y', 'к': 'K',
        'л': 'L', 'м': 'M', 'н': 'H', 'о': 'O', 'п': 'P', 'р': 'P',
        'с': 'C', 'т': 'T', 'у': 'Y', 'ф': 'F', 'х': 'X', 'ц': 'TS',
        'ч': 'CH', 'ш': 'SH', 'щ': 'SHCH', 'ъ': '', 'ы': 'Y', 'ь': '',
        'э': 'E', 'ю': 'YU', 'я': 'YA', 'і': 'I', 'ї': 'YI', 'є': 'YE',
        'ґ': 'G'
    }
    
    result = []
    for char in plate_number:
        # Если буква кириллическая - заменяем
        if char in translit_map:
            result.append(translit_map[char])
        # Если буква латинская или цифра - оставляем как есть
        elif char.isalnum():
            result.append(char.upper())
        # Остальные символы (пробелы, дефисы и т.д.) - пропускаем
    
    # Склеиваем и переводим в верхний регистр (на всякий случай)
    normalized = ''.join(result).upper()
    
    return normalized


def process_entry_view(request):
    """Заїзд на паркінг - открываем только если машина ждет"""
    if request.method == 'POST':
        plate_number = request.POST.get('plate_number')
        
        if plate_number:
            plate_number = normalize_plate_number(plate_number)
            print(f"   🧹 Нормализованный номер: {plate_number}")
        
        free_spots = arduino_service.get_free_spots()
        
        if free_spots is None:
            return JsonResponse({
                'success': False,
                'message': 'Помилка зв\'язку з паркувальним обладнанням. Спробуйте пізніше.'
            })
        
        if free_spots <= 0:
            return JsonResponse({
                'success': False,
                'message': f'На жаль, парковка заповнена. Вільних місць: 0/{arduino_service.get_total_spots() or "?"}'
            })


        try:
            print(f"\n{'='*50}")
            print(f"ПОПЫТКА ВЪЕЗДА: {plate_number}")
            print(f"{'='*50}")
            
            # ШАГ 1: ПРОВЕРКА ДАТЧИКОВ - машина должна ЖДАТЬ
            print("\n1. ПРОВЕРКА: Машина ждет на въезде?")
            
            # Получаем данные датчиков
            arduino_service.update_sensors()
            sensor_readings = arduino_service.get_sensor_readings()
            
            print(f"   Датчики: {sensor_readings}")
            print(f"   E_B (перед шлагбаумом): {sensor_readings['E_B']} "
                  f"(0=машина ждет, 1=свободно)")
            print(f"   E_A (после шлагбаума): {sensor_readings['E_A']} "
                  f"(0=машина внутри, 1=свободно)")
            
            # Проверяем условия:
            # 1. Машина должна стоять перед шлагбаумом (E_B=0)
            # 2. После шлагбаума должно быть свободно (E_A=1)
            car_waiting = sensor_readings['E_B'] == 0
            path_clear = sensor_readings['E_A'] == 1
            
            if not car_waiting:
                print("   ❌ НЕТ: Никто не ждет на въезде (E_B=1)")
                return JsonResponse({
                    'success': False,
                    'message': 'Шлагбаум не відкрито: немає машин на в''їзді',
                    'sensor_data': sensor_readings,
                    'debug': {
                        'car_waiting': False,
                        'path_clear': path_clear,
                        'reason': 'no_car_waiting'
                    }
                })
            
            if not path_clear:
                print("   ❌ НЕТ: Путь не свободен (E_A=0)")
                return JsonResponse({
                    'success': False,
                    'message': 'Шлагбаум не открыт: путь после шлагбаума занят',
                    'sensor_data': sensor_readings,
                    'debug': {
                        'car_waiting': True,
                        'path_clear': False,
                        'reason': 'path_blocked'
                    }
                })
            
            print("   ✓ ДА: Машина ждет и путь свободен")
            
            # ШАГ 2: ПРОВЕРКА РАЗРЕШЕНИЯ НА ВЪЕЗД С ИНФОРМАЦИЕЙ О ПРИГЛАШЕНИИ
            print("\n2. ПРОВЕРКА РАЗРЕШЕНИЯ В БД:")
            
            with request.db_conn.cursor() as cursor:
                cursor.execute("SELECT * FROM check_entry_with_invitation_info(%s)", [plate_number])
                result = cursor.fetchone()
            
            print(f"   Результат БД: {result}")
            
            if not result:
                print("   ❌ Нет результата от БД")
                return JsonResponse({
                    'success': False,
                    'message': 'Ошибка проверки разрешения: нет ответа от базы данных'
                })
            
            try:
                can_enter, user_type, message, guest_id, vehicle_id, cost, invitation_info, warning_message = result
                print(f"   Успешно распаковано: can_enter={can_enter}, type={user_type}, msg={message}")
                print(f"   invitation_info: {invitation_info}")
                print(f"   warning_message: {warning_message}")
                print(f"   guest_id: {guest_id}, vehicle_id: {vehicle_id}, cost: {cost}")
                
                print(f"   🔍 Анализ user_type: {user_type}")
                if user_type == 'invited_guest':
                    print("   ⚠️  ВНИМАНИЕ: user_type = 'invited_guest' - может быть устаревшая функция в БД!")
                elif user_type == 'paying_guest':
                    print("   ✓ user_type = 'paying_guest' - правильный тип")
                elif user_type == 'staff':
                    print("   ✓ user_type = 'staff' - сотрудник")
                
            except Exception as unpack_error:
                print(f"   ❌ Ошибка распаковки: {unpack_error}")
                print(f"   Количество значений в результате: {len(result)}")
                print(f"   Значения: {result}")
                return JsonResponse({
                    'success': False,
                    'message': f'Ошибка обработки данных: {str(unpack_error)}'
                })
            
            if not can_enter:
                print(f"   ❌ БД запрещает въезд: {message}")
                return JsonResponse({
                    'success': False,
                    'message': message,
                    'sensor_data': sensor_readings
                })
            
            print("   ✓ Разрешение получено")
            
            print("\n3. СОЗДАНИЕ ЗАПИСИ О ПАРКОВКЕ:")
            
            parking_id = None
            try:
                if user_type == 'staff':
                    # Используем существующую функцию для сотрудников
                    with request.db_conn.cursor() as cursor:
                        cursor.execute("SELECT create_staff_parking(%s)", [plate_number])
                        parking_result = cursor.fetchone()
                        if parking_result and parking_result[0]:
                            parking_id = parking_result[0]
                            print(f"   ✓ Запись для сотрудника создана: id={parking_id}")
                        else:
                            print("   ❌ Ошибка создания записи для сотрудника")
                
                
                elif user_type == 'paying_guest':
                    print(f"   Создание записи для гостя (тип: paying_guest)")
                    print(f"   guest_id: {guest_id}, vehicle_id: {vehicle_id}")
                    
                    with request.db_conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT COUNT(*) 
                            FROM pg_proc 
                            WHERE proname = 'create_paying_guest_parking'
                        """)
                        func_exists = cursor.fetchone()[0]
                        
                        if func_exists > 0:
                            print("   Функция create_paying_guest_parking существует")
                            cursor.execute("SELECT create_paying_guest_parking(%s)", [plate_number])
                            parking_result = cursor.fetchone()
                            if parking_result and parking_result[0]:
                                parking_id = parking_result[0]
                                print(f"   ✓ Запись для гостя создана через функцию: id={parking_id}")
                            else:
                                print("   ❌ Функция вернула NULL, пробуем прямой INSERT")
                                raise Exception("Функция вернула NULL")
                        else:
                            print("   ⚠️  Функция create_paying_guest_parking не найдена, используем прямой SQL")
                    
                    if not parking_id:
                        print("   Пробуем создать запись напрямую через SQL")
                        
                        # Если гость не найден, создаем временного гостя
                        if not guest_id:
                            print("   Гость не найден, создаем временную запись...")
                            with request.db_conn.cursor() as cursor:
                                # Создаем временного гостя
                                cursor.execute("""
                                    INSERT INTO guests (phone_number, first_name, last_name)
                                    VALUES (%s, 'Відвідувач', 'Тимчасовий')
                                    RETURNING id
                                """, [f'temp_{int(time.time())}_{plate_number}'])
                                guest_id = cursor.fetchone()[0]
                                
                                # Если машины нет, создаем
                                if not vehicle_id:
                                    cursor.execute("""
                                        INSERT INTO vehicles (number_plate) 
                                        VALUES (%s)
                                        RETURNING id
                                    """, [plate_number])
                                    vehicle_id = cursor.fetchone()[0]
                                
                                # Связываем гостя с машиной
                                cursor.execute("""
                                    INSERT INTO guest_vehicles (guest_id, vehicle_id)
                                    VALUES (%s, %s)
                                    ON CONFLICT DO NOTHING
                                """, [guest_id, vehicle_id])
                        
                        # Получаем текущую цену
                        with request.db_conn.cursor() as cursor:
                            cursor.execute("""
                                SELECT id FROM price_history 
                                WHERE valid_from <= NOW() 
                                ORDER BY valid_from DESC 
                                LIMIT 1
                            """)
                            price_row = cursor.fetchone()
                            price_id = price_row[0] if price_row else 1
                            
                            # Создаем запись о парковке
                            cursor.execute("""
                                INSERT INTO parking_paid 
                                (guest_id, vehicle_id, price_id, entry_time, is_paid, total_price)
                                VALUES (%s, %s, %s, NOW(), FALSE, NULL)
                                RETURNING id
                            """, [guest_id, vehicle_id, price_id])
                            parking_id = cursor.fetchone()[0]
                        
                        print(f"   ✓ Запись для гостя создана напрямую: id={parking_id}")
                            
            except Exception as e:
                print(f"   ❌ Ошибка при создании записи: {e}")
                import traceback
                traceback.print_exc()
                return JsonResponse({
                    'success': False,
                    'message': f'Ошибка создания записи: {str(e)[:100]}',
                    'sensor_data': sensor_readings
                })
            
            if not parking_id:
                print("   ❌ Ошибка создания записи о парковке")
                return JsonResponse({
                    'success': False,
                    'message': 'Ошибка создания записи о парковке',
                    'sensor_data': sensor_readings
                })
            
            print("\n4. ОТКРЫТИЕ ШЛАГБАУМА:")
            
            # Финальная проверка перед открытием
            if not arduino_service.can_open_entry_barrier():
                print("   ❌ Последняя проверка: нельзя открыть!")
                return JsonResponse({
                    'success': False,
                    'message': 'Перед открытием изменилось состояние датчиков',
                    'sensor_data': arduino_service.get_sensor_readings()
                })
            
            print("   Открываем шлагбаум...")
            
            if arduino_service.open_entry_barrier():
                print("   ✓ Команда отправлена")
                time.sleep(0.5)
                
                response = arduino_service.read_response()
                print(f"   Ответ Arduino: {response}")
                
                final_message = message
                if invitation_info:
                    final_message += f". {invitation_info}"
                if warning_message:
                    final_message += f". {warning_message}"
                final_message += ". Шлагбаум відкрито"
                
                debug_info = {
                    'parking_id': parking_id,
                    'guest_id': guest_id,
                    'vehicle_id': vehicle_id,
                    'user_type': user_type
                }
                
                print(f"   Результат въезда:")
                print(f"     - parking_id: {parking_id}")
                print(f"     - guest_id: {guest_id}")
                print(f"     - vehicle_id: {vehicle_id}")
                print(f"     - user_type: {user_type}")
                print(f"     - cost: {cost}")
                
                return JsonResponse({
                    'success': True,
                    'message': final_message,
                    'cost': float(cost) if cost else 0,
                    'user_type': user_type,
                    'invitation_info': invitation_info,
                    'warning_message': warning_message,
                    'sensor_data': sensor_readings,
                    'debug_info': debug_info,
                    'parking_id': parking_id  # Добавляем ID для возможной проверки
                })
            else:
                print("   ❌ Ошибка отправки команды")
                return JsonResponse({
                    'success': False,
                    'message': 'Ошибка открытия шлагбаума',
                    'sensor_data': sensor_readings
                })
                
        except Exception as e:
            print(f"\n ОШИБКА: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return JsonResponse({
                'success': False,
                'message': f'Ошибка: {str(e)[:100]}'
            })
    
    current_price = 0
    try:
        with request.db_conn.cursor() as cursor:
            cursor.execute("SELECT get_current_price_info()")
            price_result = cursor.fetchone()
            if price_result:
                price_data = price_result[0]
                if isinstance(price_data, tuple):
                    current_price = float(price_data[0])  # первый элемент кортежа
                else:
                    current_price = float(price_data)
    except Exception as e:
        print(f"Ошибка получения цены: {e}")
        current_price = 60  # значение по умолчанию
    
    return render(request, 'parking_app/process_entry.html', {
        'current_price': current_price
    })

import time
import math
from django.http import JsonResponse
from django.shortcuts import render

from django.utils import timezone  
import math

def process_exit_view(request):
    """Выезд с паркинга"""
    if request.method == 'GET':
        with request.db_conn.cursor() as cursor:
            cursor.execute("SELECT get_current_price_info()")
            price_result = cursor.fetchone()
            if price_result:
                current_price = float(price_result[0]) if price_result[0] else 0

        return render(request, 'parking_app/process_exit.html', {
            'current_price': current_price
        })
    
    elif request.method == 'POST':
        action = request.POST.get('action')
        plate_number = request.POST.get('plate_number', '').strip().upper()
        if plate_number:
            plate_number = normalize_plate_number(plate_number)
            print(f"   🧹 Нормализованный номер: {plate_number}")

        try:
            if action == 'check':
                with request.db_conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM check_exit_info(%s)", [plate_number])
                    result = cursor.fetchone()
                
                print(f"\nDEBUG check_exit_info для {plate_number}:")
                print(f"Результат: {result}")
                print(f"Количество значений: {len(result) if result else 0}")
                
                if not result:
                    return JsonResponse({
                        'success': False,
                        'message': 'Автомобіль з таким номером не знайдено на парковці'
                    })
                
                # Функция возвращает 12 значений
                can_exit, user_type, message, user_id, vehicle_id, entry_time, \
                need_payment, parking_id, total_price, hours_parked, is_paid, additional_info = result
                
                print(f"can_exit: {can_exit}")
                print(f"user_type: {user_type}")
                print(f"need_payment: {need_payment}")
                print(f"is_paid: {is_paid}")
                print(f"total_price: {total_price}")
                print(f"hours_parked: {hours_parked}")
                print(f"additional_info: {additional_info}")
                
                friendly_message = message
                if user_type == 'staff':
                    friendly_message = 'Працівник. Безкоштовне паркування.'
                elif user_type == 'invited_guest':
                    friendly_message = 'Запрошений гість. Безкоштовно за запрошенням.'
                elif user_type == 'paying_guest':
                    if is_paid:
                        if total_price == 0:
                            friendly_message = 'Відвідувач. Паркування безкоштовно.'
                        else:
                            friendly_message = f'Відвідувач. Паркування оплачено ({total_price:.2f} грн).'
                    else:
                        free_minutes = 10
                        if hours_parked <= (free_minutes / 60.0):
                            friendly_message = f'Відвідувач. Перші {free_minutes} хвилин безкоштовно.'
                        else:
                            friendly_message = f'Відвідувач. Потрібна оплата: {total_price:.2f} грн за {hours_parked:.1f} год.'
                
                response_data = {
                    'success': True,
                    'can_exit': can_exit,
                    'user_type': user_type,
                    'message': friendly_message,
                    'need_payment': need_payment and total_price > 0 and not is_paid,
                    'is_paid': is_paid,
                    'total_price': float(total_price) if total_price else 0,
                    'hours_parked': float(hours_parked) if hours_parked else 0,
                    'entry_time': entry_time.isoformat() if entry_time else None,
                    'parking_id': parking_id,
                    'additional_info': additional_info
                }
                
                print(f"Отправляем в ответ: need_payment={response_data['need_payment']}")
                
                return JsonResponse(response_data)
            
            elif action == 'pay':
                parking_id = request.POST.get('parking_id')
                user_type = request.POST.get('user_type')
                
                print(f"\nDEBUG process_payment для parking_id={parking_id}, user_type={user_type}")
                
                with request.db_conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM process_payment(%s, %s)", [parking_id, user_type])
                    result = cursor.fetchone()
                
                print(f"Результат process_payment: {result}")
                print(f"Количество значений process_payment: {len(result) if result else 0}")
                
                if result:
                    if len(result) >= 3:
                        success = result[0]
                        message = result[1]
                        total_price = result[2]
                        
                        friendly_message = message
                        if success:
                            if total_price == 0:
                                friendly_message = 'Перші 10 хвилин безкоштовно. Оплата не потрібна.'
                            else:
                                friendly_message = f'Оплата успішна. Сплачено {float(total_price):.2f} грн.'
                        
                        response_data = {
                            'success': success,
                            'message': friendly_message,
                            'total_price': float(total_price) if total_price else 0
                        }
                        
                        if len(result) >= 4:
                            response_data['fixed_hours'] = float(result[3]) if result[3] else 0
                        if len(result) >= 5:
                            response_data['payment_time'] = result[4].isoformat() if result[4] else None
                        if len(result) >= 6:
                            response_data['additional_info'] = result[5]
                        
                        return JsonResponse(response_data)
                    else:
                        return JsonResponse({
                            'success': False,
                            'message': 'Ошибка при обработке оплаты: неверный формат ответа от БД'
                        })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Ошибка при обработке оплаты: нет ответа от БД'
                    })
            
            elif action == 'exit':
                print(f"\n{'='*50}")
                print(f"ПОПЫТКА ВЫЕЗДА: {plate_number}")
                print(f"{'='*50}")
                
                with request.db_conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM check_exit_info(%s)", [plate_number])
                    db_result = cursor.fetchone()
                
                if not db_result:
                    return JsonResponse({
                        'success': False,
                        'message': 'Автомобіль не знайдено на парковці'
                    })
                
                can_exit, user_type, message, user_id, vehicle_id, entry_time, \
                need_payment, parking_id, total_price, hours_parked, is_paid, additional_info = db_result
                
                if not can_exit:
                    return JsonResponse({
                        'success': False,
                        'message': message
                    })
                
                if user_type == 'paying_guest' and not is_paid:
                    has_future_invitation = False
                    invitation_start = None
                    
                    if user_id:
                        with request.db_conn.cursor() as cursor:
                            cursor.execute("SELECT * FROM check_future_invitation(%s, %s)", [user_id, entry_time])
                            future_result = cursor.fetchone()
                            if future_result:
                                has_future_invitation, invitation_start, _ = future_result
                    
                    if has_future_invitation and invitation_start:
                        current_time_naive = timezone.now().replace(tzinfo=None)  # 🔴 timezone вже імпортовано
                        
                        if current_time_naive <= invitation_start:
                            if total_price == 0:
                                try:
                                    with request.db_conn.cursor() as cursor:
                                        cursor.execute("""
                                            SELECT ph.price 
                                            FROM parking_paid pp
                                            JOIN price_history ph ON pp.price_id = ph.id
                                            WHERE pp.id = %s
                                        """, [parking_id])
                                        price_result = cursor.fetchone()
                                        
                                        if price_result:
                                            price_per_hour = price_result[0]
                                            minutes_parked = hours_parked * 60
                                            paid_minutes = max(minutes_parked - 10, 0)
                                            rounded_minutes = math.ceil(paid_minutes / 5.0) * 5.0
                                            recalculated_price = (rounded_minutes / 60.0) * price_per_hour
                                            
                                            if recalculated_price <= 0:
                                                with request.db_conn.cursor() as cursor:
                                                    cursor.execute("""
                                                        UPDATE parking_paid 
                                                        SET is_paid = TRUE, total_price = 0
                                                        WHERE id = %s AND exit_time IS NULL
                                                    """, [parking_id])
                                                request.db_conn.commit()
                                            else:
                                                return JsonResponse({
                                                    'success': False,
                                                    'message': f'Потрібна оплата паркування: {recalculated_price:.2f} грн за {hours_parked:.1f} годин (виїзд до початку запрошення о {invitation_start.strftime("%H:%M")})',
                                                    'need_payment': True,
                                                    'additional_info': additional_info
                                                })
                                except Exception as calc_error:
                                    print(f"Ошибка пересчета: {calc_error}")
                            
                            if hours_parked <= (10 / 60.0):
                                return JsonResponse({
                                    'success': False,
                                    'message': f'Потрібна оплата паркування: {float(total_price) if total_price else 0:.2f} грн за {hours_parked:.1f} годин (виїзд до початку запрошення о {invitation_start.strftime("%H:%M")})',
                                    'need_payment': True,
                                    'additional_info': additional_info
                                })
                            else:
                                return JsonResponse({
                                    'success': False,
                                    'message': f'Потрібна оплата паркування: {float(total_price) if total_price else 0:.2f} грн за {hours_parked:.1f} годин (виїзд до початку запрошення о {invitation_start.strftime("%H:%M")})',
                                    'need_payment': True,
                                    'additional_info': additional_info
                                })
                    
                    if total_price == 0:
                        print(f"Бесплатный выезд для {plate_number} (total_price=0)")
                        with request.db_conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE parking_paid 
                                SET is_paid = TRUE, total_price = 0
                                WHERE id = %s AND exit_time IS NULL
                            """, [parking_id])
                        request.db_conn.commit()

                    free_minutes = 10
                    if hours_parked <= (free_minutes / 60.0):
                        print(f"Бесплатный период! hours_parked={hours_parked}, обновляем БД...")
                        with request.db_conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE parking_paid 
                                SET is_paid = TRUE, total_price = 0
                                WHERE id = %s AND exit_time IS NULL
                            """, [parking_id])
                        request.db_conn.commit()
                        print("Обновление успешно")
                    else:
                        print(f"Требуется оплата: total_price={total_price}")
                        return JsonResponse({
                            'success': False,
                            'message': f'Потрібна оплата паркування: {float(total_price) if total_price else 0:.2f} грн за {hours_parked:.1f} годин',
                            'need_payment': True,
                            'additional_info': additional_info
                        })
                
                # Проверка датчиков
                print("\nПроверка датчиков:")
                arduino_service.update_sensors()
                sensor_readings = arduino_service.get_sensor_readings()
                
                car_waiting = sensor_readings.get('X_B') == 0
                path_clear = sensor_readings.get('X_A') == 1
                
                if not car_waiting:
                    return JsonResponse({
                        'success': False,
                        'message': 'Шлагбаум не відкрито: немає машин на виїзді (перевірте позицію авто)',
                        'sensor_data': sensor_readings,
                        'additional_info': additional_info
                    })
                
                if not path_clear:
                    return JsonResponse({
                        'success': False,
                        'message': 'Шлагбаум не відкрито: шлях після шлагбауму зайнятий',
                        'sensor_data': sensor_readings,
                        'additional_info': additional_info
                    })
                
                with request.db_conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM process_exit(%s)", [plate_number])
                    result = cursor.fetchone()
                
                if not result:
                    return JsonResponse({
                        'success': False,
                        'message': 'Помилка перевірки дозволу на виїзд',
                        'additional_info': additional_info
                    })
                
                success, message, exit_user_type, was_paid, exit_total_price, exit_hours_parked = result
                
                if not success:
                    return JsonResponse({
                        'success': False,
                        'message': f'{message}',
                        'additional_info': additional_info
                    })
                
                if not arduino_service.can_open_exit_barrier():
                    return JsonResponse({
                        'success': False,
                        'message': 'Не вдалося відкрити шлагбаум: змінився стан датчиків',
                        'additional_info': additional_info
                    })
                
                if arduino_service.open_exit_barrier():
                    time.sleep(0.5)
                    
                    final_message = ""
                    if exit_user_type == 'staff':
                        final_message = f"Шлагбаум відкрито. Ви виїхали з паркінгу. Гарного дня, колего!"
                    elif exit_user_type == 'invited_guest':
                        final_message = f"Шлагбаум відкрито. Ви успішно виїхали. Дякуємо за візит!"
                    elif exit_user_type == 'paying_guest':
                        if was_paid:
                            if float(exit_total_price) == 0:
                                final_message = f"Шлагбаум відкрито. Ви успішно виїхали. Дякуємо!"
                            else:
                                final_message = f"Шлагбаум відкрито. Ви виїхали. Сплачено {float(exit_total_price) if exit_total_price else 0:.2f} грн. Дякуємо!"
                        else:
                            final_message = f"Шлагбаум відкрито. Ви успішно виїхали. Гарного дня!"
                    else:
                        final_message = f"{message}"
                    
                    return JsonResponse({
                        'success': True,
                        'message': final_message,
                        'user_type': exit_user_type,
                        'was_paid': was_paid,
                        'total_price': float(exit_total_price) if exit_total_price else 0,
                        'hours_parked': float(exit_hours_parked) if exit_hours_parked else 0,
                        'sensor_data': sensor_readings,
                        'additional_info': additional_info
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'message': 'Помилка відкриття шлагбауму',
                        'additional_info': additional_info
                    })
            
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Невідома дія'
                })
                
        except Exception as e:
            print(f"\n❌ ОШИБКА: {str(e)}")
            import traceback
            traceback.print_exc()
            
            return JsonResponse({
                'success': False,
                'message': f'Помилка сервера: {str(e)[:100]}'
            })
    
    return JsonResponse({'error': 'Invalid method'}, status=400)

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.cache import cache

@csrf_exempt  
@require_POST
def api_set_plate(request):
    """
    API endpoint для получения распознанного номера от recognition_server
    """
    try:
        data = json.loads(request.body)
        plate_number = data.get('plate', '').strip().upper()
        
        if not plate_number:
            return JsonResponse({'error': 'Plate number required'}, status=400)
        
        print(f"\n🎥 Распознан номер: {plate_number}")
        
        cache.set('recognized_plate', plate_number, timeout=30)  # 30 секунд
        
        
        return JsonResponse({
            'success': True,
            'plate': plate_number,
            'message': 'Номер получен'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
def api_get_plate(request):
    """
    API для получения последнего распознанного номера
    """
    plate = cache.get('recognized_plate')
    
    if plate:
        cache.delete('recognized_plate')
        return JsonResponse({
            'success': True,
            'plate': plate,
            'source': 'recognition_server'
        })
    
    return JsonResponse({
        'success': False,
        'plate': None
    })

def api_check_entry_sensor(request):
    """API для проверки датчика въезда"""
    try:
        # Обновляем данные с Arduino
        arduino_service.update_sensors()
        sensor_readings = arduino_service.get_sensor_readings()
        
        # Проверяем, есть ли машина перед шлагбаумом
        car_detected = sensor_readings.get('E_B') == 0
        
        return JsonResponse({
            'success': True,
            'car_detected': car_detected,
            'message': 'Машина біля шлагбаума' if car_detected else 'Під\'їдьте ближче до шлагбаума',
            'sensors': sensor_readings
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'car_detected': False,
            'message': 'Помилка з\'єднання з Arduino'
        })
    
def api_check_exit_sensor(request):
    """API для проверки датчика выезда"""
    try:
        arduino_service.update_sensors()
        sensor_readings = arduino_service.get_sensor_readings()
        
        car_detected = sensor_readings.get('X_B') == 0
        
        return JsonResponse({
            'success': True,
            'car_detected': car_detected,
            'message': 'Машина біля шлагбаума на виїзді' if car_detected else 'Під\'їдьте ближче до шлагбаума на виїзді',
            'sensors': sensor_readings
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'car_detected': False,
            'message': 'Помилка з\'єднання з Arduino'
        })


def api_get_parking_stats(request):
    """API для отримання статистики паркомісць (вільні/зайняті місця)"""
    try:
        stats = arduino_service.get_all_parking_stats()
        
        if stats:
            return JsonResponse({
                'success': True,
                'total_spots': stats.get('total', 0),
                'occupied_spots': stats.get('occupied', 0),
                'free_spots': stats.get('free', 0),
                'occupancy_percent': round((stats.get('occupied', 0) / stats.get('total', 1)) * 100, 1)
            })
        else:
            free_spots = arduino_service.get_free_spots()
            total_spots = arduino_service.get_total_spots()
            
            if free_spots is not None and total_spots is not None:
                occupied = total_spots - free_spots
                return JsonResponse({
                    'success': True,
                    'total_spots': total_spots,
                    'occupied_spots': occupied,
                    'free_spots': free_spots,
                    'occupancy_percent': round((occupied / total_spots) * 100, 1)
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Не вдалося отримати дані з Arduino. Перевірте підключення.'
                })
                
    except Exception as e:
        logger.error(f"Помилка отримання статистики: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Помилка: {str(e)}'
        })


def api_get_free_spots(request):
    """API для отримання тільки кількості вільних місць"""
    try:
        free_spots = arduino_service.get_free_spots()
        
        if free_spots is not None:
            return JsonResponse({
                'success': True,
                'free_spots': free_spots
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Не вдалося отримати дані з Arduino'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


def api_reset_parking_counter(request):
    """API для скидання лічильника паркомісць (тільки для адмінів)"""
    # Перевірка прав доступу
    if request.session.get('user_role') != 'admin_role':
        return JsonResponse({
            'success': False,
            'message': 'Доступ заборонено. Тільки для адміністраторів.'
        }, status=403)
    
    try:
        success = arduino_service.reset_parking_counter()
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Лічильник паркомісць успішно скинуто'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Не вдалося скинути лічильник. Перевірте зв\'язок з Arduino.'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Помилка: {str(e)}'
        })

import json
import math
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import traceback

logger = logging.getLogger(__name__)

def active_parkings_view(request):
    """Вкладка активных парковок"""
    return render(request, 'parking_app/active_parkings.html')

@csrf_exempt
def get_active_parking_info(request):
    """Получение информации об активной парковке по номеру машины"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        plate_number = data.get('plate_number', '').strip().upper()
        
        if not plate_number:
            return JsonResponse({
                'success': False,
                'message': 'Введите номер автомобиля'
            })
        
        with request.db_conn.cursor() as cursor:
            cursor.execute("SELECT * FROM get_active_parking_by_plate(%s)", [plate_number])
            result = cursor.fetchone()
        
        if not result:
            return JsonResponse({
                'success': False,
                'message': 'Автомобиль не найден на парковке',
                'has_parking': False
            })
        
        (user_type, vehicle_id, vehicle_plate, entry_time, current_duration,
         current_duration_hours, free_minutes, need_payment, current_price,
         price_per_hour, parking_id, user_name, additional_info) = result
        
        # Форматируем время
        duration_hours = int(current_duration_hours)
        duration_minutes = int((current_duration_hours - duration_hours) * 60)
        total_minutes = duration_hours * 60 + duration_minutes
        free_minutes_val = int(free_minutes) if free_minutes else 10
        
        # Рассчитываем информацию для отображения
        free_minutes_used = min(free_minutes_val, total_minutes)
        paid_minutes = max(0, total_minutes - free_minutes_val)
        rounded_paid_minutes = math.ceil(paid_minutes / 5.0) * 5.0 if paid_minutes > 0 else 0
        
        response_data = {
            'success': True,
            'has_parking': True,
            'user_type': user_type,
            'vehicle_plate': vehicle_plate,
            'entry_time': entry_time.isoformat() if entry_time else None,
            'duration': {
                'hours': duration_hours,
                'minutes': duration_minutes,
                'total_minutes': total_minutes,
                'formatted': f"{duration_hours} ч {duration_minutes} мин"
            },
            'free_minutes': {
                'total': free_minutes_val,
                'used': free_minutes_used,
                'remaining': max(0, free_minutes_val - free_minutes_used)
            },
            'payment_info': {
                'need_payment': need_payment,
                'paid_minutes': paid_minutes,
                'rounded_paid_minutes': rounded_paid_minutes,
                'price_per_hour': float(price_per_hour) if price_per_hour else 0,
                'current_price': float(current_price) if current_price else 0
            },
            'user_name': user_name,
            'additional_info': additional_info,
            'parking_id': parking_id
        }
        
        # Добавляем сообщение для пользователя
        if user_type == 'staff':
            response_data['message'] = f'Сотрудник {user_name} - бесплатная парковка'
        elif user_type == 'free_guest':
            response_data['message'] = f'Гость {user_name} - бесплатная парковка'
        elif user_type == 'paid_guest':
            if not need_payment:
                response_data['message'] = f'Гость {user_name} - парковка оплачена'
            else:
                free_minutes_left = response_data['free_minutes']['remaining']
                if free_minutes_left > 0:
                    response_data['message'] = f'Гость {user_name} - бесплатно еще {free_minutes_left} мин, затем оплата'
                else:
                    response_data['message'] = f'Гость {user_name} - требуется оплата {response_data["payment_info"]["current_price"]:.2f} грн'
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Ошибка в get_active_parking_info: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'message': f'Ошибка сервера: {str(e)}'
        }, status=500)

@csrf_exempt
def recalculate_parking_price(request):
    """Пересчет цены парковки в реальном времени"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        plate_number = data.get('plate_number', '').strip().upper()
        
        if not plate_number:
            return JsonResponse({
                'success': False,
                'message': 'Введите номер автомобиля'
            })
        
        with request.db_conn.cursor() as cursor:
            cursor.execute("SELECT * FROM get_active_parking_by_plate(%s)", [plate_number])
            result = cursor.fetchone()
        
        if not result:
            return JsonResponse({
                'success': False,
                'message': 'Автомобиль не найден на парковке'
            })
        
        # Распаковываем результат
        (user_type, vehicle_id, vehicle_plate, entry_time, current_duration,
         current_duration_hours, free_minutes, need_payment, current_price,
         price_per_hour, parking_id, user_name, additional_info) = result
        
        # Форматируем данные
        duration_hours = int(current_duration_hours)
        duration_minutes = int((current_duration_hours - duration_hours) * 60)
        total_minutes = duration_hours * 60 + duration_minutes
        free_minutes_val = int(free_minutes) if free_minutes else 10
        
        paid_minutes = max(0, total_minutes - free_minutes_val)
        rounded_paid_minutes = math.ceil(paid_minutes / 5.0) * 5.0 if paid_minutes > 0 else 0
        
        response_data = {
            'success': True,
            'duration': {
                'hours': duration_hours,
                'minutes': duration_minutes,
                'total_minutes': total_minutes,
                'formatted': f"{duration_hours} ч {duration_minutes} мин"
            },
            'free_minutes_remaining': max(0, free_minutes_val - total_minutes),
            'paid_minutes': paid_minutes,
            'rounded_paid_minutes': rounded_paid_minutes,
            'current_price': float(current_price) if current_price else 0,
            'need_payment': need_payment,
            'price_per_hour': float(price_per_hour) if price_per_hour else 0
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Ошибка в recalculate_parking_price: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Ошибка сервера: {str(e)}'
        }, status=500)