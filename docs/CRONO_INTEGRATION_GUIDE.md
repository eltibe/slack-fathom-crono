# 🎯 Crono CRM Integration Guide

## Overview

The Crono integration automatically creates structured meeting notes in your Crono CRM with sales-focused insights extracted from meeting transcripts.

## ✨ Features

### Automatic Sales Data Extraction

The AI analyzes your meeting transcript and extracts:

1. **💻 Tech Stack** - Technologies, tools, and platforms the customer uses
2. **⚠️ Pain Points** - Problems and challenges mentioned
3. **📊 Impact of Pain** - Quantified business impact (time, money, opportunities)
4. **✅ Next Steps** - Agreed actions with responsibilities and dates
5. **🚧 Roadblocks** - Potential obstacles (budget, approvals, concerns)

### Smart Company Matching

The system uses a **4-strategy matching approach** to find the right company:

**Strategy 0: Local Account Mappings** (Fastest) 🚀
- Checks `account_mappings.json` for pre-configured domain → company mappings
- Bypasses API limits (200 accounts max per request)
- Supports both objectId and company names
- **How it works:**
  - If mapped value contains `_` → Treats as objectId and calls GET `/v1/Accounts/{id}`
  - Otherwise → Treats as company name and uses POST `/api/v1/Accounts/search`
- **Example mappings:**
  ```json
  {
    "domain_to_account": {
      "neuronup.com": "NeuronUP",
      "insightrevenue.com": "Insight Revenue"
    }
  }
  ```
- **Why use company names?** GET `/v1/Accounts/{id}` returns 404 for some accounts, but POST search by name works reliably

**Strategy 1: Website Field Domain Match** ⭐
- Fetches recent 200 Crono accounts via GET `/v1/Accounts?limit=200`
- Extracts domain from external participant email (e.g., `john@acmecorp.com` → `acmecorp.com`)
- Compares email domain with account website field
- Example: `sarah@techstartup.io` email matches Crono account with website `https://techstartup.io`
- Handles all formats: `techstartup.io`, `www.techstartup.io`, `https://techstartup.io`
- **Limitation:** Only searches first 200 accounts

**Strategy 2: POST Search by Company Name** (Most Accurate)
- Uses POST `/api/v1/Accounts/search` with exact company name
- Works for accounts beyond the 200-account limit
- Payload: `{"name": "ExactCompanyName"}`
- More reliable than GET search
- **Important:** Endpoint uses different base URL (`/api/v1` instead of `/v1`)

**Strategy 3: GET Search by Company Name** (Fallback)
- If POST search fails, tries GET `/v1/Accounts?search=name`
- Less accurate but provides additional fallback
- Useful for partial name matches

### 📋 Adding Custom Account Mappings

For accounts that are hard to find (beyond 200-account limit or with complex names):

1. **Find the exact company name in Crono:**
   ```bash
   python3 test_find_insightrevenue.py  # Use as template
   ```

2. **Add to `account_mappings.json`:**
   ```json
   {
     "domain_to_account": {
       "companywebsite.com": "Exact Company Name"
     },
     "comments": {
       "companywebsite.com": "Description for reference"
     }
   }
   ```

3. **Restart webhook server** (if using Slack integration):
   ```bash
   lsof -ti:3000 | xargs kill
   python3 slack_webhook_handler.py > followup_webhook.log 2>&1 &
   ```

**Pro tip:** Always use exact company names as they appear in Crono for best results.

## 🚀 Setup

### 1. Get Crono API Credentials

1. Log in to your Crono account
2. Go to Settings → API Keys
3. Generate a new API key
4. Copy the API key

### 2. Configure Environment Variables

Add to your `.env` file:

```bash
# Crono CRM Configuration
CRONO_API_KEY=your_api_key_here
CRONO_API_URL=https://dev.api.crono.one/cronoapi-e3b0madc44269/v1
```

### 3. Test the Integration

Test the Crono client:

```bash
python3 modules/crono_client.py
```

This will:
- Search for test accounts
- Attempt to create a sample meeting note
- Show you if the API endpoints are working

## 📱 Using the Menu Bar App

### Flow

1. **Click** the 🚀 icon in your menu bar
2. **Select** "📧 Generate Follow-up Email"
3. **Choose** which meeting to process from today's list
4. **Decide** if you want to create a Crono note:
   - **Yes** → Creates email draft + calendar event + Crono note
   - **No** → Creates only email draft + calendar event

### What Happens

When you choose "Yes, create note":

1. ✅ Fetches the meeting transcript from Fathom
2. 🤖 Generates follow-up email with Claude
3. 📧 Creates Gmail draft
4. 📅 Creates Google Calendar follow-up event (if discussed)
5. 🧠 **Extracts sales insights** from transcript
6. 🔍 **Finds company** in Crono CRM
7. 📝 **Creates meeting note** with structured data

### Example Crono Note

```
🎯 Meeting Summary: Discovery Call with Acme Corp

💻 Tech Stack
HubSpot CRM, LinkedIn for prospecting, Node.js backend,
React frontend, PostgreSQL database

⚠️ Pain Points
Manual prospecting taking 10 hours/week per SDR,
only generating 15 qualified meetings/month vs 30 needed

📊 Impact of Pain
Missing Q1 targets, each missed meeting = €50K lost pipeline,
10 hours/week of SDR time consumed

✅ Next Steps
1. Send security documentation
2. Technical deep-dive with CTO - Wednesday 3pm
3. Trial start Monday (pending CTO approval)

🚧 Roadblocks
Requires CTO approval, concerns about data quality
and integration complexity

---
🎥 View Full Meeting Recording

---
🤖 Generated by Crono AI Meeting Assistant
```

