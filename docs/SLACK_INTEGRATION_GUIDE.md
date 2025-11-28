# Slack Integration Guide

Questo tool ora supporta un workflow interattivo con Slack che ti permette di ricevere il meeting summary e decidere quali azioni eseguire (Gmail, Calendar, Crono) tramite chat.

## 🎯 Come funziona

Invece di eseguire automaticamente tutte le azioni (Gmail draft, Calendar, Crono), puoi inviare il meeting summary a Slack dove potrai:

1. **Ricevere un messaggio ricco** con:
   - 📋 Meeting summary
   - 📧 Email proposta dall'AI
   - 💡 Sales insights (tech stack, pain points, next steps)
   - 🎥 Link alla registrazione Fathom

2. **Selezionare le azioni** tramite checkbox:
   - ☑️ Create Gmail Draft
   - ☑️ Add Calendar Event
   - ☑️ Save to Crono CRM

3. **Confermare in chat** - Il bot ti chiederà conferma in stile conversazionale

4. **Ricevere i risultati** - Il bot eseguirà le azioni e ti darà feedback

## 📋 Setup Slack App

### Passo 1: Creare la Slack App

1. Vai su [api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"**
3. Scegli **"From scratch"**
4. Nome dell'app: `Meeting Follow-up Bot`
5. Workspace: Seleziona il tuo workspace aziendale Crono
6. Click **"Create App"**

### Passo 2: Configurare Bot Token Scopes

1. Nella sidebar, vai su **"OAuth & Permissions"**
2. Scroll down a **"Scopes"** → **"Bot Token Scopes"**
3. Aggiungi questi scopes:
   ```
   chat:write          # Per inviare messaggi
   chat:write.public   # Per scrivere in canali pubblici
   channels:read       # Per leggere info dei canali
   users:read          # Per leggere info degli utenti (optional)
   ```

### Passo 3: Installare l'App nel Workspace

1. Scroll up a **"OAuth Tokens for Your Workspace"**
2. Click **"Install to Workspace"**
3. Autorizza l'app
4. Copia il **Bot User OAuth Token** (inizia con `xoxb-`)
   - Salvalo in `.env` come `SLACK_BOT_TOKEN=xoxb-...`

### Passo 4: Abilitare Interactive Components

1. Nella sidebar, vai su **"Interactivity & Shortcuts"**
2. Attiva **"Interactivity"**
3. **Request URL** → Inserisci il tuo webhook URL (vedi Passo 5)
   - Esempio: `https://your-ngrok-url.ngrok.io/slack/interactions`

### Passo 5: Setup Webhook Server (ngrok)

Per ricevere le interazioni da Slack, devi esporre il server locale con ngrok:

1. Installa ngrok:
   ```bash
   # macOS
   brew install ngrok

   # O scarica da https://ngrok.com/download
   ```

2. Avvia il webhook handler:
   ```bash
   python slack_webhook_handler.py
   ```

3. In un altro terminale, avvia ngrok:
   ```bash
   ngrok http 3000
   ```

4. Copia l'URL HTTPS generato (es: `https://abc123.ngrok.io`)

5. Vai su Slack App → **"Interactivity & Shortcuts"**:
   - Request URL: `https://abc123.ngrok.io/slack/interactions`
   - Click **"Save Changes"**

6. Vai su **"Event Subscriptions"**:
   - Attiva **"Enable Events"**
   - Request URL: `https://abc123.ngrok.io/slack/events`
   - Subscribe to bot events:
     - `message.channels`
     - `message.groups`
     - `message.im`
   - Click **"Save Changes"**

### Passo 6: Ottenere il Signing Secret

1. Vai su **"Basic Information"** nella sidebar
2. Scroll a **"App Credentials"**
3. Copia il **Signing Secret**
4. Salvalo in `.env` come `SLACK_SIGNING_SECRET=...`

### Passo 7: Configurare il canale Slack

1. Scegli o crea un canale (es: `#sales`)
2. Invita il bot nel canale:
   ```
   /invite @Meeting Follow-up Bot
   ```
3. Aggiungi il nome del canale in `.env`:
   ```
   SLACK_CHANNEL=#sales
   ```

## ⚙️ Configurazione `.env`

Il tuo file `.env` dovrebbe includere:

```bash
# Existing API keys
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
FATHOM_API_KEY=...
CRONO_API_KEY=...
CRONO_API_URL=...

# NEW: Slack Integration
SLACK_BOT_TOKEN=xoxb-1234567890123-1234567890123-abcdefghijklmnopqrstuvwx
SLACK_SIGNING_SECRET=abcdef1234567890abcdef1234567890
SLACK_CHANNEL=#sales
```

## 🚀 Usage

### 1. Avvia il webhook handler

Prima di usare il workflow Slack, devi avviare il webhook handler:

```bash
python slack_webhook_handler.py
```

Lascia questo terminale aperto.

### 2. (Opzionale) Avvia ngrok se necessario

Se il tuo ngrok è scaduto, riavvialo:

```bash
ngrok http 3000
```

### 3. Esegui il tool con flag `--slack`

```bash
# Basic usage
python meeting_followup.py --slack

# Specifica un canale diverso
python meeting_followup.py --slack --slack-channel @lorenzo

# Usa solo Claude per l'email
python meeting_followup.py --slack --model claude

# Aggiungi contesto
python meeting_followup.py --slack --context "This was about the Pro plan for 5 users"
```

### 4. Vai su Slack

1. Riceverai un messaggio nel canale configurato
2. Rivedi l'email e gli insights
3. Seleziona le azioni che vuoi eseguire (checkbox)
4. Click **"Execute Selected Actions"**
5. Il bot ti chiederà conferma: **"Vuoi procedere con: ..."**
6. Rispondi **"sì"** per confermare o **"no"** per annullare
7. Il bot eseguirà le azioni e ti darà feedback

## 💬 Esempio di conversazione Slack

```
🤖 Bot:
📋 Call con Acme Corp

Meeting Summary
Discussed implementation timeline and pricing for 10 users...

📧 Proposed Follow-up Email
Subject: Follow-up from our call
Hi John,
Thanks for taking the time...

💡 Sales Insights
💻 Tech Stack: Salesforce, HubSpot
⚠️ Pain Points: Manual data entry, slow lead response
📊 Impact: 10 hours/week on manual tasks
...

Select actions:
☑️ Create Gmail Draft
☑️ Add Calendar Event
☑️ Save to Crono CRM

[Execute Selected Actions] [Cancel]

---

👤 You: [deseleziona "Calendar Event" e clicca "Execute"]

---

🤖 Bot:
Vuoi procedere con:
✅ Gmail Draft
✅ Crono Note

Rispondere 'sì' per confermare o 'no' per annullare

---

👤 You: sì

---

🤖 Bot:
✅ Gmail Draft completed
   Draft ID: r1234567890
✅ Crono Note completed
   Note ID: abc123

Tutto fatto! 🎉
```

## 🔧 Troubleshooting

### "Invalid signature" error
- Verifica che `SLACK_SIGNING_SECRET` in `.env` sia corretto
- Riavvia il webhook handler dopo aver modificato `.env`

### Bot non risponde ai button clicks
- Verifica che ngrok sia attivo
- Verifica che l'URL in Slack App → Interactivity corrisponda all'URL ngrok
- Controlla i logs del webhook handler per errori

### "Channel not found"
- Assicurati che il bot sia stato invitato nel canale: `/invite @Meeting Follow-up Bot`
- Verifica che `SLACK_CHANNEL` in `.env` sia corretto (con `#`)

### Ngrok URL scade
- Gli URL ngrok gratuiti cambiano ad ogni riavvio
- Dopo aver riavviato ngrok, devi aggiornare gli URL in Slack App
- Considera un piano ngrok a pagamento per URL fissi

### Messages sent but no interactions work
- Verifica che Event Subscriptions sia abilitato
- Verifica che i bot events siano configurati correttamente
- Riavvia il webhook handler

## 📊 Workflow Comparison

### Normal Mode (senza --slack)
```
Meeting → Fathom → AI → [Choose email]
                            ↓
                    Gmail Draft ✓
                    Calendar ✓
                    Crono ✓
                    (tutto automatico)
```

### Slack Mode (con --slack)
```
Meeting → Fathom → AI → Slack Message
                            ↓
                    [Review & Choose]
                            ↓
                    [Confirm in chat]
                            ↓
                    Execute selected actions only
```

## 🎯 Quando usare Slack Mode

**Usa `--slack` quando:**
- Vuoi rivedere l'email prima di creare il draft
- Non sei sicuro se creare un calendar event
- Vuoi condividere il summary con il team prima di procedere
- Hai bisogno di più controllo sulle azioni

**Usa il modo normale quando:**
- Vuoi massima velocità
- Sei sicuro di voler creare tutto
- Usi il menu bar app con azioni pre-selezionate

## 🔐 Security Notes

- Il `SLACK_SIGNING_SECRET` verifica che le richieste vengano da Slack
- Non condividere mai il `SLACK_BOT_TOKEN` pubblicamente
- Considera di usare HTTPS anche per development (ngrok lo fa automaticamente)
- In produzione, usa un server con URL fisso e certificato SSL

## 📚 Resources

- [Slack API Documentation](https://api.slack.com/)
- [Block Kit Builder](https://app.slack.com/block-kit-builder/) - Per testare messaggi interattivi
- [ngrok Documentation](https://ngrok.com/docs)
- [Flask Documentation](https://flask.palletsprojects.com/)

---

**Domande?** Apri un issue o contatta il team di sviluppo!
