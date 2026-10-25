from django.urls import path

from . import views, views_reports, views_weights

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
    path('weights/', views_reports.weights, name='weights'),
    path('weights/<int:pk>/', views_weights.detail, name='weight_detail'),
    path('weights/<int:pk>/action/', views_weights.action, name='weight_action'),
    path('weights/<int:pk>/simulation/', views_weights.simulation, name='weight_simulation'),
]
