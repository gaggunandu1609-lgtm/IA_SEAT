from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_data, name='upload_data'),
    path('generate-seating/', views.generate_seating, name='generate_seating'),
    path('generate-teachers/', views.generate_teachers, name='generate_teachers'),
    path('clear-data/', views.clear_data, name='clear_data'),
    path('reports/seating/', views.seating_reports, name='seating_reports'),
    path('reports/teachers/', views.teacher_reports, name='teacher_reports'),
    
    # Students Management routes
    path('students/list/', views.student_list, name='student_list'),
    path('students/add/', views.student_add, name='student_add'),
    path('students/delete/<int:student_id>/', views.student_delete, name='student_delete'),
]
