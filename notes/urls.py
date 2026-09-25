from django.urls import path

from . import views


urlpatterns = [
    path('', views.shift_table, name='shift_table'),
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/new/', views.staff_create, name='staff_create'),
    path('staff/<int:pk>/edit/', views.staff_update, name='staff_update'),
    path('staff/<int:pk>/salary-visibility/', views.staff_salary_visibility, name='staff_salary_visibility'),
    path('salary/', views.salary_list, name='salary_list'),
    path('salary/settings/', views.salary_settings, name='salary_settings'),
    path('salary/staff/<int:pk>/settings/', views.staff_salary_settings, name='staff_salary_settings'),
    path('shift-types/', views.shift_type_list, name='shift_type_list'),
    path('shift-types/new/', views.shift_type_create, name='shift_type_create'),
    path('shift-types/<int:pk>/edit/', views.shift_type_update, name='shift_type_update'),
    path('shift-types/<int:pk>/delete/', views.shift_type_delete, name='shift_type_delete'),
    path('actuals/<str:work_date>/', views.actual_work_edit, name='actual_work_edit'),
    path('shifts/new/', views.shift_create, name='shift_create'),
    path('shifts/<int:pk>/edit/', views.shift_update, name='shift_update'),
    path('shifts/<int:pk>/delete/', views.shift_delete, name='shift_delete'),
]
