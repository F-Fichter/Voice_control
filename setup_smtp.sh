#!/bin/bash
# Installation Postfix SMTP pour fichter.eu
# Usage: sudo ./setup_smtp.sh

set -e

echo "=== SMTP Postfix pour fichter.eu ==="

# Variables
DOMAIN="fichter.eu"
HOSTNAME="mail.${DOMAIN}"
ADMIN_EMAIL="admin@${DOMAIN}"

# 1. Installation
echo "[1/6] Installation Postfix + Dovecot..."
apt update
apt install -y postfix postfix-pcre dovecot-core dovecot-imapd dovecot-lmtpd \
    opendkim opendkim-tools fail2ban

# Configuration Postfix
echo "[2/6] Configuration Postfix..."

cat > /etc/postfix/main.cf << 'EOF'
# Hostname
myhostname = mail.fichter.eu
mydomain = fichter.eu
myorigin = $mydomain
mydestination = localhost.$mydomain, localhost, $mydomain
mynetworks = 127.0.0.0/8 [::ffff:127.0.0.0]/104 [::1]/128
inet_interfaces = all
inet_protocols = all

# Relay
relay_domains = $mydestination
transport_maps = hash:/etc/postfix/transport

# SMTP Auth
smtpd_sasl_type = dovecot
smtpd_sasl_path = private/auth
smtpd_sasl_auth_enable = yes
smtpd_sasl_authenticated_header = yes
smtpd_sasl_security_options = noanonymous
broken_sasl_auth_clients = yes

# Restrictions
smtpd_helo_required = yes
smtpd_recipient_restrictions =
    permit_mynetworks,
    permit_sasl_authenticated,
    reject_rbl_client zen.spamhaus.org,
    reject_rhsbl_helo dbl.spamhaus.org,
    reject_rhsbl_reverse_client dbl.spamhaus.org,
    reject_unknown_reverse_client_hostname,
    reject_unauth_destination

# TLS
smtpd_tls_cert_file = /etc/ssl/certs/mail.crt
smtpd_tls_key_file = /etc/ssl/private/mail.key
smtpd_tls_security_level = may
smtp_tls_security_level = may
smtpd_tls_protocols = !SSLv2,!SSLv3,!TLSv1,!TLSv1.1
tls_preempt_cipherlist = yes

# Logging
maillog_file = /var/log/mail.log
maillog_macros = main

# Queue
message_size_limit = 52428800
mailbox_size_limit = 1073741824
EOF

# 2. Dovecot
echo "[3/6] Configuration Dovecot..."

cat > /etc/dovecot/dovecot.conf << 'EOF'
protocols = imap lmtp
listen = *, ::
!include_try /etc/dovecot/local.conf
EOF

cat > /etc/dovecot/conf.d/10-mail.conf << 'EOF'
mail_location = maildir:~/Maildir
namespace inbox {
    inbox = yes
}
EOF

cat > /etc/dovecot/conf.d/10-master.conf << 'EOF'
service imap-login {
    inet_listener imap {
        port = 143
    }
    inet_listener imaps {
        port = 993
        ssl = yes
    }
}

service submission-login {
    inet_listener submission {
        port = 587
    }
}

service lmtp {
    unix_listener /var/spool/postfix/private/lmtp {
        mode = 0600
        user = postfix
        group = postfix
    }
}

service auth {
    unix_listener /var/spool/postfix/private/auth {
        mode = 0600
        user = postfix
        group = postfix
    }
}
EOF

cat > /etc/dovecot/conf.d/10-ssl.conf << 'EOF'
ssl = required
ssl_cert = </etc/ssl/certs/mail.crt
ssl_key = </etc/ssl/private/mail.key
ssl_protocols = !SSLv2 !SSLv3 !TLSv1 !TLSv1.1
EOF

cat > /etc/dovecot/conf.d/10-auth.conf << 'EOF'
auth_mechanisms = plain login
!include auth-system.conf.ext
EOF

