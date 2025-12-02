# Piano Dettagliato - Deployment in Produzione

**Obiettivo**: Deployare l'app Slack per tutti i colleghi (3 utenti totali)

**Timeline stimata**: 2-3 giorni di lavoro

---

## FASE 1: Preparazione Codice per Produzione

### 1.1 Configurazione Environment Variables
**Tempo**: 1-2 ore

- [ ] Creare file `.env.example` con tutte le variabili richieste (senza valori sensibili)
- [ ] Verificare che tutte le API keys siano caricate da environment variables, non hardcoded
- [ ] Variabili necessarie:
  - `DATABASE_URL` - Connection string Supabase PostgreSQL
  - `SLACK_BOT_TOKEN` - Token bot Slack
  - `SLACK_SIGNING_SECRET` - Secret per verificare richieste Slack
  - `ANTHROPIC_API_KEY` - API key Claude
  - `FATHOM_API_KEY` - Chiave Fathom (se usata come default)
  - `GOOGLE_CLIENT_ID` - OAuth2 Gmail
  - `GOOGLE_CLIENT_SECRET` - OAuth2 Gmail
  - `CRONO_PUBLIC_KEY` - Per ogni tenant
  - `CRONO_PRIVATE_KEY` - Per ogni tenant
  - `FLASK_ENV=production`
  - `PORT=3000` (o quello che usa Render)

**File da modificare**:
- `src/database.py` - Verificare usa DATABASE_URL
- `src/slack_webhook_handler.py` - Verificare tutte le env vars
- Tutti i moduli che usano API keys

---

### 1.2 Setup Gunicorn (WSGI Server)
**Tempo**: 30 min

- [ ] Aggiungere `gunicorn` al `requirements.txt`
- [ ] Creare file `gunicorn_config.py`:
  ```python
  bind = "0.0.0.0:3000"
  workers = 2
  worker_class = "sync"
  timeout = 120
  accesslog = "-"
  errorlog = "-"
  loglevel = "info"
  ```
- [ ] Testare localmente: `gunicorn -c gunicorn_config.py src.slack_webhook_handler:app`

---

### 1.3 Logging Strutturato
**Tempo**: 1 ora

- [ ] Sostituire tutti i `print()` e `sys.stderr.write()` con `logging`
- [ ] Configurare logging in `src/slack_webhook_handler.py`:
  ```python
  import logging
  logging.basicConfig(
      level=logging.INFO,
      format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  )
  logger = logging.getLogger(__name__)
  ```
- [ ] Aggiungere log strutturati per:
  - Richieste webhook in arrivo
  - Errori nelle chiamate API
  - Operazioni database
  - Operazioni AI (Claude)

---

### 1.4 Health Check Endpoint
**Tempo**: 15 min

- [ ] Aggiungere endpoint `/health` in `slack_webhook_handler.py`:
  ```python
  @app.route('/health', methods=['GET'])
  def health_check():
      return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200
  ```
- [ ] Opzionale: verificare connessione database nel health check

---

### 1.5 Gestione Errori Globale
**Tempo**: 30 min

- [ ] Aggiungere error handler globale Flask:
  ```python
  @app.errorhandler(Exception)
  def handle_error(error):
      logger.error(f"Unhandled error: {error}", exc_info=True)
      return jsonify({"error": "Internal server error"}), 500
  ```

---

## FASE 2: Database - Migrazioni su Supabase

### 2.1 Applicare Migrazioni Alembic
**Tempo**: 30 min

- [ ] Verificare che tutte le migrazioni siano create:
  ```bash
  alembic history
  ```
- [ ] Eseguire migrazioni su Supabase:
  ```bash
  DATABASE_URL="postgresql://..." alembic upgrade head
  ```
- [ ] Verificare tabelle create:
  - `tenants`
  - `users`
  - `user_settings`
  - Eventuali altre tabelle

---

### 2.2 Setup Dati Iniziali Produzione
**Tempo**: 30 min

- [ ] Creare tenant per il tuo team in Supabase
- [ ] Inserire utenti iniziali (te + 2 colleghi)
- [ ] Configurare Fathom API keys per ogni utente
- [ ] Script SQL o Python per seeding iniziale

---

## FASE 3: Gmail OAuth Multi-Utente

### 3.1 Configurazione Google Cloud Console
**Tempo**: 1 ora

