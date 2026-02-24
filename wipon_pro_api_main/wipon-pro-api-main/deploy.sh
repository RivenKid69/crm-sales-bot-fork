#!/bin/sh

git pull
docker build --target production -t wipon-pro-api .
docker-compose down --remove-orphans
docker-compose up -d
docker system prune --volumes --force
