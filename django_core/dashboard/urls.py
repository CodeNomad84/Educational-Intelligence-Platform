from django.urls import path
from . import counselor_views, school_views, student360, teacher_views, views

app_name = 'dashboard'

urlpatterns = [
    path('', views.login_view, name='login'),          # صفحه‌ی ورود (root)
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),  
    path('students/', views.student_list_view, name='student_list'),
    path('students/<int:pk>/', views.student_detail_view, name='student_detail'),
    path('students/<int:pk>/360/', student360.student_360, name='student_360'),
    path('upload/', views.upload_students_view, name='upload_students'),
    path('chat/', views.chat_view, name='chat'),
    path('library/', views.library_view, name='library'),
    path('upload-document/', views.upload_document_view, name='upload_document'),
    path('delete-document/', views.delete_document_view, name='delete_document'),
    path('students/add/', views.student_create_view, name='student_add'),

    # Referral and Counselor pages (Slice 4a)
    path('students/<int:pk>/refer/', counselor_views.student_refer, name='student_refer'),
    path('counselor/', counselor_views.home, name='counselor_home'),
    path('counselor/case/<int:pk>/', counselor_views.case, name='counselor_case'),
    path('counselor/case/<int:pk>/close/', counselor_views.case_close, name='counselor_close'),

    # Subject Teacher pages (Slice 2)
    path('teacher/', teacher_views.home, name='teacher_home'),
    path('teacher/<int:pk>/grades/', teacher_views.grade_sheet, name='teacher_grades'),
    path('teacher/<int:pk>/grades/<int:grade_pk>/delete/', teacher_views.grade_delete, name='teacher_grade_delete'),
    path('teacher/<int:pk>/students/<int:student_pk>/', teacher_views.student_page, name='teacher_student'),

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
