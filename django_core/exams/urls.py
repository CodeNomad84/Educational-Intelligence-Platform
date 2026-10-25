from django.urls import path

from . import views

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
]
