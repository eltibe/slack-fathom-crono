# 🚀 Crono Menu Bar App - Guida Completa

App nativa macOS per generare follow-up automatici con un click dalla menu bar!

## 🎯 Caratteristiche

✅ **Icona sempre visibile** in alto a destra
✅ **Badge con conteggio** meeting di oggi (es. "🚀 3")
✅ **Status in tempo reale** mentre processa
✅ **Notifiche desktop** quando completato
✅ **Un click** e parte tutto automaticamente

## 📦 Installazione

### Passo 1: Installa l'app

```bash
cd /Users/lorenzo/cazzeggio
bash install_menubar.sh
```

Questo installerà le dipendenze necessarie.

### Passo 2: Avvia l'app

```bash
python3 menu_bar_app.py
```

**Vedrai:** L'icona 🚀 apparire in alto a destra nella menu bar!

### Passo 3 (Opzionale): Auto-start all'avvio

Per far partire l'app automaticamente quando accendi il Mac:

```bash
bash setup_autostart.sh
```

## 🎮 Come Usare

### Menu Bar Icon

Quando l'app è attiva, vedrai:

```
Menu Bar: WiFi 🔋 🔊 🕐 [🚀 3]
                            ↑
                      Badge con numero
                   meeting di oggi
```

### Click sull'Icona

```
┌───────────────────────────────────┐
│ 📧 Generate Follow-up Email      │  <- Click qui dopo meeting
│ ─────────────────────────────────│
│ 📊 Today's Meetings              │  <- Vedi lista meeting oggi
│ 📅 Open Calendar                 │  <- Apre Google Calendar
│ ✉️  Open Gmail Drafts            │  <- Apre Gmail drafts
│ ─────────────────────────────────│
│ 🔄 Refresh Badge                 │  <- Aggiorna contatore
│ ─────────────────────────────────│
│ ❌ Quit Crono                    │  <- Chiude app
└───────────────────────────────────┘
```

## 🔔 Notifiche Desktop

### Quando inizi il processo:
```
┌────────────────────────────────┐
│ 🔄 Crono Follow-up             │
│ Processing...                  │
│ Fetching meeting and           │
│ generating email...            │
└────────────────────────────────┘
```

### Quando completa:
```
┌────────────────────────────────┐
│ ✅ Crono Follow-up             │
│ Success!                       │
│ Draft created in Gmail and     │
│ calendar event added!          │
└────────────────────────────────┘
```

## 📊 Badge Dinamico

Il badge cambia in tempo reale:

- **🚀** - Nessun meeting oggi
- **🚀 3** - 3 meeting oggi
- **🔄** - Sta processando (icona animata)

## 🎯 Workflow Tipico

**Dopo un meeting:**

1. 👀 Guardi in alto a destra → Vedi **🚀 2** (2 meeting oggi)
2. 🖱️ Click sull'icona
3. 📧 Click su "Generate Follow-up Email"
4. ⏳ Vedi icona cambiare a **🔄** (processing)
5. 🔔 Ricevi notifica desktop "Processing..."
6. ⏱️ Dopo 30-60 secondi
7. 🔔 Ricevi notifica "✅ Success!"
8. 📧 Vai su Gmail → Draft pronto
9. 📅 Vai su Calendar → Evento creato

**Totale tempo:** 1 click + 1 minuto di attesa → Tutto fatto!

## ⚙️ Configurazione Auto-Start

### Controlla se è attivo:
```bash
launchctl list | grep crono
```

### Disattiva auto-start:
```bash
launchctl unload ~/Library/LaunchAgents/com.crono.menubar.plist
```

### Riattiva auto-start:
```bash
launchctl load ~/Library/LaunchAgents/com.crono.menubar.plist
```

### Rimuovi completamente:
```bash
launchctl unload ~/Library/LaunchAgents/com.crono.menubar.plist
rm ~/Library/LaunchAgents/com.crono.menubar.plist
```

## 🐛 Troubleshooting

### L'icona non appare

1. Verifica che l'app sia in esecuzione:
```bash
ps aux | grep menu_bar_app
```

2. Riavvia l'app:
```bash
pkill -f menu_bar_app
python3 menu_bar_app.py
```

### Badge non aggiorna

Click su "🔄 Refresh Badge" nel menu

### Notifiche non appaiono

Verifica permessi notifiche:
- System Preferences → Notifications → Script Editor (o Python)
- Abilita "Allow Notifications"

### Errori nel log

Controlla i log:
```bash
tail -f /Users/lorenzo/cazzeggio/menubar.log
tail -f /Users/lorenzo/cazzeggio/menubar_error.log
```

## 💡 Tips & Tricks

### Shortcut da Tastiera

Puoi aggiungere una hotkey globale:
1. System Preferences → Keyboard → Shortcuts
2. App Shortcuts → +
3. Application: Python
4. Menu Title: "Generate Follow-up Email"
5. Keyboard Shortcut: `⌘⇧F` (Cmd+Shift+F)

### Background Processing

L'app gira in background - non serve tenere il Terminale aperto!

### Performance

- **CPU:** Quasi zero quando idle
- **RAM:** ~50MB
- **Batteria:** Impatto minimo

## 🚀 Comandi Rapidi

```bash
# Avvia
python3 menu_bar_app.py

# Avvia in background (detached)
nohup python3 menu_bar_app.py > /dev/null 2>&1 &

# Stop
pkill -f menu_bar_app

# Restart
pkill -f menu_bar_app && python3 menu_bar_app.py

# Check status
ps aux | grep menu_bar_app
```

## 📈 Statistiche

L'app mostra:
- **Meeting di oggi:** Conteggio in tempo reale
- **Ultimo check:** Quando ha controllato l'ultima volta
- **Status:** Processing/Idle/Error

## 🎨 Personalizzazione

Puoi modificare `menu_bar_app.py` per:
- Cambiare icona (default: 🚀)
- Aggiungere altre voci al menu
- Cambiare timeout (default: 3 minuti)
- Personalizzare notifiche

## ✨ Prossimi Upgrade (Opzionali)

Posso aggiungere:
- [ ] Hotkey globale (es. Cmd+Shift+F ovunque)
- [ ] Preview email prima di creare draft
- [ ] Selezione manuale meeting (se hai più meeting oggi)
- [ ] History degli ultimi follow-up
- [ ] Widget per vedere status senza aprire menu

Vuoi qualcuna di queste feature? 🎯
