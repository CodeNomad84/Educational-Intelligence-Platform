from django.urls import path

from . import views, views_reports

app_name = 'missions'
urlpatterns = [
    path('', views.activities, name='activities'),
    path('activities/<int:pk>/grid/', views.grid, name='grid'),
    path('students/', views_reports.students, name='students'),
    path('students/<int:pk>/report/', views_reports.report, name='report'),
    path('students/<int:pk>/plan/', views_reports.plan, name='plan'),
    path('students/<int:pk>/choices/', views_reports.choices, name='choices'),
    path('students/<int:pk>/meetings/', views_reports.meetings, name='meetings'),
    path('aggregate/', views_reports.aggregate, name='aggregate'),
]
