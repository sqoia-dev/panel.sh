#!/bin/bash

if [[ -f ./docker-compose.yml ]]; then
    docker compose up -d panelsh-wifi-connect
fi
