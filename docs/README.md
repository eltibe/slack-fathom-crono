# Meeting Follow-up Email Generator

Automatically generate professional follow-up emails from your Fathom meeting transcripts using AI (Claude & Gemini), create Gmail drafts, schedule calendar events, and save structured sales notes to Crono CRM.

## Features

- 📥 **Fetch meeting transcripts** from Fathom API
- 🤖 **AI-powered email generation** using Claude and Gemini
- 📧 **Automatically create Gmail drafts** with HTML formatting
- 📅 **Smart calendar events** - only creates follow-ups when actually discussed
- 🎯 **Sales-focused emails** with problem-solution-ROI framework
- 🌍 **Multi-language support** - emails in same language as meeting
- 🍎 **macOS Menu Bar App** - one-click processing with badge counter
- 💬 **Slack Integration** - slash commands `/followup` and `/meetings` with interactive buttons
- 📝 **Crono CRM Integration** - structured sales notes with AI-extracted insights
- 🎨 **Customizable tone** (professional, friendly, formal)

## Project Structure

```
cazzeggio/
├── meeting_followup.py              # Main orchestration script
├── menu_bar_app.py                  # macOS menu bar application
├── slack_webhook_handler.py         # Slack webhook server (Flask)
├── setup_config.py                  # Interactive setup helper
├── requirements.txt                 # Python dependencies
├── .env.example                     # Example environment variables
├── .env                             # Your API keys (not in git)
├── credentials.json                 # Gmail OAuth credentials (not in git)
├── token.json                       # Gmail OAuth token (auto-generated)
├── account_mappings.json            # Crono domain → company name mappings
├── crono_knowledge_base.txt         # Crono company knowledge for AI
├── PROJECT_STATUS.md                # Complete project status & implementation details
├── CHANGELOG.md                     # Version history and changes
├── CRONO_INTEGRATION_GUIDE.md       # Crono CRM setup guide
├── SLACK_INTEGRATION_GUIDE.md       # Slack slash commands setup guide
├── SALES_FOCUSED_UPDATES.md         # Sales-focused features documentation
└── modules/
    ├── fathom_client.py             # Fathom API integration
    ├── claude_email_generator.py    # Claude AI email generator (sales-focused)
    ├── gemini_email_generator.py    # Gemini AI email generator (sales-focused)
    ├── gmail_draft_creator.py       # Gmail draft creation (HTML support)
    ├── date_extractor.py            # Smart follow-up detection
    ├── calendar_event_creator.py    # Google Calendar integration
    ├── meeting_summary_generator.py # AI meeting summaries
    ├── sales_summary_generator.py   # Extract sales insights from transcripts
    ├── slack_slash_commands.py      # Slack UI generation (Block Kit)
    └── crono_client.py              # Crono CRM integration
```

## Setup Instructions

### 1. Install Dependencies

