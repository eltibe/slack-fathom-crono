
import os
import anthropic

# --- IMPORTANT ---
# Set your ANTHROPIC_API_KEY environment variable before running.
# You can get an API key from your Anthropic account settings.
#
# For example, in your terminal:
# export ANTHROPIC_API_KEY="YOUR_API_KEY"
# -----------------

try:
    # The Anthropic client automatically looks for the ANTHROPIC_API_KEY
    # environment variable.
    client = anthropic.Anthropic()
except Exception as e:
    print(f"Error initializing Anthropic client: {e}")
    print("Please ensure your ANTHROPIC_API_KEY is set correctly.")
    exit(1)

# Query the model
prompt = "Write a short story about a programmer who discovers a secret in the code of a vintage video game."

try:
    message = client.messages.create(
        model="claude-3-opus-20240229",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    # The response is a list of content blocks, we'll take the first one.
    if message.content:
        print(message.content[0].text)
    else:
        print("No response generated. Check your API key and network connection.")

except Exception as e:
    print(f"An error occurred: {e}")

