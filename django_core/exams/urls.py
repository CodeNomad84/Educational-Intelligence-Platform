from django.urls import path

from . import views, views_import, views_results

app_name = 'exams'
urlpatterns = [
    path('', views.student_home, name='student_home'),
    path('<int:pk>/play/', views.play, name='play'),
    path('teacher/', views.teacher_home, name='teacher_home'),
    path('teacher/topics/', views.topics, name='topics'),
    path('teacher/questions/new/', views.question_edit, name='question_new'),
    path('teacher/questions/<int:pk>/', views.question_edit, name='question_edit'),
    path('teacher/questions/<int:pk>/status/', views.question_status, name='question_status'),
    path('teacher/exams/new/', views.exam_new, name='exam_new'),
    path('teacher/exams/<int:pk>/unpublish/', views.exam_unpublish, name='exam_unpublish'),
    path('teacher/exams/<int:pk>/edit/', views.exam_edit, name='exam_edit'),
    path('teacher/exams/<int:pk>/results/', views_results.exam_results, name='exam_results'),
    path('teacher/import/', views_import.import_form, name='import_form'),
    path('teacher/import/template/', views_import.import_template, name='import_template'),
    path('teacher/import/preview/', views_import.import_preview, name='import_preview'),
    path('teacher/import/confirm/', views_import.import_confirm, name='import_confirm'),
    path('teacher/import/cancel/', views_import.import_cancel, name='import_cancel'),
    path('lead/', views_results.lead_overview, name='lead_overview'),
    path('admin/', views_results.admin_overview, name='admin_overview'),
]
