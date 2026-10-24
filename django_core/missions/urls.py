from django.urls import path

from . import views

app_name = 'missions'
urlpatterns = [
    path('', views.activities, name='activities'),
    path('activities/<int:pk>/grid/', views.grid, name='grid'),
]
