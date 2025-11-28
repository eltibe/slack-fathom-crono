#!/usr/bin/env python3
"""
Interactive Slack Setup Script

Guides you through setting up Slack integration step by step.
"""

import os
import sys
from dotenv import load_dotenv, set_key

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*80}{Colors.ENDC}\n")

def print_step(number, text):
    print(f"\n{Colors.BOLD}{Colors.CYAN}📍 STEP {number}: {text}{Colors.ENDC}\n")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")

def wait_for_user():
    input(f"\n{Colors.YELLOW}Press Enter when ready to continue...{Colors.ENDC}")

def get_input(prompt, required=True):
    while True:
        value = input(f"{Colors.CYAN}{prompt}{Colors.ENDC}").strip()
        if value or not required:
            return value
        print_warning("This field is required. Please enter a value.")

def main():
    print_header("🚀 SLACK INTEGRATION SETUP")

    print("""
This script will guide you through setting up Slack integration for the
Meeting Follow-up Tool. You'll create a Slack App and configure webhooks.

The setup takes about 10-15 minutes.
""")

    ready = input(f"{Colors.CYAN}Ready to start? (yes/no): {Colors.ENDC}").lower().strip()
    if ready not in ['yes', 'y', 'si', 'sì']:
        print("Setup cancelled.")
        sys.exit(0)

    # ========================================================================
    # STEP 1: Create Slack App
    # ========================================================================
    print_step(1, "Create Slack App")

    print("""
1. Open your browser and go to: https://api.slack.com/apps
2. Click the GREEN button "Create New App"
3. Choose "From scratch"
4. Enter these details:
   - App Name: "Meeting Follow-up Bot"
   - Pick a workspace: Select your Crono workspace
5. Click "Create App"
""")

    wait_for_user()
    print_success("Slack App created!")

    # ========================================================================
    # STEP 2: Configure Bot Token Scopes
    # ========================================================================
    print_step(2, "Configure Bot Permissions")

    print("""
1. In the left sidebar, click "OAuth & Permissions"
2. Scroll down to "Scopes" section
3. Under "Bot Token Scopes", click "Add an OAuth Scope"
4. Add these scopes one by one:

   ✓ chat:write          (Send messages)
   ✓ chat:write.public   (Write in public channels)
   ✓ channels:read       (View channels)
   ✓ im:write           (Send direct messages)

5. You should see all 4 scopes listed
""")

    wait_for_user()
    print_success("Bot scopes configured!")

    # ========================================================================
    # STEP 3: Install App to Workspace
    # ========================================================================
    print_step(3, "Install App to Workspace")

    print("""
1. Scroll to the TOP of the "OAuth & Permissions" page
2. Click the GREEN button "Install to Workspace"
3. Review the permissions
4. Click "Allow"
5. You'll see a "Bot User OAuth Token" starting with xoxb-
6. Click the "Copy" button to copy the token
""")

    print_info("Keep this page open! You'll need it in the next step.")
    wait_for_user()

    # Get Bot Token
    print("\n" + "="*80)
    bot_token = get_input("Paste your Bot User OAuth Token (starts with xoxb-): ", required=True)

    if not bot_token.startswith('xoxb-'):
        print_warning("Token doesn't start with 'xoxb-'. Double check you copied the right token.")
        proceed = get_input("Proceed anyway? (yes/no): ")
        if proceed.lower() not in ['yes', 'y']:
            print("Setup cancelled. Please copy the correct token and run again.")
            sys.exit(1)

    print_success("Bot token saved!")

    # ========================================================================
    # STEP 4: Get Signing Secret
    # ========================================================================
    print_step(4, "Get Signing Secret")

    print("""
1. In the left sidebar, click "Basic Information"
2. Scroll down to "App Credentials" section
3. You'll see "Signing Secret"
4. Click "Show" and then copy the secret
""")

    wait_for_user()

    signing_secret = get_input("Paste your Signing Secret: ", required=True)
    print_success("Signing secret saved!")

    # ========================================================================
    # STEP 5: Choose Slack Channel
    # ========================================================================
    print_step(5, "Choose Slack Channel")

    print("""
Choose where you want to receive meeting follow-up messages.
Examples:
  - #sales (public channel)
  - #meetings
  - @lorenzo (direct message to yourself)
""")

    slack_channel = get_input("Enter channel name (with # or @): ", required=True)

    if not slack_channel.startswith('#') and not slack_channel.startswith('@'):
        print_warning("Channel should start with # (for channels) or @ (for DMs)")
        slack_channel = '#' + slack_channel
        print_info(f"Using: {slack_channel}")

    print_success(f"Channel set to: {slack_channel}")

    # ========================================================================
    # STEP 6: Save to .env file
    # ========================================================================
    print_step(6, "Save Configuration")

    env_file = '/Users/lorenzo/cazzeggio/.env'

    print(f"Saving configuration to {env_file}...")

    try:
        # Save to .env file
        set_key(env_file, 'SLACK_BOT_TOKEN', bot_token)
        set_key(env_file, 'SLACK_SIGNING_SECRET', signing_secret)
        set_key(env_file, 'SLACK_CHANNEL', slack_channel)

        print_success("Configuration saved to .env file!")
    except Exception as e:
        print_warning(f"Could not save to .env: {e}")
        print("\nManually add these lines to your .env file:")
        print(f"SLACK_BOT_TOKEN={bot_token}")
        print(f"SLACK_SIGNING_SECRET={signing_secret}")
        print(f"SLACK_CHANNEL={slack_channel}")

    # ========================================================================
    # STEP 7: Install ngrok (if needed)
    # ========================================================================
    print_step(7, "Setup ngrok (for webhooks)")

    print("""
Slack needs to send events to your local server. We use ngrok to expose
your local server to the internet.

Do you have ngrok installed?
""")

    has_ngrok = get_input("Do you have ngrok? (yes/no): ").lower()

    if has_ngrok in ['no', 'n']:
        print("""
To install ngrok:

Option 1 (Homebrew):
  brew install ngrok

Option 2 (Download):
  1. Go to https://ngrok.com/download
  2. Download for macOS
  3. Unzip and move to /usr/local/bin/

After installing, run: ngrok authtoken YOUR_TOKEN
(Sign up at https://ngrok.com/ to get your token)
""")
        wait_for_user()

    print_success("ngrok is ready!")

    # ========================================================================
    # STEP 8: Start webhook handler
    # ========================================================================
    print_step(8, "Start Webhook Handler")

    print("""
Now we need to start the webhook server that will receive Slack events.

In a NEW TERMINAL window, run:
    cd /Users/lorenzo/cazzeggio
    python slack_webhook_handler.py

Keep that terminal open!
""")

    wait_for_user()

    # ========================================================================
    # STEP 9: Start ngrok
    # ========================================================================
    print_step(9, "Start ngrok")

    print("""
In ANOTHER NEW TERMINAL window, run:
    ngrok http 3000

You'll see output like:
    Forwarding    https://abc123.ngrok.io -> http://localhost:3000

Copy the HTTPS URL (starts with https://)
""")

    wait_for_user()

    ngrok_url = get_input("Paste your ngrok HTTPS URL: ", required=True)

    if not ngrok_url.startswith('https://'):
        print_warning("URL should start with https://")
        if ngrok_url.startswith('http://'):
            ngrok_url = ngrok_url.replace('http://', 'https://')
            print_info(f"Using: {ngrok_url}")

    # Remove trailing slash if present
    ngrok_url = ngrok_url.rstrip('/')

    events_url = f"{ngrok_url}/slack/events"
    interactions_url = f"{ngrok_url}/slack/interactions"

    print(f"\n{Colors.BOLD}Your webhook URLs:{Colors.ENDC}")
    print(f"  Events: {Colors.GREEN}{events_url}{Colors.ENDC}")
    print(f"  Interactions: {Colors.GREEN}{interactions_url}{Colors.ENDC}")

    # ========================================================================
    # STEP 10: Configure Slack Event Subscriptions
    # ========================================================================
    print_step(10, "Configure Event Subscriptions")

    print(f"""
1. Go back to https://api.slack.com/apps
2. Select your "Meeting Follow-up Bot" app
3. In the left sidebar, click "Event Subscriptions"
4. Toggle "Enable Events" to ON
5. In "Request URL", paste:
   {events_url}
6. Wait for the URL to be verified (green checkmark)
7. Scroll down to "Subscribe to bot events"
8. Click "Add Bot User Event" and add these:
   ✓ message.channels
   ✓ message.groups
   ✓ message.im
9. Click "Save Changes" at the bottom
""")

    wait_for_user()
    print_success("Event subscriptions configured!")

    # ========================================================================
    # STEP 11: Configure Interactivity
    # ========================================================================
    print_step(11, "Configure Interactivity")

    print(f"""
1. In the left sidebar, click "Interactivity & Shortcuts"
2. Toggle "Interactivity" to ON
3. In "Request URL", paste:
   {interactions_url}
4. Click "Save Changes"
""")

    wait_for_user()
    print_success("Interactivity configured!")

    # ========================================================================
    # STEP 12: Invite bot to channel
    # ========================================================================
    print_step(12, "Invite Bot to Channel")

    print(f"""
1. Open Slack and go to the {slack_channel} channel
2. Type this command in the channel:
   /invite @Meeting Follow-up Bot
3. Press Enter

The bot should now be in the channel!
""")

    wait_for_user()
    print_success("Bot invited to channel!")

    # ========================================================================
    # FINAL: Test the integration
    # ========================================================================
    print_header("🎉 SETUP COMPLETE!")

    print(f"""
{Colors.GREEN}Congratulations! Your Slack integration is ready to use.{Colors.ENDC}

{Colors.BOLD}What's running:{Colors.ENDC}
  ✓ Webhook handler: http://localhost:3000
  ✓ ngrok tunnel: {ngrok_url}
  ✓ Slack bot: Listening in {slack_channel}

{Colors.BOLD}To test it:{Colors.ENDC}
  1. Make sure the webhook handler is still running
  2. Make sure ngrok is still running
  3. Run: python meeting_followup.py --slack

{Colors.BOLD}You should see:{Colors.ENDC}
  - A message in {slack_channel} with meeting details
  - Interactive buttons to select actions
  - A chat conversation to confirm

{Colors.BOLD}Important Notes:{Colors.ENDC}
  ⚠️  Keep the webhook handler running when using --slack mode
  ⚠️  Keep ngrok running (free URLs change on restart)
  ⚠️  If ngrok URL changes, update it in Slack App settings

{Colors.BOLD}Quick Reference:{Colors.ENDC}
  Start webhook:  python slack_webhook_handler.py
  Start ngrok:    ngrok http 3000
  Test command:   python meeting_followup.py --slack

{Colors.CYAN}Need help? Check SLACK_INTEGRATION_GUIDE.md{Colors.ENDC}
""")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Setup cancelled by user.{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}Error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
