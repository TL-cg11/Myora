#!/usr/bin/env bash
set -euo pipefail

if ! command -v nginx >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y nginx
fi

sudo mkdir -p /etc/nginx/conf.d
sudo cp nginx.conf /etc/nginx/nginx.conf
sudo cp conf.d/luck.conf /etc/nginx/conf.d/luck.conf

sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl status nginx --no-pager | head
