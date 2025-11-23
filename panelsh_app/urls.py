from django.urls import path, re_path

from . import views

app_name = 'panelsh_app'

urlpatterns = [
    path('splash-page', views.splash_page, name='splash_page'),
    path('api/splash-page-metadata', views.splash_page_metadata, name='splash_page_metadata'),
    path('login/', views.login, name='login'),
    re_path(r'^(?!api/).*$', views.react, name='react'),
]
