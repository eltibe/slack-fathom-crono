# 🎯 Slack Meeting Follow-up Bot - Project Status

**Last Updated:** 2025-11-26
**Status:** ✅ FULLY FUNCTIONAL

---

## 📋 Overview

Sistema completo per gestire follow-up dei meeting Fathom via Slack con integrazione Gmail, Google Calendar e Crono CRM.

---

## ✅ Funzionalità Implementate

### 1. Comando Slack `/followup` o `/meetings`
- ✅ Mostra tutti i meeting di oggi da Fathom
- ✅ Interfaccia con radio buttons per selezione
- ✅ Bottone "Generate Follow-up" per elaborazione

### 2. Elaborazione Meeting con AI
- ✅ Recupera transcript da Fathom API
- ✅ Genera email di follow-up con Claude AI
- ✅ Genera summary del meeting
- ✅ Estrae sales insights (tech stack, pain points, impact, next steps, roadblocks)
- ✅ Formattazione HTML → Markdown per Slack
- ✅ Processing in background (evita timeout Slack 3s)

### 3. Action Buttons

#### 📧 Create Gmail Draft
- ✅ Crea bozza in Gmail con email generata
- ✅ Destinatari: attendee esterni del meeting
- ✅ Autenticazione OAuth rinnovata
- ✅ **TESTATO E FUNZIONANTE**

#### 📅 Create Calendar Event
- ✅ Crea evento follow-up 1 settimana dopo
- ✅ Include attendee esterni
- ✅ Aggiunge descrizione dal summary
- ✅ Crea Google Meet automaticamente

#### 📝 Create Crono Note
- ✅ Trova account Crono per dominio email
- ✅ Crea nota strutturata con sales insights
- ✅ Include link a registrazione Fathom
- ✅ Supporto HTML nel contenuto
- ✅ **Account NeuronUP configurato**

---

## 📁 File Principali Modificati

### Core Files

#### `/Users/lorenzo/cazzeggio/slack_webhook_handler.py`
**Modifiche:**
- Aggiunto background threading per evitare timeout Slack
- Implementato `handle_process_meeting_button()` con response_url
- Implementato `handle_create_gmail_draft()` (linee 555-654)
- Implementato `handle_create_calendar_event()` (linee 657-760)
- Implementato `handle_create_crono_note()` (linee 763-895)
- Aggiunto salvataggio dati in `conversation_state` (linee 390-401)
- Conversione HTML → Markdown per Slack (linee 399-417)
- Formattazione sales insights con emoji (linee 420-437)

**Funzioni chiave:**
```python
process_selected_meeting()  # Linea 313
handle_create_gmail_draft()  # Linea 555
handle_create_calendar_event()  # Linea 657
handle_create_crono_note()  # Linea 763
```

#### `/Users/lorenzo/cazzeggio/modules/fathom_client.py`
**Modifiche:**
- Fix confronto `recording_id` con conversione a stringa (linea 104)
- `get_specific_meeting_with_transcript()` cerca in 200 meeting recenti
- Rimosso tentativo di chiamare endpoint `/recordings/{id}` (404)

**Metodo importante:**
```python
get_specific_meeting_with_transcript(recording_id)  # Linea 86
```

#### `/Users/lorenzo/cazzeggio/modules/slack_slash_commands.py`
**Modifiche:**
- Fix `recording_id` convertito a string per Slack (linea 187)
- Filtra meeting per data odierna con timezone UTC

**Metodo importante:**
```python
_get_todays_meetings()  # Linea 83
```

#### `/Users/lorenzo/cazzeggio/modules/crono_client.py`
**Modifiche principali:**
- ✅ Base URL aggiornato: `https://ext.crono.one/v1` (linea 25)
- ✅ `create_note()` riscritto con formato API v1 (linee 151-216)
  - Payload: `{"data": {"description": "...", "accountId": "...", ...}}`
  - Response: `{"isSuccess": true, "data": {...}, "errors": []}`
- ✅ Aggiunto `search_accounts_by_name()` - POST search (linee 84-121)
- ✅ Aggiunto `_check_domain_mapping()` - legge mappings locali (linee 123-145)
- ✅ `find_account_by_domain()` con 3 strategie (linee 343-403):
  1. Controlla mapping locale (`account_mappings.json`)
  2. POST search per nome (più accurato)
  3. GET search per nome (fallback)

