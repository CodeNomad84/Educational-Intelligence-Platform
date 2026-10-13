from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.login_view, name='login'),          # صفحه‌ی ورود (root)
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),  
    path('students/', views.student_list_view, name='student_list'),
    path('students/<int:pk>/', views.student_detail_view, name='student_detail'),
    path('upload/', views.upload_students_view, name='upload_students'),
    path('chat/', views.chat_view, name='chat'),
    path('library/', views.library_view, name='library'),
    path('upload-document/', views.upload_document_view, name='upload_document'),
    path('delete-document/', views.delete_document_view, name='delete_document'),
    path('students/add/', views.student_create_view, name='student_add'),

]

# DEMO SCOPE begin — extra routes, registered only when config.settings.demo is active
from django.conf import settings as _demo_settings
if getattr(_demo_settings, 'DEMO_MODE', False):
    from demo_intel import views as demo_views
    urlpatterns += [
        path('demo/counselor/', demo_views.counselor_view, name='demo_counselor'),
        path('demo/students/', demo_views.demo_student_list, name='demo_students'),
        path('demo/assistant/', demo_views.assistant_view, name='demo_assistant'),
    ]
# DEMO SCOPE end
