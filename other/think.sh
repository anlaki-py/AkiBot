#!/bin/bash

# Set your API key as an environment variable or directly here (not recommended for security)
# GEMINI_API_KEY="YOUR_GEMINI_API_KEY"

# Check if the API key is set
if [ -z "$GEMINI_API_KEY" ]; then
  echo "Error: GEMINI_API_KEY environment variable is not set."
  exit 1
fi

# Get user input
read -r -p "Enter your query: " user_input

# Construct the JSON payload with the user input
payload=$(cat <<-END
{
  "contents": [
    {
      "role": "user",
      "parts": [
        {
          "text": "$user_input"
        }
      ]
    }
  ],
  "generationConfig": {
    "temperature": 0.65,
    "topK": 64,
    "topP": 0.95,
    "maxOutputTokens": 8192,
    "responseMimeType": "text/plain"
  }
}
END
)

# Execute the curl command
response=$(curl \
  -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-thinking-exp-1219:generateContent?key=${GEMINI_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d "$payload")

# Output the response
echo "$response"