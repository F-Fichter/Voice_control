# SMTP Server Setup - fichter.eu

## Architecture

```
                    ┌─────────────────┐
                    │   Internet      │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
          Port 25         Port 587       Port 993
         (SMTP)         (Submission)    (IMAPS)
              │              │              │
              └──────────────┴──────────────┘
                             │
                    ┌────────▼────────┐
                    │    Postfix     │
                    │   (SMTP/MTA)   │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
          SPF/DKIM      Transport       FILTRAGE
           Vérif          LMTP           SpamAssassin
              │              │              │
              └──────────────┴──────────────┘
                             │
                    ┌────────▼────────┐
                    │    Dovecot     │
                    │  (IMAP/LMTP)   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Maildir Format │
                    │ /var/vmail/    │
                    └────────────────┘
```

## Installation Rapide

```bash
# 1. Lancez le script d'installation
sudo ./setup_smtp.sh

# 2. Créez un utilisateur boîte email
sudo useradd -m -s /sbin/nologin vmail
sudo mkdir -p /var/vmail
sudo chown vmail:vmail /var/vmail

# 3. Ajoutez DNS records (voir ci-dessous)

# 4. Test
echo "Test email" | mail -s "Test SMTP" admin@fichter.eu
tail -f /var/log/mail.log
```

## DNS Records à Configurer

### Zone DNS (chez votre registrar)

| Type | Nom | Valeur |
|------|-----|--------|
| A | mail | `VOTRE_IP_PUBLIQUE` |
| MX | @ | `mail.fichter.eu` (priorité 10) |
| TXT | @ | `v=spf1 mx a:mail.fichter.eu ~all` |
| TXT | mail._domainkey | `v=DKIM1; k=rsa; p=[clé_publique]` |

### Récupérer la clé DKIM
```bash
cat /etc/opendkim/keys/mail.txt
```

## Ports à Ouvrir

```bash
# UFW
sudo ufw allow 25/tcp    # SMTP
sudo ufw allow 465/tcp   # SMTPS
sudo ufw allow 587/tcp   # Submission
sudo ufw allow 993/tcp   # IMAPS
sudo ufw allow 143/tcp   # IMAP
```

## Créer une Boîte Email

```bash
# Méthode 1: Utilisateur système
sudo useradd -m -s /bin/false admin
sudo passwd admin

# Méthode 2: Boîtes virtuelles (Postfix + MySQL)
# Voir section virtuelle ci-dessous
```

## Clients Email

### Thunderbird / Outlook
```
Serveur IMAP:  mail.fichter.eu
Port:          993 (SSL)
Utilisateur:   admin@fichter.eu
Mot de passe:  ****

SMTP:
Serveur:       mail.fichter.eu  
Port:          587 (STARTTLS)
Utilisateur:   admin@fichter.eu
```

### Test CLI
```bash
# IMAP
nc -C mail.fichter.eu 993

# SMTP
telnet mail.fichter.eu 25
EHLO test
MAIL FROM:<test@fichter.eu>
RCPT TO:<admin@fichter.eu>
DATA
Test email
.
QUIT
```

## Commandes Utiles

```bash
# Logs
tail -f /var/log/mail.log
tail -f /var/log/mail.warn
grep -i error /var/log/mail.log

# File d'attente
postqueue -p
postqueue -f           # Forcer envoi
postsuper -d ALL       # Vider la queue

# Tester config
postfix check
doveadm config

# Relancer
systemctl restart postfix
systemctl restart dovecot
```

## Dépannage

### Problème: "Connection refused"
```bash
# Vérifier que Postfix écoute
netstat -tlnp | grep :25

# Si non, vérifier main.cf
postconf -n | grep inet_interfaces
```

### Problème: "Authentication failed"
```bash
# Vérifier SASL
testsaslauthd -u admin@fichter.eu -p 'password'
```

### Problème: Emails en queue
```bash
# Vérifier les restrictions
postconf -d | grep restrictions
mailq
```

## SSL Let's Encrypt (Recommandé)

```bash
# Après configuration DNS
sudo apt install certbot
sudo certbot certonly --standalone -d mail.fichter.eu

# Liens symboliques
sudo ln -s /etc/letsencrypt/live/mail.fichter.eu/fullchain.pem \
          /etc/ssl/certs/mail.crt
sudo ln -s /etc/letsencrypt/live/mail.fichter.eu/privkey.pem \
          /etc/ssl/private/mail.key

sudo systemctl restart postfix dovecot
```

## Virtual Hosting (Multi-domaines)

Pour gérer plusieurs domaines, utilisez MySQL:

```sql
CREATE DATABASE mailserver;
USE mailserver;

CREATE TABLE virtual_domains (
    id INT PRIMARY KEY,
    name VARCHAR(50)
);

CREATE TABLE virtual_users (
    id INT PRIMARY KEY,
    domain_id INT,
    email VARCHAR(100),
    password VARCHAR(255),
    FOREIGN KEY (domain_id) REFERENCES virtual_domains(id)
);
```

 Voir: https://www.postfix.org/VIRTUAL_README.html