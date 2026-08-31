#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

sudo apt-get update
sudo apt-get install -y nginx curl

sudo mkdir -p /etc/nginx/conf.d
sudo install -m 0644 nginx.conf /etc/nginx/nginx.conf
sudo install -m 0644 conf.d/luck.conf /etc/nginx/conf.d/luck.conf

sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

curl --fail --silent --show-error http://127.0.0.1/nginx-health
