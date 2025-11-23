# Documentation

## How to get logs from panel.sh

SSH into your Raspberry Pi. For instance, if you've set `pi` for the username
and `raspberrypi` for the hostname, then run:

```bash
$ ssh pi@raspberrypi
```

Anthias makes use of Docker for containerization. To get the logs from the
containers, you can either make use of the `docker logs` command or you can
use the `docker-compose logs` command.

### Using `docker logs`

For instance, the command below will show you the logs from the server container:

```bash
$ docker logs -f panelsh-anthias-server-1
```

If you'd want to see the logs from other containers, simply replace the name
of the container in the command above. Here's a table of the available containers:

<!-- create a two-column table -->
| Container Name | Description |
| -------------- | ----------- |
| `panelsh-anthias-nginx-1` | NGINX service |
| `panelsh-anthias-viewer-1` | Viewer service |
| `panelsh-anthias-celery-1` | Celery service |
| `panelsh-anthias-websocket-1` | WebSocket service |
| `panelsh-anthias-server-1` | web UI (front-end and back-end) |
| `panelsh-anthias-redis-1` | Redis (database, cache, message broker) |
| `panelsh-anthias-wifi-connect-1` | Wi-Fi connectivity |

### Using `docker-compose logs`

> [!IMPORTANT]
> Before running the succeeding commands, make sure that you're in the
> `/home/${USER}/panel.sh` directory:
> 
> ```bash
> $ cd /home/${USER}/panel.sh # e.g., /home/pi/panel.sh if the user is `pi`
> ```

If you'd like to see the logs of a specific container or service via Docker Compose,
you can run the following:

```bash
$ docker compose logs -f ${SERVICE_NAME}
# e.g., docker compose logs -f anthias-server
```

Check out [this section](/docs/developer-documentation.md#understanding-the-components-that-make-up-anthias) of the Developer documentation page for the list of available services.

## Enabling SSH

See [the official documentation](https://www.raspberrypi.org/documentation/remote-access/ssh/)

## Updating Anthias

Run the following command in your console:

```bash
$ bash <(curl -sL https://install-anthias.srly.io)
```

Alternatively, you can also run the following command:

```bash
$ $HOME/panel.sh/bin/run_upgrade.sh
```

## Accessing the REST API

To get started, open your browser and go to `http://<ip-address>/api/docs/` (or `http://localhost:8000/api/docs/`
if you're in development mode). You should see the API docs for the endpoints.

## Installing (trusted) self-signed certificates

> [!WARNING]
> This section only works for devices running Raspberry Pi OS Lite.
> With running the following script, you can install self-signed certificates:
> 
> ```bash
> $ cd $HOME/panel.sh
> $ ./bin/add_certificate.sh /path/to/certificate.crt
> ```

More details about generating self-signed certificates can be found [here](https://devopscube.com/create-self-signed-certificates-openssl/).

## Wi-Fi Setup

- Read the [Wi-Fi Setup](wifi-setup.md) page for more details on how to set up Wi-Fi on the Raspberry Pi.
