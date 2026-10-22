from django.urls import path
from . import school_views, views

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

    # SchoolAdmin pages (Slice 1)
    path('school/', school_views.home, name='school_home'),
    path('school/years/', school_views.years, name='school_years'),
    path('school/years/<int:pk>/current/', school_views.year_set_current, name='school_year_current'),
    path('school/classes/', school_views.classes, name='school_classes'),
    path('school/classes/new/', school_views.class_edit, name='school_class_new'),
    path('school/classes/<int:pk>/edit/', school_views.class_edit, name='school_class_edit'),
    path('school/<str:kind>/', school_views.staff_list, name='school_staff'),
    path('school/<str:kind>/<int:pk>/', school_views.staff_detail, name='school_staff_detail'),
    path('school/<str:kind>/<int:pk>/active/', school_views.staff_toggle_active, name='school_staff_active'),
    path('school/<str:kind>/<int:pk>/assignments/<int:assignment_pk>/delete/', school_views.assignment_delete,
         name='school_assignment_delete'),

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
