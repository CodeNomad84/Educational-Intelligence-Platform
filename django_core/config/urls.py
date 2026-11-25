from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from students.views import StudentViewSet
from dashboard.ai_api import AIChatView, AIStatusView
from dashboard.platform_api import PlatformGlobalStatsView
from dashboard.summary_api import DashboardSummaryView
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
    # JSON session auth for the presentation frontends (ADR-0014, docs/changes/0040): csrf/, login/, logout/, me/.
    # Additive: /api/token/ above is unchanged and keeps working for machine clients.
    path('api/auth/', include('dashboard.auth_api')),
    # JSON dashboard summary for the two presentation frontends (Phase 3): /api/dashboard/.
    path('api/dashboard/', DashboardSummaryView.as_view(), name='api_dashboard_summary'),
    # Platform Admin (Ministry) aggregate report: /api/platform/global-stats/ (platform operators only).
    path('api/platform/global-stats/', PlatformGlobalStatsView.as_view(), name='api_platform_global_stats'),
    # Mentor assistant (رهنما) health + chat for the presentation frontends.
    path('api/ai/status/', AIStatusView.as_view(), name='api_ai_status'),
    path('api/ai/chat/', AIChatView.as_view(), name='api_ai_chat'),
    path('mission/', include('missions.urls')),
    path('exams/', include('exams.urls')),
    path('rules/', include('risk.urls')),
    path('assistant/', include('docqa.urls')),
    path('', include('dashboard.urls')),  
    path('api/', include(router.urls)),  # همه APIها زیر api/ قرار می‌گیرند
]