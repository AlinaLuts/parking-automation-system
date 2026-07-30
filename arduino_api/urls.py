from django.urls import path
from . import views

app_name = 'arduino_api'

urlpatterns = [
    path('test-control/', views.test_control_view, name='test_control'),
]