## 🛠️ Troubleshooting

### "Could not find company in Crono"

**Problem:** The script can't automatically match the company.

**Why this happens:**
- Company doesn't exist in Crono yet (new prospect)
- Domain in Crono doesn't match email domain (e.g., Gmail address for personal email)
- Company name in Crono is very different from domain

**Solutions:**

**Before the meeting:**
1. Create the company account in Crono first
2. **Fill in the Website field** (crucial for auto-matching!) ⭐
3. Examples:
   - Website: `https://acmecorp.com` → Matches `john@acmecorp.com`
   - Website: `www.techstartup.io` → Matches `sarah@techstartup.io`
   - Website: `example.com` → Matches `contact@example.com`

**After the meeting (if not found):**
1. The sales insights are still extracted and shown in terminal
2. Manually create the account in Crono
3. Copy/paste the extracted insights from terminal output
4. Or re-run the script after creating the account

**Best Practice:**
- ✅ Always ensure external participants use **company email addresses** (not Gmail/personal)
- ✅ Fill in the **Website field** for all Crono accounts
- ✅ Website field accepts any format: `example.com`, `www.example.com`, or `https://example.com`
- ✅ The system automatically normalizes and compares domains

**Example Setup in Crono:**
```
Company: Acme Corporation
Website: https://www.acmecorp.com
```
**Auto-matches these emails:**
- john@acmecorp.com ✅
- sarah.smith@acmecorp.com ✅
- team@acmecorp.com ✅

### "Could not create note - check Crono API endpoint"

**Problem:** The API endpoint for creating notes is not correct.

**Solutions:**
1. Check the Crono API documentation for the correct endpoint
2. Update `modules/crono_client.py` in the `create_note()` method
3. Try different endpoints:
   - `/Account/{id}/notes`
   - `/Account/{id}/activities`
   - `/Activity`
   - `/Note`

### "Error: CRONO_API_KEY is required"

**Problem:** API key not configured.

**Solution:**
```bash
# Add to .env file
CRONO_API_KEY=your_actual_api_key_here
```

## 🎨 Customization

### Change Sales Data Fields

Edit `modules/sales_summary_generator.py`:

```python
# Add new fields to extract
RESPONSE FORMAT:
{
    "tech_stack": "...",
    "pain_points": "...",
    "impact": "...",
    "next_steps": "...",
    "roadblocks": "...",
    "budget": "...",           # NEW
    "decision_timeline": "..." # NEW
}
```

### Change Note Format

Edit `modules/crono_client.py` in the `create_meeting_summary()` method:

```python
html_content = f"""
<h3>Your Custom Section</h3>
<p>{summary_data.get('your_field')}</p>
"""
```

## 📊 What Makes a Good Sales Note?

### Good Examples

✅ **Tech Stack:** "Using HubSpot Pro, Salesforce for enterprise deals, Intercom for support, Segment for analytics"

✅ **Pain Points:** "Lead enrichment taking 30 min per lead, 60% bounce rate on cold emails, no integration between marketing and sales tools"

✅ **Impact:** "Missing 40% of Q3 pipeline target (€120K), CMO spending 5h/week on manual reporting, sales cycle 45 days vs industry avg 30 days"

✅ **Next Steps:** "1. Lorenzo sends ROI calculator - Friday, 2. Demo with full sales team - Tuesday 2pm, 3. Pilot program starts March 1st - 3 SDRs"

✅ **Roadblocks:** "Budget approval needed from CFO (Q1 budget frozen), requires IT security audit (2-3 weeks), competing with 2 other vendors"

### Less Useful

❌ **Vague:** "They use some CRM"
❌ **Generic:** "They have problems with lead generation"
❌ **Unquantified:** "It's affecting their business"
❌ **No timeline:** "We'll follow up later"
❌ **No specifics:** "Some concerns were raised"

## 💡 Best Practices

### During the Meeting

**Mention specifics:**
- Actual numbers (hours, revenue, users)
- Specific tools and versions
- Exact dates for next steps
- Names and titles of stakeholders
- Concrete objections and concerns

**Example:**
> "So you're spending about 10 hours per week on this?"
> "Your CTO Sarah mentioned the budget is around €50K for this quarter?"
> "Let's schedule the technical deep-dive for next Wednesday at 3pm?"

### After the Meeting

1. Run the automation immediately while details are fresh
2. Review the extracted data in the terminal output
3. Add any missing context manually in Crono if needed
4. Update next steps in Crono as they progress

## 🔗 Integration Points

The Crono integration works seamlessly with:

- ✅ **Fathom** - Source of meeting transcripts
- ✅ **Claude AI** - Extracts sales insights
- ✅ **Gmail** - Creates follow-up email draft
- ✅ **Google Calendar** - Creates follow-up meeting
- ✅ **Crono CRM** - Stores structured sales notes

All in one click! 🚀

## 🔐 Security Notes

- API keys are stored locally in `.env` file (never committed to git)
- All API calls use HTTPS encryption
- No meeting data is stored on external servers
- Crono notes are only created when you explicitly choose to

## 📈 Next Steps

Optional enhancements you could add:

- [ ] Automatic deal value estimation based on company size
- [ ] Sentiment analysis (hot/warm/cold lead)
- [ ] Competitive intelligence extraction
- [ ] Automatic task creation in Crono for next steps
- [ ] Integration with Slack for notifications
- [ ] Weekly sales insights summary report