```bash
cd /Users/lorenzo/cazzeggio

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Get API Keys

#### Anthropic (Claude) API
1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to API Keys
4. Create a new API key
5. Copy the key

#### Google Gemini API
1. Go to https://makersuite.google.com/app/apikey
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the key

#### Fathom API
1. Log into https://app.fathom.video/
2. Go to Settings → Integrations
3. Generate an API key
4. Copy the key

**Note:** Fathom API access typically requires a Business or Enterprise plan.

### 3. Configure API Keys

#### Option A: Interactive Setup (Recommended)
```bash
python setup_config.py
```

Follow the prompts to enter your API keys.

#### Option B: Manual Setup
```bash
cp .env.example .env
```

Edit `.env` and add your keys:
```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
FATHOM_API_KEY=fathom_...
```

### 4. Setup Gmail API

#### Step 1: Create Google Cloud Project
1. Go to https://console.cloud.google.com/
2. Create a new project or select an existing one
3. Note your project name

#### Step 2: Enable Gmail API
1. In your project, go to "APIs & Services" → "Library"
2. Search for "Gmail API"
3. Click "Enable"

#### Step 3: Create OAuth Credentials
1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. If prompted, configure the OAuth consent screen:
   - User Type: External
   - App name: "Meeting Follow-up Generator"
   - Add your email as a test user
4. Choose "Desktop app" as application type
5. Name it "Meeting Follow-up Client"
6. Click "Create"

#### Step 4: Download Credentials
1. Click the download button (⬇️) next to your OAuth client
2. Save the file as `credentials.json` in the `/Users/lorenzo/cazzeggio/` directory

#### Step 5: First-time Authentication
The first time you run the script, it will:
1. Open a browser window
2. Ask you to log in to Google
3. Request permission to create Gmail drafts
4. Save a `token.json` file for future use

## Usage

### 🍎 Menu Bar App (Recommended)

The easiest way to use this tool:

```bash
python3 menu_bar_app.py
```

This creates a 🚀 icon in your macOS menu bar with:
- **Badge counter** showing today's meeting count
- **Meeting selection** - choose which meeting to process
- **Crono note option** - decide if you want to create CRM note
- **Real-time notifications** - status updates as it processes
- **Quick access** - one-click to Gmail drafts and Calendar

**Workflow:**
1. Click 🚀 icon in menu bar
2. Select "📧 Generate Follow-up Email"
3. Choose meeting from today's list
4. Choose whether to create Crono note
5. Wait for notification ✅
6. Review draft in Gmail and send!

### 💬 Slack Integration (New!)

Use slash commands in Slack for team collaboration:

```bash
# Start webhook server
python3 slack_webhook_handler.py > followup_webhook.log 2>&1 &
```

**Workflow in Slack:**
1. Type `/followup` or `/meetings` in any Slack channel
2. Select a meeting from today's list (radio buttons)
3. Click "Generate Follow-up" button
4. Wait 30-60 seconds for AI processing
5. Choose actions with interactive buttons:
   - 📧 Create Gmail Draft
   - 📅 Create Calendar Event (1 week follow-up)
   - 📝 Create Crono Note (sales insights)

**Benefits:**
- Team visibility into meeting follow-ups
- Interactive approval workflow
- All actions available in one place
- Real-time processing with AI

For setup instructions, see [SLACK_INTEGRATION_GUIDE.md](SLACK_INTEGRATION_GUIDE.md)

### 💻 Command Line Usage

```bash
python meeting_followup.py
```

This will:
1. Fetch your latest Fathom meeting
2. Generate emails with both Claude and Gemini
3. Let you compare and choose the better version
4. Create a Gmail draft
5. Create a calendar follow-up event (if discussed)

### Advanced Options

#### Use only Claude or Gemini
```bash
# Use only Claude
python meeting_followup.py --model claude

# Use only Gemini
python meeting_followup.py --model gemini

# Use both (default)
python meeting_followup.py --model both
```

#### Add recipients
```bash
python meeting_followup.py --to colleague@example.com
python meeting_followup.py --to person1@example.com person2@example.com
```

#### Change email tone
```bash
python meeting_followup.py --tone friendly
python meeting_followup.py --tone formal
python meeting_followup.py --tone professional  # default
```

#### Add custom context
```bash
# Add specific context about the meeting
python meeting_followup.py --context "This was a follow-up about the Ultra plan for 10 users"

# Add context about what to include
python meeting_followup.py --context "Mention the integration with Salesforce we discussed"
```

#### Combine options
```bash
python meeting_followup.py --model claude --tone friendly --to team@example.com --context "Follow-up on Pro plan pricing"
```

### Crono-Specific Features

This tool is customized for Crono.one sales emails and includes:

#### Company Knowledge Base
The AI has built-in knowledge about:
- **Crono products and features** (GTM platform, integrations, AI messaging, etc.)
- **Pricing plans:**
  - **Pro Plan:** €79-99/user/month (minimum 2 users)
  - **Ultra Plan:** €119-149/user/month (minimum 5 users)
  - **Titan Plan:** Custom pricing for 50+ users
- **Customer success stories** (Spoki +12% ACV, Alibaba +70% revenue, Unguess +800 meetings, Serenis +19% demo rates)
- **200+ enterprise customers** and G2 recognition

#### Smart Email Writing
The AI automatically:
- Uses an **approachable, professional tone** (not overly formal)
- **Avoids "--" separators** (uses bullet points instead)
- **Listens for instructions** in the meeting transcript about what to include in follow-up
- **Does pricing calculations** when plans are discussed (e.g., "For 8 users on Ultra annual plan: €952/month")
- **Always proposes a follow-up meeting** if one isn't already scheduled
- **Summarizes the main benefit** for the customer based on their needs
- **References relevant customer stories** as social proof

#### Updating the Knowledge Base
To update company information, edit:
```bash
/Users/lorenzo/cazzeggio/crono_knowledge_base.txt
```

This file contains all the Crono-specific context that both Claude and Gemini use when generating emails.

### 📝 Crono CRM Integration

**NEW:** Automatically create structured sales notes in Crono CRM!

When you choose to create a Crono note (via menu bar app), the system:

1. **🤖 Extracts sales insights** using AI:
   - 💻 **Tech Stack** - Technologies and tools mentioned
   - ⚠️ **Pain Points** - Specific problems and challenges
   - 📊 **Impact** - Quantified business impact (time, money, opportunities)
   - ✅ **Next Steps** - Agreed actions with dates and owners
   - 🚧 **Roadblocks** - Potential obstacles (budget, approvals, concerns)

2. **🔍 Finds the company** in Crono CRM automatically

3. **📝 Creates a formatted note** with all sales insights

**Setup:**
```bash
# Add to .env file
CRONO_API_KEY=your_crono_api_key
CRONO_API_URL=https://dev.api.crono.one/cronoapi-e3b0madc44269/v1
```

**For detailed setup and usage**, see: [CRONO_INTEGRATION_GUIDE.md](CRONO_INTEGRATION_GUIDE.md)

### Example Workflow

```bash
# 1. Have a meeting (Fathom records and transcribes)

