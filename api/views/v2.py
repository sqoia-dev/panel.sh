import hashlib
import ipaddress
import json
import logging
from datetime import timedelta
from os import getenv, statvfs
from platform import machine

import psutil
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from hurry.filesize import size
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from celery_tasks import add_default_assets_task, remove_default_assets_task
from panelsh_app.models import Asset
from api.helpers import (
    AssetCreationError,
    get_active_asset_ids,
    save_active_assets_ordering,
)
from api.serializers.v2 import (
    AssetSerializerV2,
    CreateAssetSerializerV2,
    DeviceSettingsSerializerV2,
    IntegrationsSerializerV2,
    UpdateAssetSerializerV2,
    UpdateDeviceSettingsSerializerV2,
)
from api.views.mixins import (
    AssetContentViewMixin,
    AssetsControlViewMixin,
    BackupViewMixin,
    DeleteAssetViewMixin,
    FileAssetViewMixin,
    InfoViewMixin,
    PlaylistOrderViewMixin,
    RebootViewMixin,
    RecoverViewMixin,
    ShutdownViewMixin,
)
from lib import device_helper, diagnostics
from lib.auth import authorized, hash_password
from lib.github import is_up_to_date
from lib.utils import (
    check_redis_health,
    check_zmq_health,
    connect_to_redis,
    get_node_ip,
    get_node_mac_address,
    is_balena_app,
)
from settings import ZmqPublisher, settings

r = connect_to_redis()
logger = logging.getLogger(__name__)


