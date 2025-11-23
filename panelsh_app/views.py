from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from lib.auth import authorized, hash_password
from lib.utils import connect_to_redis, get_node_network_metadata
from settings import settings

from .helpers import (
    template,
)

r = connect_to_redis()


@authorized
def react(request):
    return template(request, 'react.html', {})


@require_http_methods(["GET", "POST"])
def login(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        if settings.auth._check(username, password):
            # Store only hashed credentials in session
            request.session['auth_username'] = username
            request.session['auth_password_hash'] = hash_password(password)

            return redirect(reverse('panelsh_app:react'))
        else:
            messages.error(request, 'Invalid username or password')
            return template(request, 'login.html', {
                'next': request.GET.get('next', '/')
            })

    return template(request, 'login.html', {
        'next': request.GET.get('next', '/')
    })


@require_http_methods(["GET"])
def splash_page(request):
    return template(request, 'splash-page.html', {
        'ip_addresses': get_node_network_metadata()['ip_addresses']
    })


@require_http_methods(["GET"])
def splash_page_metadata(request):
    return JsonResponse(get_node_network_metadata())