# 2. Run the script
python meeting_followup.py

# Output:
# 🚀 Meeting Follow-up Email Generator
# ==================================================
#
# 📥 Fetching meeting transcript from Fathom...
# ✓ Found meeting: Product Planning Session
#
# 🤖 Generating follow-up emails...
#   → Generating with Claude...
#   ✓ Claude email generated
#   → Generating with Gemini...
#   ✓ Gemini email generated
#
# ======================================
# CLAUDE'S VERSION:
# ======================================
# [Email content...]
#
# ======================================
# GEMINI'S VERSION:
# ======================================
# [Email content...]
# ======================================
#
# Which version would you like to use? (claude/gemini/quit): claude
#
# 📧 Creating Gmail draft...
# Draft created successfully! Draft ID: r1234567890
#
# ✅ Success! Draft created in Gmail.
#    Open Gmail to review and send your draft:
#    https://mail.google.com/mail/#drafts

# 3. Open Gmail, review the draft, and send!
```

## Testing Individual Modules

Each module can be tested independently:

```bash
# Test Fathom API
cd modules
python fathom_client.py

# Test Claude email generator
python claude_email_generator.py

# Test Gemini email generator
python gemini_email_generator.py

# Test Gmail draft creator
python gmail_draft_creator.py
```

## Troubleshooting

### "Fathom API key is required"
- Make sure your `.env` file exists and contains `FATHOM_API_KEY`
- Check that your Fathom account has API access enabled

### "credentials.json not found"
- Download OAuth credentials from Google Cloud Console
- Save as `credentials.json` in the project root

### "No meetings found"
- Ensure you have at least one recorded meeting in Fathom
- Check that your Fathom API key has access to your meetings

### Gmail authentication issues
- Delete `token.json` and re-authenticate
- Check that Gmail API is enabled in Google Cloud Console
- Ensure your email is added as a test user in OAuth consent screen

### Import errors
- Make sure you're in the virtual environment: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r requirements.txt`

## Security Notes

⚠️ **Important**: Never commit sensitive files to git!

The `.gitignore` file excludes:
- `.env` (API keys)
- `credentials.json` (Gmail OAuth credentials)
- `token.json` (Gmail OAuth token)

## Learning Goals

This project helps you learn:
- API integration with multiple services (Fathom, Anthropic, Google)
- OAuth 2.0 authentication flow
- Working with different AI models
- Building practical automation tools
- Comparing AI model outputs

## Next Steps

Ideas to extend this project:
- Add support for more AI models (OpenAI GPT, etc.)
- Implement webhook listening for automatic triggers
- Add email templates for different meeting types
- Create a web interface
- Add support for Slack/Teams notifications
- Implement meeting summary storage/database

## License

Personal learning project - feel free to use and modify!

## Resources

- [Fathom API Documentation](https://docs.fathom.video/)
- [Anthropic API Documentation](https://docs.anthropic.com/)
- [Google Gemini API Documentation](https://ai.google.dev/docs)
- [Gmail API Documentation](https://developers.google.com/gmail/api)
