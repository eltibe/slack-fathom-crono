# Slack-Fathom-Crono Integration - Setup & Usage Guide

Complete guide for setting up and using the Slack app that integrates Fathom meeting recordings with Crono CRM.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Setup Instructions](#setup-instructions)
   - [Step 1: Slack App Configuration](#step-1-slack-app-configuration)
   - [Step 2: Fathom Integration](#step-2-fathom-integration)
   - [Step 3: Crono CRM Integration](#step-3-crono-crm-integration)
   - [Step 4: AI Services Setup](#step-4-ai-services-setup)
3. [User Onboarding](#user-onboarding)
4. [How to Use the App](#how-to-use-the-app)
5. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before starting, make sure you have:

- [ ] Admin access to your Slack workspace
- [ ] A Fathom account with API access
- [ ] A Crono CRM account
- [ ] Access to Google AI Studio (for Gemini API) OR Anthropic API (for Claude)

---

## Setup Instructions

### Step 1: Slack App Configuration

#### 1.1 Create Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Enter app name: `Crono Meeting Assistant` (or your preferred name)
5. Select your workspace
6. Click **"Create App"**

#### 1.2 Configure OAuth Scopes

1. In your app settings, go to **"OAuth & Permissions"**
2. Scroll to **"Scopes"** section
3. Add these **Bot Token Scopes**:
   - `chat:write`
   - `commands`
   - `im:history`
   - `im:write`
   - `users:read`
   - `users:read.email`

#### 1.3 Enable Interactivity

1. Go to **"Interactivity & Shortcuts"**
2. Toggle **"Interactivity"** to **ON**
3. Set **Request URL** to: `https://your-app-url.com/slack/interactions`
   - Replace `your-app-url.com` with your actual deployment URL (e.g., Render URL)
4. Click **"Save Changes"**

#### 1.4 Create Slash Commands

Go to **"Slash Commands"** and create these commands:

| Command | Request URL | Short Description |
|---------|-------------|-------------------|
| `/crono-connect` | `https://your-app-url.com/slack/commands` | Connect your Crono CRM account |
| `/crono-add-note` | `https://your-app-url.com/slack/commands` | Add a note to Crono CRM |
| `/crono-add-task` | `https://your-app-url.com/slack/commands` | Create a task in Crono CRM |
| `/crono-search` | `https://your-app-url.com/slack/commands` | Search contacts in Crono CRM |
| `/crono-settings` | `https://your-app-url.com/slack/commands` | Configure your Crono settings |

For each command:
1. Click **"Create New Command"**
2. Enter the command name
3. Enter the Request URL (same for all: `https://your-app-url.com/slack/commands`)
4. Add the short description
5. Click **"Save"**

#### 1.5 Install App to Workspace

1. Go to **"Install App"**
2. Click **"Install to Workspace"**
3. Review permissions and click **"Allow"**
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)
   - You'll need this for your `.env` file

#### 1.6 Get App Credentials

1. Go to **"Basic Information"**
2. Copy these values (you'll need them later):
   - **Signing Secret** (under "App Credentials")
   - **Bot User OAuth Token** (from previous step)

---

### Step 2: Fathom Integration

#### 2.1 Get Fathom API Key

1. Log in to [Fathom](https://app.fathom.video)
2. Go to **Settings** → **Integrations** → **API**
3. Click **"Generate New API Key"**
4. Copy the API key
5. Save it securely - you'll need it for the `.env` file

#### 2.2 Configure Fathom Webhook

1. In Fathom, go to **Settings** → **Integrations** → **Webhooks**
2. Click **"Add Webhook"**
3. Set **URL** to: `https://your-app-url.com/fathom/webhook`
4. Select event: **"Recording Complete"**
5. Click **"Save"**

---

### Step 3: Crono CRM Integration

#### 3.1 Get Crono API Credentials

Each user needs their own Crono API keys:

1. Log in to [Crono CRM](https://app.crono.one)
2. Go to **Settings** → **API** or **Integrations**
3. Generate or copy:
   - **Public Key** (also called API Key)
   - **Private Key** (also called API Secret)
4. Save these securely

**Note**: Users will connect their personal Crono accounts using `/crono-connect` in Slack.

---

### Step 4: AI Services Setup

You need at least ONE of these AI services:

#### Option A: Google Gemini (Recommended)

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click **"Get API Key"**
4. Click **"Create API key in new project"** or select an existing project
5. Copy the API key (starts with `AIza...`)
6. Save it for your `.env` file

#### Option B: Anthropic Claude

1. Go to [Anthropic Console](https://console.anthropic.com/)
2. Sign up or log in
3. Go to **API Keys**
4. Click **"Create Key"**
5. Copy the API key (starts with `sk-ant-...`)
6. Save it for your `.env` file

---

### Step 5: Environment Configuration

#### 5.1 Create `.env` File

Create a `.env` file in your project root with these variables:

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret

# Fathom
FATHOM_API_KEY=your-fathom-api-key

# Crono (Default/Admin credentials - optional)
CRONO_PUBLIC_KEY=your-crono-public-key
CRONO_API_KEY=your-crono-private-key

# AI Services (at least one required)
GEMINI_API_KEY=your-gemini-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key

# App Configuration
PORT=3000
LOG_LEVEL=INFO
```

#### 5.2 Deploy Application

If using Render:

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `slack-fathom-crono`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python src/slack_webhook_handler.py`
5. Add all environment variables from your `.env` file
6. Click **"Create Web Service"**
7. Copy the deployment URL (e.g., `https://your-app.onrender.com`)
8. Update your Slack app URLs with this deployment URL

---

## User Onboarding

Each user needs to connect their Crono CRM account:

### Connect Crono Account

1. Open Slack
2. Type `/crono-connect`
3. A modal will appear asking for:
   - **Crono Public Key**: Your personal Crono API Key
   - **Crono Private Key**: Your personal Crono API Secret
4. Click **"Connect"**
5. You should see a success message

**Where to find your Crono keys:**
- Log in to [Crono CRM](https://app.crono.one)
- Go to Settings → API
- Copy your Public Key and Private Key

---

## How to Use the App

### 1. Automatic Meeting Follow-ups

When a Fathom meeting ends, the app automatically:

1. **Sends you a DM** with meeting summary
2. **Shows action buttons**:
   - **Add Note to Crono**: Save meeting notes to the contact's account
   - **Create Task**: Create a follow-up task in Crono
   - **View Deals**: See deals associated with the account
   - **Generate Email**: Create a follow-up email draft

#### Example Flow:

```
📹 Fathom Meeting Recording Ready
Meeting: Customer Discovery Call with John Smith
Duration: 45 minutes
Participants: John Smith (john@company.com), Sarah Lee

[Add Note to Crono] [Create Task] [View Deals] [Generate Email]
```

---

### 2. Manual Commands

#### `/crono-search` - Search Contacts

Search for contacts or companies in your Crono CRM:

```
/crono-search Acme Corp
```

Results show:
- Contact name
- Company
- Email
- Actions: Add Note, Create Task, View Deals

---

#### `/crono-add-note` - Add Note Manually

Create a note on a Crono account:

```
/crono-add-note
```

A modal appears where you can:
1. Search for a contact/company
2. Write your note
3. Submit

---

#### `/crono-add-task` - Create Task

Create a task in Crono:

```
/crono-add-task
```

Fill in:
- **Contact**: Search and select
- **Task Title**: What needs to be done
- **Due Date**: When it's due
- **Time**: What time (with time picker)
- **Priority**: Low, Medium, High
- **Description**: Additional details

---

#### `/crono-settings` - Configure Settings

Adjust your preferences:

```
/crono-settings
```

Options:
- **Default Task Priority**: Set default priority for tasks
- **AI Model Preference**: Choose between Claude or Gemini
- **Email Template Style**: Professional, friendly, or formal

---

### 3. Interactive Actions

#### Add Note to Crono

When you click **"Add Note to Crono"**:

1. Modal opens with meeting summary pre-filled
2. Contact is automatically detected from meeting participants
3. You can edit the note
4. Click **"Save Note"** to add to Crono

The note includes:
- Meeting title
- Tech stack discussed
- Pain points identified
- Impact of pain
- Next steps
- Roadblocks
- Link to Fathom recording

---

#### Create Task

When you click **"Create Task"**:

1. Modal opens with task creation form
2. **Contact field is pre-filled** with meeting participant
3. **Meeting title is suggested** as task title
4. Select due date with date picker
5. Select time with time picker
6. Choose priority
7. Add description
8. Click **"Create Task"**

Task is created in Crono CRM and linked to the contact.

---

#### View Deals

When you click **"View Deals"**:

1. Shows open deals for the contact's account
2. Filters out closed deals (Closed Won/Lost)
3. Displays most recent deal with:
   - Deal name
   - Amount
   - Stage
   - Close date
4. You can edit amount and stage
5. Click **"Update Deal"** to save changes

---

#### Generate Email

When you click **"Generate Email"**:

1. AI analyzes the meeting transcript
2. Generates a follow-up email in the meeting's language
3. Email includes:
   - Subject line
   - Brief thank you
   - Key discussion points
   - Next steps
   - Professional closing
4. Copy the email and paste into Gmail or your email client

**Note**: Email is formatted in HTML for easy pasting.

---

## Features Summary

### Automatic Features

✅ **Auto-detect meeting participants** from Fathom
✅ **Search Crono for matching contacts** by email
✅ **Generate meeting summaries** with AI
✅ **Pre-fill forms** with meeting context
✅ **Multi-language support** (emails in meeting language)

### CRM Integration

✅ **Add notes** to Crono accounts
✅ **Create tasks** with due dates and times
✅ **View and edit deals**
✅ **Search contacts** and companies
✅ **Link activities** to correct accounts

### AI Features

✅ **Meeting summaries** with key points
✅ **Follow-up email generation**
✅ **Context-aware suggestions**
✅ **Fallback support** (Claude → Gemini)

---

## Troubleshooting

### "Connection Failed" when connecting Crono

**Problem**: Error when running `/crono-connect`

**Solutions**:
1. Check your Crono API keys are correct
2. Verify keys have the right permissions in Crono
3. Try regenerating keys in Crono settings
4. Make sure you're using Public Key and Private Key (not other credentials)

---

### "No contact found" after meeting

**Problem**: App can't find participant in Crono

**Solutions**:
1. Check if the contact exists in Crono
2. Verify email address matches exactly
3. Manually search with `/crono-search` and add note
4. Add contact to Crono first, then retry

---

### Task modal doesn't open

**Problem**: Nothing happens when clicking "Create Task"

**Solutions**:
1. Check app logs for errors
2. Verify Slack app has correct permissions
3. Try restarting the Slack app
4. Check interaction URL is correct in Slack app settings

---

### AI email generation fails

**Problem**: Email generation returns error

**Solutions**:
1. Check `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` is set
2. Verify API key has credits/quota
3. Check API key permissions
4. Try the other AI service if one fails

---

### Webhook not triggering

**Problem**: No DM after Fathom meeting

**Solutions**:
1. Verify Fathom webhook URL is correct: `https://your-app-url.com/fathom/webhook`
2. Check webhook is enabled in Fathom settings
3. Test webhook manually in Fathom
4. Check app logs for incoming webhook requests
5. Ensure app is deployed and running

---

## Best Practices

### For Administrators

1. **Test with a sample meeting** before rolling out
2. **Document your Crono account structure** (custom fields, stages)
3. **Set up monitoring** for webhook failures
4. **Rotate API keys** periodically for security
5. **Train users** on the onboarding flow

### For Users

1. **Connect Crono immediately** after installation
2. **Review AI-generated content** before saving
3. **Use consistent email addresses** in Fathom and Crono
4. **Set realistic due dates** for tasks
5. **Add context to notes** beyond what's auto-generated

---

## Support

For issues or questions:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review app logs in your deployment platform
3. Contact your workspace administrator
4. Check Slack API documentation: [https://api.slack.com/docs](https://api.slack.com/docs)

---

## Security Notes

⚠️ **Important Security Considerations**:

1. **Never share your `.env` file** - it contains sensitive keys
2. **Use environment variables** in production (never hardcode keys)
3. **Rotate API keys** if compromised
4. **Limit API key permissions** to minimum required
5. **Use HTTPS** for all webhook URLs
6. **Keep dependencies updated** for security patches

---

## Quick Reference

### Slash Commands

| Command | Description |
|---------|-------------|
| `/crono-connect` | Connect your Crono account |
| `/crono-search <query>` | Search contacts/companies |
| `/crono-add-note` | Manually add a note |
| `/crono-add-task` | Manually create a task |
| `/crono-settings` | Configure preferences |

### Action Buttons

- **Add Note to Crono**: Save meeting notes
- **Create Task**: Create follow-up task
- **View Deals**: See and edit deals
- **Generate Email**: Create follow-up email

---

**Version**: 1.0
**Last Updated**: December 2024
**Maintained by**: Lorenzo & Team
