from django.urls import path
from . import views

app_name = 'automacao'

urlpatterns = [
    path('sincronizar/', views.sincronizar, name='sincronizar'),
]