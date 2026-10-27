from django.urls import path

from . import views

app_name = 'rules'
urlpatterns = [
    path('', views.index, name='index'),
    path('settings/', views.save_settings, name='settings'),
    path('run/', views.run_now, name='run'),
    path('new/', views.create, name='create'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/action/', views.action, name='action'),
]
