# parking_system/db_config.py

import psycopg2
from django.utils.deprecation import MiddlewareMixin

ROLE_CONNECTIONS = {
    "admin_role": {
        "USER": "parking_admin_role",
        "PASSWORD": "AdminPass123!",
    },
    "staff_role": {
        "USER": "parking_staff_role",
        "PASSWORD": "StaffPass123!",
    },
    "guest_role": {
        "USER": "parking_guest_role",
        "PASSWORD": "GuestPass123!",
    },
    "visitor_role": {
        "USER": "parking_visitor_role",
        "PASSWORD": "VisitorPass123!",
    },
    "arduino_role": {
        "USER": "parking_arduino_role",
        "PASSWORD": "ArduinoPass123!",
    },
}

def get_connection_for_role(role):
    creds = ROLE_CONNECTIONS.get(role)
    if not creds:
        raise Exception(f"Невідома роль: {role}")
    return psycopg2.connect(
        dbname="parking",
        user=creds["USER"],
        password=creds["PASSWORD"],
        host="localhost",
        port="5432"
    )

class RoleBasedDBConnectionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Определяем роль по URL или сессии
        if request.path.startswith('/arduino/'):
            role = "arduino_role"
        else:
            role = request.session.get("user_role", "visitor_role")
        
        request.session["user_role"] = role
        
        try:
            request.db_conn = get_connection_for_role(role)
            request.db_conn.autocommit = True
        except Exception as e:
            print(f"[DB Middleware] Помилка з'єднання для ролі {role}:", e)
            request.db_conn = None

    def process_response(self, request, response):
        conn = getattr(request, "db_conn", None)
        if conn:
            conn.close()
        return response