**Strategia di ricerca account:**
```python
# Strategia 0: Mapping locale (più veloce)
mapped_value = self._check_domain_mapping(email_domain)
if mapped_value:
    # Se contiene underscore → objectId (prova GET /Accounts/{id})
    # Altrimenti → company name (usa POST search)
    if '_' in mapped_value:
        account = self.get_account_by_id(mapped_value)
    else:
        account = self.search_accounts_by_name(mapped_value)

# Strategia 1: Ricerca in 200 account recenti per website
accounts = self.search_accounts(limit=200)
domain_matches = self._filter_by_website_domain(accounts, email_domain)

# Strategia 2: POST search per nome (accurato)
account = self.search_accounts_by_name(company_name)

# Strategia 3: GET search per nome (fallback)
accounts = self.search_accounts(query=company_name)
```

**⚠️ Nota:** Strategy 0 ora supporta sia objectId che company names. Usa company names se GET `/v1/Accounts/{id}` restituisce 404.

### Configuration Files

#### `/Users/lorenzo/cazzeggio/account_mappings.json` ⭐ NUOVO
```json
{
  "domain_to_account": {
    "neuronup.com": "NeuronUP",
    "insightrevenue.com": "Insight Revenue"
  },
  "comments": {
    "neuronup.com": "NeuronUP - Company name for POST search",
    "insightrevenue.com": "Insight Revenue - Company name for POST search"
  },
  "note": "Values are company names used for POST /api/v1/Accounts/search"
}
```

**Scopo:** Mapping manuale dominio → company name Crono per account oltre il limite API (200)

**⚠️ IMPORTANTE:** I valori sono **company names**, non objectId, perché l'endpoint GET `/v1/Accounts/{id}` restituisce 404 per molti account. Il sistema usa automaticamente POST `/api/v1/Accounts/search` con il nome dell'azienda.

**Come aggiungere nuovi mapping:**
```json
"domain_to_account": {
  "neuronup.com": "NeuronUP",
  "esempio.com": "Nome Azienda Esatto"
}
```

**Come trovare il nome esatto:**
```bash
python3 test_find_insightrevenue.py  # Modificare per cercare l'azienda desiderata
```

#### `/Users/lorenzo/cazzeggio/.env`
**Chiavi configurate:**
```bash
# Slack
SLACK_BOT_TOKEN=xoxb-2854114626724-9956667730244-...
SLACK_SIGNING_SECRET=51f9dae2910ecd4db71c5642c2fcff8e

# Fathom
FATHOM_API_KEY=***

# Claude AI
ANTHROPIC_API_KEY=***

# Crono CRM
CRONO_API_KEY=csk_piJu7Z...  # Private key
CRONO_PUBLIC_KEY=cpk_5GTWvL...  # Public key
```

#### `/Users/lorenzo/cazzeggio/token.json`
- Token OAuth per Gmail/Calendar APIs
- Rinnovato il 2025-11-26
- Auto-refresh quando scade

---

## 🔧 Configurazione Slack

### Slash Commands
**URL:** `https://ciderlike-sleetier-maureen.ngrok-free.dev/slack/commands`

Comandi configurati:
- `/followup` → Mostra meeting di oggi
- `/meetings` → Alias di /followup

### Interactive Components
**URL:** `https://ciderlike-sleetier-maureen.ngrok-free.dev/slack/interactions`

Gestisce:
- Radio button selection (meeting)
- Button clicks (Generate Follow-up, Create Gmail Draft, etc.)

### Bot Token Scopes
```
chat:write
commands
```

---

## 🚀 Come Eseguire

### 1. Avvia Webhook Server
```bash
cd /Users/lorenzo/cazzeggio
python3 slack_webhook_handler.py > followup_webhook.log 2>&1 &
```

### 2. Verifica Server Running
```bash
lsof -ti:3000  # Dovrebbe mostrare il PID
tail -f followup_webhook.log  # Monitor logs
```

### 3. Ngrok (già configurato)
```bash
# Ngrok dovrebbe essere già running su:
https://ciderlike-sleetier-maureen.ngrok-free.dev
```

### 4. Test in Slack
```
/followup
→ Seleziona meeting
→ Click "Generate Follow-up"
→ Aspetta 30-60 secondi
→ Test bottoni: Gmail Draft, Calendar Event, Crono Note
```

