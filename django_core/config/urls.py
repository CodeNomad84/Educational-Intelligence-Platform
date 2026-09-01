from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
import requests
from rest_framework.routers import DefaultRouter
from students.views import StudentViewSet
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView 
# تابع test_fastapi_connection (بدون تغییر)
def test_fastapi_connection(request):
    try:
        response = requests.get('http://fastapi:8001/', timeout=5)
        return JsonResponse({
            'status': 'success',
            'fastapi_response': response.json(),
            'message': 'Django successfully connected to FastAPI'
        })
    except requests.exceptions.RequestException as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

# ساخت router
router = DefaultRouter()
router.register(r'students', StudentViewSet, basename='student')

# تعریف urlpatterns
urlpatterns = [
    path('admin/', admin.site.urls),
    path('test-fastapi/', test_fastapi_connection),  # مسیر تست

    # ✅ مسیرهای احراز هویت JWT
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('test-fastapi/', test_fastapi_connection),
    path('', include('dashboard.urls')),  
    path('api/', include(router.urls)),  # همه APIها زیر api/ قرار می‌گیرند
]