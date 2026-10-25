from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from students.views import StudentViewSet
from dashboard.throttle import ThrottledTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

# ساخت router
router = DefaultRouter()
router.register(r'students', StudentViewSet, basename='student')

# تعریف urlpatterns
urlpatterns = [
    path('admin/', admin.site.urls),

    # ✅ مسیرهای احراز هویت JWT
    path('api/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('mission/', include('missions.urls')),
    path('exams/', include('exams.urls')),
    path('', include('dashboard.urls')),  
    path('api/', include(router.urls)),  # همه APIها زیر api/ قرار می‌گیرند
]