---

## 🧪 Testing

### Test Gmail Draft
```bash
python3 modules/gmail_draft_creator.py
```

### Test Calendar Event
```bash
python3 modules/calendar_event_creator.py
```

### Test Crono Search
```bash
python3 test_crono_advanced_search.py
```

### Test Crono Note Creation
```bash
cd /Users/lorenzo/cazzeggio
python3 -c "
from modules.crono_client import CronoClient
from dotenv import load_dotenv
load_dotenv()

crono = CronoClient()
account = crono.find_account_by_domain('neuronup.com', 'NeuronUP')
print(f'Account: {account.get(\"name\")} - {account.get(\"objectId\")}')

note_id = crono.create_meeting_summary(
    account_id=account['objectId'],
    meeting_title='Test Meeting',
    summary_data={
        'tech_stack': 'React, Node.js',
        'pain_points': 'Manual processes',
        'impact': 'Wasted 10h/week',
        'next_steps': 'Demo next week',
        'roadblocks': 'Budget approval needed'
    },
    meeting_url='https://app.fathom.video/meetings/test'
)
print(f'Note created: {note_id}')
"
```

---

## 🐛 Problemi Risolti

### 1. Slack 3-Second Timeout ✅
**Problema:** Handler bloccava la risposta HTTP
**Soluzione:** Background threading + response_url per delayed responses

### 2. Invalid Blocks Error ✅
**Problema:** `recording_id` era int, Slack vuole string
**Soluzione:** `str(meeting['recording_id'])` in slack_slash_commands.py:187

### 3. Fathom 404 Error ✅
**Problema:** Endpoint `/recordings/{id}` non esiste
**Soluzione:** Cerca in lista di 200 meeting recenti, confronta recording_id

### 4. HTML in Slack Messages ✅
**Problema:** Tag HTML (`<b>`, `<p>`) mostrati letteralmente
**Soluzione:** Funzione `html_to_text()` converte HTML → Markdown

### 5. Sales Insights JSON Dump ✅
**Problema:** Dati mostrati come stringa JSON
**Soluzione:** Funzione `format_sales_data()` con emoji e campi leggibili

### 6. Gmail Token Expired ✅
**Problema:** `invalid_grant` error
**Soluzione:** `rm token.json` e ri-autenticazione

### 7. Crono Account Non Trovato (NeuronUP, InsightRevenue) ✅
**Problema:** Account oltre limite 200 dell'API GET, endpoint GET `/v1/Accounts/{id}` restituisce 404
**Soluzione:**
- Mapping locale in `account_mappings.json` con **company names** (non objectId)
- Strategy 0: Se trova mapping locale, usa POST search con `{"name": "CompanyName"}`
- POST search `{"name": "ExactName"}` funziona anche per account oltre il limite 200
- Sistema a 3 strategie di fallback (mapping locale → POST search by name → GET search by name)
- ✅ NeuronUP: `"neuronup.com": "NeuronUP"`
- ✅ InsightRevenue: `"insightrevenue.com": "Insight Revenue"`

---

## 📊 API Endpoints Usati

### Fathom API
```
GET  https://api.fathom.ai/external/v1/meetings?limit=200
GET  https://api.fathom.ai/external/v1/recordings/{id}/transcript
```

### Crono API
```
GET  https://ext.crono.one/v1/Accounts?limit=200
GET  https://ext.crono.one/v1/Accounts/{objectId}
POST https://ext.crono.one/api/v1/Accounts/search
POST https://ext.crono.one/v1/Notes
```

**Nota importante:** L'endpoint di ricerca usa base URL diverso!
- Accounts: `/v1/Accounts`
- Search: `/api/v1/Accounts/search` ⚠️
- Notes: `/v1/Notes`

### Slack API
```
POST response_url  # Delayed responses
```

### Google APIs
```
Gmail API: drafts().create()
Calendar API: events().insert()
```

---

## 🔑 Note Tecniche Importanti

### Crono API Peculiarities

1. **Limite account:** Max 200 per richiesta GET
2. **Search endpoint:**
   - ❌ `{"search": "text"}` → restituisce risultati casuali
   - ✅ `{"name": "ExactName"}` → funziona correttamente
3. **Base URL doppio:**
   - `/v1/` per Accounts e Notes
   - `/api/v1/` per search endpoint
