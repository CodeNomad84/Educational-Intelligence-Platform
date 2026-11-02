from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from students.views import StudentViewSet
from dashboard.throttle import ThrottledTokenObtainPairView, throttled_admin_login
from rest_framework_simplejwt.views import TokenRefreshView

# ساخت router
router = DefaultRouter()
router.register(r'students', StudentViewSet, basename='student')

admin.site.login = throttled_admin_login(admin.site.login)   # /admin/ login: same brute-force limits as /login/

# تعریف urlpatterns
urlpatterns = [
    path('admin/', admin.site.urls),

    # ✅ مسیرهای احراز هویت JWT
    path('api/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('mission/', include('missions.urls')),
    path('exams/', include('exams.urls')),
    path('rules/', include('risk.urls')),
    path('assistant/', include('docqa.urls')),
    path('', include('dashboard.urls')),  
    path('api/', include(router.urls)),  # همه APIها زیر api/ قرار می‌گیرند
]