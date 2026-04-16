# Deploy HyperKitchen on Alibaba Cloud ECS

This repository is ready for a single-server deployment on Ubuntu 22.04.

## 1. Server packages

```bash
apt update
apt install -y git python3 python3-venv python3-pip nginx ffmpeg curl
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
```

## 2. Clone the repository

```bash
mkdir -p /srv/hyperkitchen
cd /srv/hyperkitchen
git clone https://github.com/zhengyongqimic/cookbox_rq.git current
python3 -m venv /srv/hyperkitchen/venv
/srv/hyperkitchen/venv/bin/pip install --upgrade pip
/srv/hyperkitchen/venv/bin/pip install -r /srv/hyperkitchen/current/backend/requirements.txt
```

## 3. Build the frontend

```bash
cd /srv/hyperkitchen/current/frontend
npm ci
npm run build
```

## 4. Shared directories

```bash
mkdir -p /srv/hyperkitchen/shared/instance
mkdir -p /srv/hyperkitchen/shared/uploads
mkdir -p /srv/hyperkitchen/shared/thumbnails
mkdir -p /srv/hyperkitchen/shared/slices
```

## 5. Environment file

Create `/etc/hyperkitchen.env`:

```bash
cat >/etc/hyperkitchen.env <<'EOF'
HYPERKITCHEN_SECRET_KEY=replace-with-a-long-random-secret
HYPERKITCHEN_JWT_SECRET_KEY=replace-with-a-long-random-jwt-secret
ARK_API_KEY=
HYPERKITCHEN_DB_PATH=/srv/hyperkitchen/shared/hyperkitchen.db
HYPERKITCHEN_INSTANCE_DIR=/srv/hyperkitchen/shared/instance
HYPERKITCHEN_UPLOAD_DIR=/srv/hyperkitchen/shared/uploads
HYPERKITCHEN_THUMBNAIL_DIR=/srv/hyperkitchen/shared/thumbnails
HYPERKITCHEN_SLICES_DIR=/srv/hyperkitchen/shared/slices
HYPERKITCHEN_FRONTEND_DIST=/srv/hyperkitchen/current/frontend/dist
HYPERKITCHEN_ALLOWED_ORIGINS=https://cookbox.site,https://www.cookbox.site
HYPERKITCHEN_MAX_UPLOAD_MB=500
HYPERKITCHEN_PORT=5000
HYPERKITCHEN_DEBUG=false
EOF
chmod 600 /etc/hyperkitchen.env
```

## 6. systemd service

```bash
cp /srv/hyperkitchen/current/deploy/systemd/hyperkitchen.service /etc/systemd/system/hyperkitchen.service
systemctl daemon-reload
systemctl enable --now hyperkitchen
systemctl status hyperkitchen --no-pager
```

## 7. Nginx

```bash
cp /srv/hyperkitchen/current/deploy/nginx/cookbox.site.conf /etc/nginx/sites-available/cookbox.site.conf
ln -sf /etc/nginx/sites-available/cookbox.site.conf /etc/nginx/sites-enabled/cookbox.site.conf
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

## 8. DNS

Create these DNS records after domain verification completes:

- `A @ -> 47.239.92.209`
- `A www -> 47.239.92.209`

## 9. HTTPS

After DNS resolves:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d cookbox.site -d www.cookbox.site
```

## 10. Verify

```bash
curl -I http://127.0.0.1:5000
curl -I http://47.239.92.209
curl -I https://www.cookbox.site
journalctl -u hyperkitchen -n 100 --no-pager
```