- [ ] Andare su [Google Cloud Console](https://console.cloud.google.com)
- [ ] Creare/configurare progetto OAuth
- [ ] Aggiungere Authorized redirect URIs:
  - `https://tua-app.onrender.com/oauth/gmail/callback`
- [ ] Scaricare nuove credentials (client_id e client_secret)
- [ ] Configurare OAuth consent screen per uso interno o pubblico

---

### 3.2 Implementare OAuth Flow
**Tempo**: 3-4 ore

- [ ] Creare nuovo modulo `src/modules/gmail_oauth.py`:
  - Endpoint `/oauth/gmail/start` - Inizia OAuth flow
  - Endpoint `/oauth/gmail/callback` - Riceve token da Google
  - Funzione per salvare token nel database (per user_id)
  - Funzione per refresh token automatico

- [ ] Aggiungere campi a tabella `users` o `user_settings`:
  ```sql
  ALTER TABLE user_settings ADD COLUMN gmail_access_token TEXT;
  ALTER TABLE user_settings ADD COLUMN gmail_refresh_token TEXT;
  ALTER TABLE user_settings ADD COLUMN gmail_token_expiry TIMESTAMP;
  ```

- [ ] Creare migration Alembic per questi campi

- [ ] Modificare `src/modules/gmail_draft_creator.py`:
  - Invece di leggere `token.json`
  - Recuperare token dal database per user_id specifico
  - Gestire refresh automatico se scaduto

- [ ] Aggiungere comando Slack `/gmail-connect`:
  - Invia link OAuth personalizzato all'utente
  - Salva state con user_id per callback

---

## FASE 4: Deployment su Render

### 4.1 Preparare File di Configurazione
**Tempo**: 30 min

- [ ] Verificare `requirements.txt` aggiornato:
  ```bash
  pip freeze > requirements.txt
  ```

- [ ] Creare `render.yaml`:
  ```yaml
  services:
    - type: web
      name: slack-fathom-crono
      env: python
      buildCommand: "pip install -r requirements.txt"
      startCommand: "gunicorn -c gunicorn_config.py src.slack_webhook_handler:app"
      envVars:
        - key: PYTHON_VERSION
          value: 3.11
        - key: DATABASE_URL
          sync: false
        - key: SLACK_BOT_TOKEN
          sync: false
        - key: SLACK_SIGNING_SECRET
          sync: false
        # ... altre env vars
  ```

- [ ] Creare `.gitignore` completo:
  ```
  __pycache__/
  *.pyc
  .env
  .venv/
  venv/
  token.json
  credentials.json
  *.db
  .DS_Store
  ```

---

### 4.2 Creare Account e Deploy su Render
**Tempo**: 1 ora

- [ ] Creare account su [Render.com](https://render.com)
- [ ] Collegare repository GitHub
- [ ] Creare nuovo "Web Service"
- [ ] Configurare:
  - **Name**: slack-fathom-crono
  - **Region**: Scegliere più vicino (EU se in Europa)
  - **Branch**: main
  - **Build Command**: `pip install -r requirements.txt`
  - **Start Command**: `gunicorn -c gunicorn_config.py src.slack_webhook_handler:app`
  - **Plan**: Starter ($7/mese) - Always-on

---

### 4.3 Configurare Environment Variables su Render
**Tempo**: 30 min

- [ ] Nel dashboard Render, andare su Environment
- [ ] Aggiungere tutte le variabili d'ambiente:
  - DATABASE_URL (da Supabase)
  - SLACK_BOT_TOKEN
  - SLACK_SIGNING_SECRET
  - ANTHROPIC_API_KEY
  - GOOGLE_CLIENT_ID
  - GOOGLE_CLIENT_SECRET
  - Tutte le altre necessarie

- [ ] Salvare e fare re-deploy

---

### 4.4 Verificare Deploy
**Tempo**: 30 min

- [ ] Controllare logs su Render
- [ ] Verificare app è up: `https://tua-app.onrender.com/health`
- [ ] Copiare URL pubblico generato da Render

---

## FASE 5: Configurazione Slack App

### 5.1 Aggiornare Webhook URLs
**Tempo**: 30 min

- [ ] Andare su [api.slack.com/apps](https://api.slack.com/apps)
- [ ] Selezionare la tua app
- [ ] **Event Subscriptions**:
  - Request URL: `https://tua-app.onrender.com/slack/events`
  - Verificare che Slack validi l'URL (status 200)

- [ ] **Interactivity & Shortcuts**:
  - Request URL: `https://tua-app.onrender.com/slack/interactions`

- [ ] **Slash Commands**:
  - `/followup`: `https://tua-app.onrender.com/slack/commands`
  - `/crono-add-task`: `https://tua-app.onrender.com/slack/commands`
  - Tutti gli altri comandi

- [ ] Salvare modifiche

---

### 5.2 OAuth & Permissions (se distribuire ad altri team)
**Tempo**: 30 min

- [ ] **OAuth & Permissions**:
  - Redirect URLs: `https://tua-app.onrender.com/slack/oauth/callback`

- [ ] **Bot Token Scopes** - Verificare hai tutti gli scope necessari:
  - `chat:write`
  - `commands`
  - `users:read`
  - `channels:history`
  - `im:write`
  - `im:history`
  - Altri necessari

---

## FASE 6: Testing in Produzione

### 6.1 Test Funzionalità Base
**Tempo**: 1-2 ore

- [ ] Testare `/followup`:
  - Aprire modal
  - Selezionare meeting
  - Vedere messaggio "Processing..."
  - Attendere generazione AI
  - Cliccare "View & Edit"
  - Verificare modal si apre correttamente

- [ ] Testare `/crono-add-task`:
  - Autocomplete prospects
  - Autocomplete accounts
  - Creazione task

- [ ] Testare azioni da modal:
  - Creare Gmail Draft
  - Creare Calendar Event
  - Push note a Crono
  - View Deals
  - Create Task

- [ ] Verificare logs su Render per eventuali errori

---

### 6.2 Test Multi-Utente
**Tempo**: 1 ora

- [ ] Invitare i 2 colleghi nello Slack workspace
- [ ] Far provare a loro `/followup`
- [ ] Verificare tenant isolation (ogni utente vede solo i suoi dati)
- [ ] Far eseguire `/gmail-connect` per autenticare Gmail
- [ ] Testare creazione Gmail draft con account loro

---

## FASE 7: Monitoring & Manutenzione

### 7.1 Setup Monitoring
**Tempo**: 1 ora

- [ ] Configurare alerts su Render per:
  - App down
  - High error rate
  - High memory usage

- [ ] Opzionale: Integrare Sentry per error tracking:
  ```bash
  pip install sentry-sdk[flask]
  ```

- [ ] Configurare retention logs su Render

---

### 7.2 Documentazione per Utenti
**Tempo**: 1-2 ore

- [ ] Creare documento/video guida per colleghi:
  - Come usare `/followup`
  - Come connettere Gmail (`/gmail-connect`)
  - Come usare `/crono-add-task`
  - Troubleshooting comuni

- [ ] Condividere su Slack channel

---

## FASE 8: Ottimizzazioni Post-Launch (Opzionale)

### 8.1 Performance
- [ ] Implementare Redis cache per autocomplete Crono
- [ ] Ottimizzare query database con indici
- [ ] Considerare worker queue (Celery) per AI tasks lunghi

### 8.2 Sicurezza
- [ ] Rate limiting su endpoints pubblici
- [ ] Audit log per azioni sensibili
- [ ] Backup automatici database (Supabase li fa già)

### 8.3 Features Future
- [ ] Notifiche automatiche per meeting importanti
- [ ] Dashboard analytics
- [ ] Integrazione con altri CRM oltre Crono

---

## Checklist Pre-Launch Finale

**Giorno del Deploy**:

- [ ] Database migrations applicate su Supabase
- [ ] Tutte le env vars configurate su Render
- [ ] App deployata e health check verde
- [ ] Webhook URLs aggiornati su Slack
- [ ] Test completo di tutte le funzionalità
- [ ] Colleghi hanno fatto onboarding Gmail OAuth
- [ ] Logs monitorati per 24h senza errori critici

---

## Risorse e Link Utili

- **Render Dashboard**: https://dashboard.render.com
- **Slack App Dashboard**: https://api.slack.com/apps
- **Supabase Dashboard**: https://app.supabase.com
- **Google Cloud Console**: https://console.cloud.google.com

---

## Note Importanti

1. **Costi Stimati Mensili**:
   - Render Starter: $7/mese
   - Supabase Free tier: $0 (sotto 500MB)
   - Anthropic API: Pay-per-use (dipende da utilizzo)
   - Totale: ~$7-15/mese

2. **Backup & Recovery**:
   - Supabase fa backup automatici
   - Tenere git repo aggiornato
   - Documentare env vars in password manager

3. **Scaling Future**:
   - Per più utenti (>10), considerare:
     - Upgrade Render plan
     - Worker queue per AI
     - Database connection pooling

---

**Ultima revisione**: 2025-12-03
**Status**: Da iniziare