4. **Note format:**
   ```json
   {
     "data": {
       "description": "HTML content here",
       "accountId": "25995825_XXXXXX",
       "opportunityId": null,
       "prospectIds": []
     }
   }
   ```
5. **API Read-Only Limitations (documentato in https://ext.crono.one/docs/):**
   - ✅ **Disponibili:** GET Opportunities, GET Activities, POST search
   - ❌ **NON Disponibili:** PUT/PATCH per update, POST per create, DELETE
   - **Implicazione:** Impossibile aggiornare stage di deal o creare task da API
   - **Workaround:** Bottone "Open in Crono CRM" per gestire manualmente nel CRM

### Slack Best Practices

1. **Timeout 3s:** Sempre rispondere entro 3s, usare threading per long operations
2. **response_url:** Per aggiornamenti dopo 3s, ha TTL di 30 minuti
3. **Block values:** Sempre string, mai int
4. **Markdown:** Supportato ma limitato (no HTML)

### Fathom API Quirks

1. **No endpoint `/recordings/{id}`:** Usare GET /meetings + filter locale
2. **Transcript structure:** Nested `transcript.transcript[]`
3. **Speaker format:** `{display_name: "Name"}` non semplice stringa

---

## 📝 TODO / Possibili Miglioramenti

### Priorità Bassa
- [ ] Aggiungere caching per meeting già processati
- [ ] Supporto per meeting di ieri/settimana scorsa
- [ ] Edit manuale email/summary prima di creare draft
- [ ] Notifiche quando note/events sono creati
- [ ] Dashboard con statistiche meeting processati
- [ ] Support per altre lingue oltre italiano/inglese

### Opzionale
- [ ] Deployment su server persistente (no localhost)
- [ ] Database per storico meeting processati
- [ ] Webhook Fathom per auto-processing nuovi meeting
- [ ] Integration con altri CRM oltre Crono

---

## 📞 Contatti & Support

**Developer:** Claude Code Assistant
**Repository:** `/Users/lorenzo/cazzeggio`
**Log file:** `followup_webhook.log`

### Quick Commands
```bash
# Restart server
lsof -ti:3000 | xargs kill && python3 slack_webhook_handler.py > followup_webhook.log 2>&1 &

# View logs
tail -f followup_webhook.log

# Clear Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Test Crono account search
python3 test_crono_advanced_search.py
```

---

## ✅ Sistema Pronto per Produzione

Tutti i componenti sono implementati e testati. Il sistema è completamente funzionale.

**Ultima modifica:** 2025-11-27 15:30
**Status:** ✅ PRODUCTION READY - STABLE VERSION

**Aggiornamenti recenti:**
- ✅ **[2025-11-27]** Bottone "Open in Crono CRM"
  - Aggiunto link diretto all'account Crono da Slack
  - Appare dopo "View Crono Deals" e "Create Crono Note"
  - URL: `https://app.crono.one/accounts/{account_id}`
  - Evita ricerca manuale dell'account nel CRM
- ✅ **[2025-11-27]** Fix formattazione Crono notes
  - Rimossi tag HTML (`<h2>`, `<h3>`, `<p>`) da `create_meeting_summary()`
  - Usato plain text con emoji e newlines per leggibilità
  - Note ora si vedono correttamente in Crono CRM
- ✅ **[2025-11-27]** Aggiunto fallback automatico meeting di ieri
  - Se oggi non ci sono meeting, mostra automaticamente quelli di ieri
  - Metodi `_get_meetings_by_date()` e `_get_yesterdays_meetings()`
  - UI aggiornata con label "Today" o "Yesterday"
- ✅ **[2025-11-27]** Aggiunto supporto Crono Deals/Opportunities
  - Implementato `search_opportunities()` e `get_deals_for_account()`
  - Bottone "View Crono Deals" ora funzionante in Slack
  - Testato con InsightRevenue (1 deal trovato)
- ✅ **[2025-11-26]** Ripristinato `crono_client.py` alla versione corretta
- ✅ **[2025-11-26]** Aggiunto supporto per InsightRevenue account in Crono
- ✅ **[2025-11-26]** Sistema mapping ora supporta sia objectId che company names
- ✅ **[2025-11-26]** NeuronUP e InsightRevenue configurati con company names per POST search
