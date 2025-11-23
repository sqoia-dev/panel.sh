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

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300


def _client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _login_blocked(ip_address):
    block_key = f"login_blocked:{ip_address}"
    return bool(r and r.get(block_key))


def _record_failed_login(ip_address):
    attempts_key = f"login_attempts:{ip_address}"
    block_key = f"login_blocked:{ip_address}"

    if not r:
        return

    attempts = r.incr(attempts_key)
    if attempts == 1:
        r.expire(attempts_key, LOCKOUT_WINDOW_SECONDS)

    if attempts >= MAX_LOGIN_ATTEMPTS:
        r.setex(block_key, LOCKOUT_WINDOW_SECONDS, 1)


def _reset_login_attempts(ip_address):
    attempts_key = f"login_attempts:{ip_address}"
    block_key = f"login_blocked:{ip_address}"

    if not r:
        return

    r.delete(attempts_key)
    r.delete(block_key)


@authorized
def react(request):
    return template(request, 'react.html', {})


@require_http_methods(["GET", "POST"])
def login(request):
    if request.method == "POST":
        client_ip = _client_ip(request)

        if _login_blocked(client_ip):
            messages.error(request, 'Too many login attempts. Please try again later.')
            return template(request, 'login.html', {
                'next': request.GET.get('next', '/')
            })

        username = request.POST.get('username')
        password = request.POST.get('password')

        if settings.auth._check(username, password):
            # Store only hashed credentials in session
            request.session['auth_username'] = username
            request.session['auth_password_hash'] = hash_password(password)

            _reset_login_attempts(client_ip)

            return redirect(reverse('panelsh_app:react'))
        else:
            _record_failed_login(client_ip)
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
