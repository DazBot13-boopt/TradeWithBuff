# Déploiement sur Digital Ocean

## Prérequis
- Un Droplet Ubuntu 22.04+ (minimum 1GB RAM)
- Python 3.10+
- Git

## 1. Cloner le repo sur le Droplet

```bash
git clone https://github.com/TON_REPO/polymarket-copy-trader.git
cd polymarket-copy-trader
```

## 2. Créer l'environnement virtuel et installer les dépendances

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Configurer les variables d'environnement

```bash
cp .env.example .env
nano .env
```

Remplir :
```
POLYMARKET_PRIVATE_KEY=0x...ta_clé_privée...
POLYMARKET_PROXY_ADDRESS=0x...ton_proxy...
```

## 4. Créer le fichier config.json

```bash
cp config.json.example config.json
nano config.json
```

Remplir l'adresse wallet à tracker.

## 5. Lancer avec Gunicorn (test)

```bash
source venv/bin/activate
gunicorn app:app --workers 2 --threads 2 --bind 0.0.0.0:5051 --timeout 120
```

## 6. Configurer systemd pour démarrage automatique

Créer `/etc/systemd/system/copytrader.service` :

```ini
[Unit]
Description=Polymarket Copy Trader
After=network.target

[Service]
User=www-data
WorkingDirectory=/home/ubuntu/polymarket-copy-trader
Environment="PATH=/home/ubuntu/polymarket-copy-trader/venv/bin"
EnvironmentFile=/home/ubuntu/polymarket-copy-trader/.env
ExecStart=/home/ubuntu/polymarket-copy-trader/venv/bin/gunicorn app:app --workers 2 --threads 2 --bind 0.0.0.0:5051 --timeout 120
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activer le service :
```bash
sudo systemctl daemon-reload
sudo systemctl enable copytrader
sudo systemctl start copytrader
sudo systemctl status copytrader
```

## 7. (Optionnel) Nginx en reverse proxy

```bash
sudo apt install nginx
```

Config `/etc/nginx/sites-available/copytrader` :
```nginx
server {
    listen 80;
    server_name TON_IP_OU_DOMAINE;

    location / {
        proxy_pass http://127.0.0.1:5051;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/copytrader /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## ⚠️ Sécurité

- Ne jamais committer `.env` ou `config.json` avec de vraies clés
- Ouvrir uniquement les ports 80/443 dans le firewall Digital Ocean
- Activer `ufw` : `sudo ufw allow 'Nginx Full' && sudo ufw enable`
