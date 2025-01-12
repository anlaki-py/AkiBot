#!/bin/bash

# Define the directory and file path
CONFIG_DIR="config"
CONFIG_FILE="$CONFIG_DIR/config.json"

# Function to handle Ctrl+C
cleanup() {
    echo -e "\nApplication terminated. Exiting script."
    exit 0
}

# Trap Ctrl+C and call cleanup function
trap cleanup SIGINT

# Check if the configuration file exists
if [ ! -f "$CONFIG_FILE" ]; then
    # Create the directory if it doesn't exist
    mkdir -p "$CONFIG_DIR"

    # Create the config.json file with the specified content
    cat > "$CONFIG_FILE" <<EOL
{
    "allowed_users": [
        "0123456789",
        "0987654321"
    ],
    "gemini_model": "gemini-2.0-flash-exp",
    "generation_config": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": 1024,
        "response_mime_type": "text/plain"
    },
    "safety_settings": {
        "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
        "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
        "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE"
    },
    "system_prompt_file": "system/default.txt"
}
EOL

    echo "Configuration file created at $CONFIG_FILE"
else
    echo "Configuration file already exists at $CONFIG_FILE"
fi

# Run the main.py application
echo "Running main.py..."
python main.py

# If the script reaches this point, notify the user
echo "Script completed. Exiting."
