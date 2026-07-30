"""
URL configuration for parking project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# parking_system/urls.py
from django.contrib import admin
from django.urls import path, include
from parking_app.views import home  # импортируем view из parking_app

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),  # корень сразу на главную
    path('parking/', include('parking_app.urls', namespace='parking_app')),
    path('arduino/', include('arduino_api.urls')),  # новое приложение
]