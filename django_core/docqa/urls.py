from django.urls import path

from . import views

app_name = 'docqa'
urlpatterns = [
    path('', views.home, name='home'),
    path('documents/', views.documents, name='documents'),
    path('documents/<int:pk>/', views.document_action, name='document_action'),
    path('setting/', views.ai_setting, name='ai_setting'),
]
