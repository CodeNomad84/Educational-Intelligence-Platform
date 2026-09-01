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