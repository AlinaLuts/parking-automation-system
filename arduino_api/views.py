# arduino_api/views.py
from django.shortcuts import render
from django.http import JsonResponse
from .serial_service import arduino_service

def test_control_view(request):
    """Тестовая страница управления Arduino"""
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'open_entry':
            success = arduino_service.open_entry_barrier()
            response = arduino_service.read_response()
            return JsonResponse({'success': success, 'response': response})
        
        elif action == 'close_entry':
            success = arduino_service.close_entry_barrier()
            response = arduino_service.read_response()
            return JsonResponse({'success': success, 'response': response})
        
        elif action == 'status':
            arduino_service.send_command("STATUS")
            response = arduino_service.read_response()
            return JsonResponse({'success': True, 'response': response})
    
    return render(request, 'arduino_api/test_control.html')