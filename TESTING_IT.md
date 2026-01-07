# Quick Test Guide

## Test Locale (Senza Docker)

### 1. Avvia il Server Python

In un terminale:
```bash
cd server
source venv/bin/activate
python main.py
```

Il server partirà sulla porta **8765** (WebSocket).

---

### 2. Avvia il Client HTTPS

In un **altro terminale**:
```bash
# Dalla root del progetto
python3 serve-client.py
```

Questo:
- Genera automaticamente i certificati SSL (se non esistono)
- Avvia un server HTTPS sulla porta **8443**
- Serve i file dalla cartella `client/`

---

### 3. Apri il Browser

1. Vai su: **https://localhost:8443**
2. Accetta l'avviso di sicurezza (certificato self-signed)
3. Click su "Activate Voice Control"
4. Concedi i permessi al microfono
5. Premi **BARRA SPAZIATRICE** per simulare la wake word
6. Il sistema inizierà a registrare audio per 5 secondi

---

## Verifica

**Pannello di Debug** (in basso nella pagina):
- Dovresti vedere i log delle connessioni
- WebSocket status: "Connected" (verde)
- Microphone status: "Active" (blu)

**Status Badges** (in alto):
- WebSocket: Connected ✅
- Wyoming: Unknown (finché non connetti HA)
- Microphone: Active ✅

---

## Problemi Comuni

### Certificato SSL non accettato
Nel browser, clicca su "Advanced" → "Proceed to localhost (unsafe)"

### Microfono non accessibile
- Controlla che sia HTTPS (non HTTP)
- Verifica permessi browser nelle impostazioni

### WebSocket non si connette
- Verifica che il server Python stia girando
- Controlla `server/config.yaml` - porta dovrebbe essere 8765
- Guarda i log del server per errori

---

## Alternative: Server Node.js

Se preferisci Node.js, puoi usare `http-server`:

```bash
npm install -g http-server

# Genera certificati
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Avvia server
http-server client -p 8443 -S -C cert.pem -K key.pem
```

---

## Test Completo con Home Assistant

1. **In Home Assistant > Impostazioni > Dispositivi > Aggiungi Integrazione**
2. Cerca **"Wyoming Protocol"**
3. Inserisci:
   - **Host**: L'indirizzo IP del tuo computer (es. `192.168.1.x`)
   - **Port**: `10700`
4. HA dovrebbe trovare il satellite "hybrid-voice-satellite"

### Nota Importante
Il server Python ora **ascolta** sulla porta 10700. Non prova più a connettersi attivamente ad HA. È HA che si connette al satellite.

Assicurati che:
- Il firewall del tuo computer permetta connessioni in ingresso sulla porta 10700
- Stai usando l'IP della rete locale (non `localhost` se HA è su un altro dispositivo)