# 3. Certificats (placeholder)
echo "[4/6] Certificats SSL..."

mkdir -p /etc/ssl/private
if [ ! -f /etc/ssl/certs/mail.crt ]; then
    # Auto-signé pour test (remplacer par Let's Encrypt après)
    openssl req -new -newkey rsa:4096 -x509 -sha256 -days 365 -nodes \
        -out /etc/ssl/certs/mail.crt \
        -keyout /etc/ssl/private/mail.key \
        -subj "/C=FR/ST=France/L=Paris/O=Fichter/OU=IT/CN=mail.fichter.eu"
    echo "⚠️  Certificat auto-signé créé. Remplacez par Let's Encrypt:"
    echo "   certbot certonly --standalone -d mail.fichter.eu"
fi

chmod 600 /etc/ssl/private/mail.key

# 4. DKIM
echo "[5/6] Configuration DKIM..."

# Créer clé DKIM
mkdir -p /etc/opendkim/keys
opendkim-genkey -b 2048 -D /etc/opendkim/keys/ -d fichter.eu -s mail
mv /etc/opendkim/keys/mail.private /etc/opendkim/keys/fichter.eu

chown -R opendkim:opendkim /etc/opendkim/keys
chmod 600 /etc/opendkim/keys/fichter.eu

# Config DKIM
cat > /etc/opendkim.conf << 'EOF'
Canonicalization relaxed/simple
ExternalIgnoreList refile:/etc/opendkim/TrustedHosts
InternalHosts refile:/etc/opendkim/TrustedHosts
KeyTable refile:/etc/opendkim/KeyTable
LogWhy yes
OversignHeaders From
Socket inet:8891@localhost
SignatureAlgorithm RSA-SHA256
SigningTable refile:/etc/opendkim/SigningTable
Syslog yes
SyslogSuccess yes
EOF

cat > /etc/opendkim/KeyTable << 'EOF'
mail._domainkey.fichter.eu fichter.eu:mail:/etc/opendkim/keys/fichter.eu
EOF

cat > /etc/opendkim/SigningTable << 'EOF'
*@fichter.eu mail._domainkey.fichter.eu
EOF

cat > /etc/opendkim/TrustedHosts << 'EOF'
127.0.0.1
localhost
*.fichter.eu
EOF

# Intégrer DKIM dans Postfix
echo "milter_default_action = accept" >> /etc/postfix/main.cf
echo "non_smtpd_milter = inet:localhost:8891" >> /etc/postfix/main.cf

# 5. DNS Records (à configurer)
echo "[6/6] DNS Records à ajouter..."

cat > /tmp/dns_records.txt << 'EOF'
# Ajouter ces enregistrements DNS chez votre registrar:

@  TXT  "v=spf1 mx a:mail.fichter.eu ~all"
mail._domainkey  TXT  "v=DKIM1; k=rsa; p=[voir /etc/opendkim/keys/mail.txt]"
@  MX  10 mail.fichter.eu
mail  A  [VOTRE_IP_PUBLIQUE]
EOF

cat /tmp/dns_records.txt

# Démarrage
echo ""
echo "=== Démarrage des services ==="
systemctl enable postfix dovecot opendkim fail2ban
systemctl restart postfix dovecot opendkim fail2ban

echo ""
echo "=== Vérification ==="
netstat -tlnp | grep -E '(25|465|587|993|143)'
echo ""

echo "=== Commandes utiles ==="
echo "tail -f /var/log/mail.log       # Logs emails"
echo "postqueue -p                     # File d'attente"
echo "postqueue -f                     # Forcer envoi"
echo ""
echo "=== IMPORTANT ==="
echo "1. Ajoutez les enregistrements DNS ci-dessus"
echo "2. Ouvrez les ports 25, 587, 465, 993, 143 sur votre firewall"
echo "3. Demandez解除 le blocage SMTP à votre FAI si nécessaire"
echo "4. Test: echo 'Test' | mail -s 'Test' admin@fichter.eu"