# parking_app/urls.py
from django.urls import path
from . import views

app_name = 'parking_app'  # важно для namespace!

urlpatterns = [
    # Основные страницы
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Администратор
    path('admin/register-staff/', views.admin_register_staff, name='admin_register_staff'),
    path('admin/staff-list/', views.admin_staff_list, name='admin_staff_list'),
    path('admin/create-price/', views.admin_create_price, name='admin_create_price'),
    path('admin/price-list/', views.admin_price_list, name='admin_price_list'),
    path('admin/price/<int:price_id>/edit/', views.admin_edit_price, name='admin_edit_price'),
    path('admin/price/<int:price_id>/delete/', views.admin_delete_price, name='admin_delete_price'),
    path('admin/staff/<int:staff_id>/edit/', views.admin_edit_staff, name='admin_edit_staff'),
    path('admin/staff/<int:staff_id>/fire/', views.admin_fire_staff, name='admin_fire_staff'),
    path('admin/staff/<int:staff_id>/restore/', views.admin_restore_staff, name='admin_restore_staff'),
    path('admin/parking-history/', views.admin_parking_history, name='admin_parking_history'),
    path('admin/financial-report/', views.admin_financial_report, name='admin_financial_report'),
    path('admin/current-parking/', views.admin_current_parking, name='admin_current_parking'),

    # Працівник
    path('staff/add-vehicle/', views.staff_add_vehicle, name='staff_add_vehicle'),
    path('staff/edit-vehicle/<str:plate_number>/', views.staff_edit_vehicle, name='staff_edit_vehicle'),
    path('staff/delete-vehicle/<str:plate_number>/', views.staff_delete_vehicle, name='staff_delete_vehicle'),
    path('staff/parking-history/', views.staff_parking_history, name='staff_parking_history'),
    path('staff/create-invitation/', views.staff_create_invitation, name='staff_create_invitation'),
    path('staff/invitations/', views.staff_invitations, name='staff_invitations'),
    
    # Гость/Сторонний
    path('guest/login/', views.guest_login, name='guest_login'),
    path('guest/dashboard/', views.guest_dashboard, name='guest_dashboard'),
    path('visitor/dashboard/', views.visitor_dashboard, name='visitor_dashboard'),
    path('guest/logout/', views.guest_logout, name='guest_logout'),
    
    # Посетители
    path('visitor/dashboard/', views.visitor_dashboard, name='visitor_dashboard'),

    path('guest/edit-profile/', views.guest_edit_profile, name='guest_edit_profile'),
    path('guest/add-vehicle/', views.guest_add_vehicle, name='guest_add_vehicle'),
    path('guest/history/', views.guest_parking_history, name='guest_parking_history'),
    path('active-parkings/', views.active_parkings_view, name='active_parkings'),
    # Общие
    path('entry/', views.process_entry_view, name='process_entry'),
    path('exit/', views.process_exit_view, name='process_exit'),
    path('test_sensors/', views.test_sensors_view, name='test_sensors'),
    path('api/set_plate/', views.api_set_plate, name='api_set_plate'),
    path('api/get_plate/', views.api_get_plate, name='api_get_plate'),
    path('api/check-entry-sensor/', views.api_check_entry_sensor, name='api_check_entry_sensor'),
    path('api/check-exit-sensor/', views.api_check_exit_sensor, name='api_check_exit_sensor'),
    # НОВІ API для паркомісць
    path('api/parking-stats/', views.api_get_parking_stats, name='api_parking_stats'),
    path('api/free-spots/', views.api_get_free_spots, name='api_free_spots'),
    path('api/reset-counter/', views.api_reset_parking_counter, name='api_reset_counter'),

    
    path('api/active-parking/', views.get_active_parking_info, name='get_active_parking'),
    path('api/recalculate-price/', views.recalculate_parking_price, name='recalculate_price'),
]