class AssetListViewV2(APIView):
    serializer_class = AssetSerializerV2

    @staticmethod
    def _parse_bool_query_param(value, name):
        if value is None:
            return None

        normalized = value.strip().lower()

        if normalized in {'1', 'true', 'yes', 'on'}:
            return True

        if normalized in {'0', 'false', 'no', 'off'}:
            return False

        raise ValueError(f"Invalid boolean value for '{name}'")

    @staticmethod
    def _generate_etag(payload):
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        digest = hashlib.md5(serialized.encode('utf-8')).hexdigest()
        return f'W/"{digest}"'

    def _matches_if_none_match(self, request, etag):
        client_header = request.headers.get('If-None-Match')
        if not client_header:
            return False

        for candidate in client_header.split(','):
            if candidate.strip() == etag:
                return True

        return False

    @extend_schema(
        summary='List assets',
        responses={
            200: AssetSerializerV2(many=True)
        }
    )
    @authorized
    def get(self, request):
        queryset = Asset.objects.all()

        try:
            is_enabled = self._parse_bool_query_param(
                request.query_params.get('is_enabled'), 'is_enabled')
            is_active = self._parse_bool_query_param(
                request.query_params.get('is_active'), 'is_active')
        except ValueError as error:
            return Response({'detail': str(error)},
                            status=status.HTTP_400_BAD_REQUEST)

        search_term = request.query_params.get('search')

        if is_enabled is not None:
            queryset = queryset.filter(is_enabled=is_enabled)

        if is_active is not None:
            current_time = timezone.now()
            active_filter = Q(is_enabled=True,
                              start_date__lt=current_time,
                              end_date__gt=current_time)

            if is_active:
                queryset = queryset.filter(active_filter)
            else:
                queryset = queryset.exclude(active_filter)

        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term) | Q(uri__icontains=search_term)
            )

        queryset = queryset.order_by('play_order', 'asset_id')

        page = request.query_params.get('page')
        page_size = request.query_params.get('page_size')

        if page or page_size:
            try:
                page_number = int(page) if page else 1
                page_limit = int(page_size) if page_size else 50
            except ValueError:
                return Response(
                    {'detail': 'Pagination parameters must be integers.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if page_number < 1 or page_limit < 1:
                return Response(
                    {'detail': 'Pagination parameters must be greater than 0.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            start = (page_number - 1) * page_limit
            end = start + page_limit
            total_count = queryset.count()
            paginated_queryset = queryset[start:end]
            serializer = AssetSerializerV2(paginated_queryset, many=True)
            response_payload = {
                'count': total_count,
                'page': page_number,
                'page_size': page_limit,
                'results': serializer.data,
            }

            etag = self._generate_etag(response_payload)

            if self._matches_if_none_match(request, etag):
                response = Response(status=status.HTTP_304_NOT_MODIFIED)
                response['ETag'] = etag
                return response

            response = Response(response_payload)
            response['ETag'] = etag
            return response

        serializer = AssetSerializerV2(queryset, many=True)
        response_payload = serializer.data
        etag = self._generate_etag(response_payload)

        if self._matches_if_none_match(request, etag):
            response = Response(status=status.HTTP_304_NOT_MODIFIED)
            response['ETag'] = etag
            return response

        response = Response(response_payload)
        response['ETag'] = etag
        return response

    @extend_schema(
        summary='Create asset',
        request=CreateAssetSerializerV2,
        responses={
            201: AssetSerializerV2
        }
    )
    @authorized
    def post(self, request):
        try:
            serializer = CreateAssetSerializerV2(
                data=request.data, unique_name=True)

            if not serializer.is_valid():
                raise AssetCreationError(serializer.errors)
        except AssetCreationError as error:
            return Response(error.errors, status=status.HTTP_400_BAD_REQUEST)

        active_asset_ids = get_active_asset_ids()
        asset = Asset.objects.create(**serializer.data)
        asset.refresh_from_db()

        if asset.is_active():
            active_asset_ids.insert(asset.play_order, asset.asset_id)

        save_active_assets_ordering(active_asset_ids)
        asset.refresh_from_db()

        return Response(
            AssetSerializerV2(asset).data,
            status=status.HTTP_201_CREATED,
        )


class AssetViewV2(APIView, DeleteAssetViewMixin):
    serializer_class = AssetSerializerV2

    @extend_schema(summary='Get asset')
    @authorized
    def get(self, request, asset_id):
        try:
            asset = Asset.objects.get(asset_id=asset_id)
        except Asset.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(asset)
        return Response(serializer.data)

    def update(self, request, asset_id, partial=False):
        try:
            asset = Asset.objects.get(asset_id=asset_id)
        except Asset.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateAssetSerializerV2(
            asset, data=request.data, partial=partial)

        if serializer.is_valid():
            serializer.save()
        else:
            return Response(
                serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        active_asset_ids = get_active_asset_ids()

        asset.refresh_from_db()

        try:
            active_asset_ids.remove(asset.asset_id)
        except ValueError:
            pass

        if asset.is_active():
            active_asset_ids.insert(asset.play_order, asset.asset_id)

        save_active_assets_ordering(active_asset_ids)
        asset.refresh_from_db()

        return Response(AssetSerializerV2(asset).data)

    @extend_schema(
        summary='Update asset',
        request=UpdateAssetSerializerV2,
        responses={
            200: AssetSerializerV2
        }
    )
    @authorized
    def patch(self, request, asset_id):
        return self.update(request, asset_id, partial=True)

    @extend_schema(
        summary='Update asset',
        request=UpdateAssetSerializerV2,
        responses={
            200: AssetSerializerV2
        }
    )
    @authorized
    def put(self, request, asset_id):
        return self.update(request, asset_id, partial=False)


class BackupViewV2(BackupViewMixin):
    pass


class RecoverViewV2(RecoverViewMixin):
    pass


class RebootViewV2(RebootViewMixin):
    pass


class ShutdownViewV2(ShutdownViewMixin):
    pass


class FileAssetViewV2(FileAssetViewMixin):
    pass


class AssetContentViewV2(AssetContentViewMixin):
    pass


class PlaylistOrderViewV2(PlaylistOrderViewMixin):
    pass


class AssetsControlViewV2(AssetsControlViewMixin):
    pass


class DeviceSettingsViewV2(APIView):
    @extend_schema(
        summary='Get device settings',
        responses={
            200: DeviceSettingsSerializerV2
        }
    )
    @authorized
    def get(self, request):
        try:
            # Force reload of settings
            settings.load()
        except FileNotFoundError as error:
            logging.error("Settings file missing during reload: %s", error)
            return Response(
                {
                    'error': 'settings_not_found',
                    'message': 'Settings file missing during reload',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except PermissionError as error:
            logging.error("Permission denied reloading settings: %s", error)
            return Response(
                {
                    'error': 'settings_permission_denied',
                    'message': 'Permission denied reloading settings',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception:
            logging.exception('Unexpected error reloading settings')
            return Response(
                {
                    'error': 'settings_reload_failed',
                    'message': 'Failed to reload device settings',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        filesystem_stats = statvfs("/")
        total_storage = filesystem_stats.f_frsize * filesystem_stats.f_blocks
        free_storage = filesystem_stats.f_frsize * filesystem_stats.f_bavail
        used_storage = total_storage - free_storage
        percent_used = (
            round((used_storage / total_storage) * 100, 2)
            if total_storage
            else 0
        )

        return Response({
            'player_name': settings['player_name'],
            'audio_output': settings['audio_output'],
            'default_duration': int(settings['default_duration']),
            'default_streaming_duration': int(
                settings['default_streaming_duration']
            ),
            'date_format': settings['date_format'],
            'auth_backend': settings['auth_backend'],
            'show_splash': settings['show_splash'],
            'default_assets': settings['default_assets'],
            'shuffle_playlist': settings['shuffle_playlist'],
            'use_24_hour_clock': settings['use_24_hour_clock'],
            'debug_logging': settings['debug_logging'],
            'username': (
                settings['user'] if settings['auth_backend'] == 'auth_basic'
                else ''
            ),
            'storage': {
                'total': total_storage,
                'used': used_storage,
                'free': free_storage,
                'percent_used': percent_used,
            },
        })

    def update_auth_settings(self, data, auth_backend, current_pass_correct):
        if auth_backend == '':
            return

        if auth_backend != 'auth_basic':
            return

        new_user = data.get('username')
        new_pass = data.get('password', '')
        new_pass2 = data.get('password_2', '')
        new_pass = hash_password(new_pass) if new_pass else None
        new_pass2 = hash_password(new_pass2) if new_pass2 else None

        target_user = new_user if new_user is not None else settings.get('user', '')
        if (new_pass or settings['password']) and not target_user:
            raise ValueError("Must provide username when password is set")

        if settings['password']:
            if new_user is not None and new_user != settings['user']:
                if current_pass_correct is None:
                    raise ValueError(
                        "Must supply current password to change username"
                    )
                if not current_pass_correct:
                    raise ValueError("Incorrect current password.")

                settings['user'] = new_user

            if new_pass:
                if current_pass_correct is None:
                    raise ValueError(
                        "Must supply current password to change password"
                    )
                if not current_pass_correct:
                    raise ValueError("Incorrect current password.")

                if new_pass2 != new_pass:
                    raise ValueError("New passwords do not match!")

                settings['password'] = new_pass

        else:
            if new_user:
                if new_pass and new_pass != new_pass2:
                    raise ValueError("New passwords do not match!")
                if not new_pass:
                    raise ValueError("Must provide password")
                settings['user'] = new_user
                settings['password'] = new_pass
            else:
                raise ValueError("Must provide username")

    @extend_schema(
        summary='Update device settings',
        request=UpdateDeviceSettingsSerializerV2,
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'message': {'type': 'string'}
                }
            },
            400: {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'},
                    'error_type': {'type': 'string'},
                }
            },
            500: {
                'type': 'object',
                'properties': {
                    'error': {'type': 'string'},
                    'error_type': {'type': 'string'},
                }
            },
        }
    )
    @authorized
    def patch(self, request):
        try:
            serializer = UpdateDeviceSettingsSerializerV2(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=400)

            data = serializer.validated_data
            settings.load()

            current_password = data.get('current_password', '')
            auth_backend = data.get('auth_backend', '')

            if (
                auth_backend != settings['auth_backend']
                and settings['auth_backend']
            ):
                if not current_password:
                    raise ValueError(
                        "Must supply current password to change "
                        "authentication method"
                    )
                if not settings.auth.check_password(current_password):
                    raise ValueError("Incorrect current password.")

            prev_auth_backend = settings['auth_backend']
            if not current_password and prev_auth_backend:
                current_pass_correct = None
            else:
                current_pass_correct = (
                    settings
                    .auth_backends[prev_auth_backend]
                    .check_password(current_password)
                )
            next_auth_backend = settings.auth_backends[auth_backend]

            self.update_auth_settings(
                data, next_auth_backend.name, current_pass_correct)
            settings['auth_backend'] = auth_backend

            # Update settings
            if 'player_name' in data:
                settings['player_name'] = data['player_name']
            if 'default_duration' in data:
                settings['default_duration'] = data['default_duration']
            if 'default_streaming_duration' in data:
                settings['default_streaming_duration'] = (
                    data['default_streaming_duration']
                )
            if 'audio_output' in data:
                settings['audio_output'] = data['audio_output']
            if 'date_format' in data:
                settings['date_format'] = data['date_format']
            if 'show_splash' in data:
                settings['show_splash'] = data['show_splash']
            if 'default_assets' in data:
                if data['default_assets'] and not settings['default_assets']:
                    add_default_assets_task.delay()
                elif not data['default_assets'] and settings['default_assets']:
                    remove_default_assets_task.delay()
                settings['default_assets'] = data['default_assets']
            if 'shuffle_playlist' in data:
                settings['shuffle_playlist'] = data['shuffle_playlist']
            if 'use_24_hour_clock' in data:
                settings['use_24_hour_clock'] = data['use_24_hour_clock']
            if 'debug_logging' in data:
                settings['debug_logging'] = data['debug_logging']

            settings.save()
            publisher = ZmqPublisher.get_instance()
            publisher.send_to_viewer('reload')

            return Response({'message': 'Settings were successfully saved.'})
        except ValueError as error:
            logger.warning(
                'Validation error while saving device settings',
                exc_info=True,
            )
            return Response(
                {
                    'error': str(error),
                    'error_type': type(error).__name__,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as error:
            logger.exception('Unexpected error while saving device settings')
            return Response(
                {
                    'error': str(error),
                    'error_type': type(error).__name__,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class InfoViewV2(InfoViewMixin):
    def get_panelsh_version(self):
        git_branch = diagnostics.get_git_branch()
        git_short_hash = diagnostics.get_git_short_hash()

        return '{}@{}'.format(
            git_branch,
            git_short_hash,
        )

    def get_device_model(self):
        device_model = device_helper.parse_cpu_info().get('model')

        if device_model is None and machine() == 'x86_64':
            device_model = 'Generic x86_64 Device'

        return device_model

    def get_uptime(self):
        system_uptime = timedelta(seconds=diagnostics.get_uptime())
        return {
            'days': system_uptime.days,
            'hours': round(system_uptime.seconds / 3600, 2),
        }

    def get_memory(self):
        virtual_memory = psutil.virtual_memory()
        return {
            'total': virtual_memory.total >> 20,
            'used': virtual_memory.used >> 20,
            'free': virtual_memory.free >> 20,
            'shared': virtual_memory.shared >> 20,
            'buff': virtual_memory.buffers >> 20,
            'available': virtual_memory.available >> 20
        }

    def get_ip_addresses(self):
        ip_addresses = []
        node_ip = get_node_ip()

        if node_ip == 'Unable to retrieve IP.':
            return []

        for ip_address in node_ip.split():
            ip_address_object = ipaddress.ip_address(ip_address)

            if isinstance(ip_address_object, ipaddress.IPv6Address):
                ip_addresses.append(f'http://[{ip_address}]')
            else:
                ip_addresses.append(f'http://{ip_address}')

        return ip_addresses

    @extend_schema(
        summary='Get system information',
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'viewlog': {'type': 'string'},
                    'loadavg': {'type': 'number'},
                    'free_space': {'type': 'string'},
                    'display_power': {'type': ['string', 'null']},
                    'up_to_date': {'type': 'boolean'},
                    'panelsh_version': {'type': 'string'},
                    'device_model': {'type': 'string'},
                    'uptime': {
                        'type': 'object',
                        'properties': {
                            'days': {'type': 'integer'},
                            'hours': {'type': 'number'}
                        }
                    },
                    'memory': {
                        'type': 'object',
                        'properties': {
                            'total': {'type': 'integer'},
                            'used': {'type': 'integer'},
                            'free': {'type': 'integer'},
                            'shared': {'type': 'integer'},
                            'buff': {'type': 'integer'},
                            'available': {'type': 'integer'}
                        }
                    },
                    'ip_addresses': {
                        'type': 'array', 'items': {'type': 'string'}
                    },
                    'mac_address': {'type': 'string'},
                    'host_user': {'type': 'string'}
                }
            }
        }
    )
    @authorized
    def get(self, request):
        viewlog = "Not yet implemented"

        # Calculate disk space
        slash = statvfs("/")
        free_space = size(slash.f_bavail * slash.f_frsize)
        display_power = r.get('display_power')

        return Response({
            'viewlog': viewlog,
            'loadavg': diagnostics.get_load_avg()['15 min'],
            'free_space': free_space,
            'display_power': display_power,
            'up_to_date': is_up_to_date(),
            'panelsh_version': self.get_panelsh_version(),
            'device_model': self.get_device_model(),
            'uptime': self.get_uptime(),
            'memory': self.get_memory(),
            'ip_addresses': self.get_ip_addresses(),
            'mac_address': get_node_mac_address(),
            'host_user': getenv('HOST_USER'),
        })


class IntegrationsViewV2(APIView):
    serializer_class = IntegrationsSerializerV2

    @extend_schema(
        summary='Get integrations information',
        responses={
            200: IntegrationsSerializerV2
        }
    )
    @authorized
    def get(self, request):
        data = {
            'is_balena': is_balena_app(),
        }

        if data['is_balena']:
            data.update({
                'balena_device_id': getenv('BALENA_DEVICE_UUID'),
                'balena_app_id': getenv('BALENA_APP_ID'),
                'balena_app_name': getenv('BALENA_APP_NAME'),
                'balena_supervisor_version': (
                    getenv('BALENA_SUPERVISOR_VERSION')
                ),
                'balena_host_os_version': (
                    getenv('BALENA_HOST_OS_VERSION')
                ),
                'balena_device_name_at_init': (
                    getenv('BALENA_DEVICE_NAME_AT_INIT')
                ),
            })

        serializer = self.serializer_class(data=data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data)


class HealthViewV2(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        summary='Service health check',
        responses={
            200: {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string', 'enum': ['ok', 'degraded']},
                    'services': {
                        'type': 'object',
                        'properties': {
                            'redis': {'type': 'object'},
                            'zmq': {'type': 'object'},
                        },
                    },
                },
                'example': {
                    'status': 'ok',
                    'services': {
                        'redis': {'status': 'ok'},
                        'zmq': {'status': 'ok'},
                    },
                },
            }
        }
    )
    def get(self, request):
        redis_status = check_redis_health()
        zmq_status = check_zmq_health()

        degraded = any(
            service.get('status') != 'ok'
            for service in (redis_status, zmq_status)
        )

        return Response({
            'status': 'degraded' if degraded else 'ok',
            'services': {
                'redis': redis_status,
                'zmq': zmq_status,
            },
        })
