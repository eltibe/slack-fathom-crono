#!/usr/bin/env python
import google.generativeai as genai
import os
import sys

# This configures the library to use the API key from your environment variables.
# Make sure to set it in your shell before running the script, like this:
# export GOOGLE_API_KEY='YOUR_API_KEY'
try:
    # It's safer to get the key from an environment variable.
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: The GOOGLE_API_KEY environment variable is not set.", file=sys.stderr)
        print("Please set it by running: export GOOGLE_API_KEY='YOUR_API_KEY'", file=sys.stderr)
        sys.exit(1)

    genai.configure(api_key=api_key)

    print("Available models that support 'generateContent':")
    for m in genai.list_models():
      if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")

except Exception as e:
    print(f"An error occurred: {e}", file=sys.stderr)
    print("\nPlease ensure you have set the GOOGLE_API_KEY environment variable correctly.", file=sys.stderr)
    sys.exit(1)
