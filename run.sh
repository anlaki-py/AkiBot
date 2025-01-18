#!/bin/bash

# =============================================================================
# AkiBot Setup Script
# Version: 1.0.2
# Description: Installation and configuration script for AkiBot
# =============================================================================

# Clear any existing readonly variables if they exist
if [ -n "$BASH_VERSION" ]; then
    if [ -n "$(readonly -p | grep VERSION)" ]; then
        unset -f VERSION &>/dev/null
    fi
    if [ -n "$(readonly -p | grep CONFIG_DIR)" ]; then
        unset -f CONFIG_DIR &>/dev/null
    fi
    if [ -n "$(readonly -p | grep CONFIG_FILE)" ]; then
        unset -f CONFIG_FILE &>/dev/null
    fi
    if [ -n "$(readonly -p | grep LOG_DIR)" ]; then
        unset -f LOG_DIR &>/dev/null
    fi
    if [ -n "$(readonly -p | grep LOG_FILE)" ]; then
        unset -f LOG_FILE &>/dev/null
    fi
    if [ -n "$(readonly -p | grep REQUIRED_PYTHON_VERSION)" ]; then
        unset -f REQUIRED_PYTHON_VERSION &>/dev/null
    fi
    if [ -n "$(readonly -p | grep RED)" ]; then
        unset -f RED &>/dev/null
    fi
    if [ -n "$(readonly -p | grep GREEN)" ]; then
        unset -f GREEN &>/dev/null
    fi
    if [ -n "$(readonly -p | grep YELLOW)" ]; then
        unset -f YELLOW &>/dev/null
    fi
    if [ -n "$(readonly -p | grep NC)" ]; then
        unset -f NC &>/dev/null
    fi
fi

# Constants and Configuration
readonly VERSION="1.0.2"
readonly CONFIG_DIR="config"
readonly CONFIG_FILE="$CONFIG_DIR/config.json"
readonly LOG_DIR="logs"
readonly LOG_FILE="$LOG_DIR/setup.log"
readonly REQUIRED_PYTHON_VERSION="3.11"

# ANSI color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly NC='\033[0m' # No Color


# =============================================================================
# Utility Functions
# =============================================================================

log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} - $1" | tee -a "$LOG_FILE"
}

error() {
    log "${RED}ERROR: $1${NC}"
    # exit 1
}

warning() {
    log "${YELLOW}WARNING: $1${NC}"
}

success() {
    log "${GREEN}SUCCESS: $1${NC}"
}

print_akibot_logo() {
    echo -e "\e[38;5;93m █████╗ ██╗  ██╗██╗██████╗  ██████╗ ████████╗"
    echo -e "\e[38;5;98m██╔══██╗██║ ██╔╝██║██╔══██╗██╔═══██╗╚══██╔══╝"
    echo -e "\e[38;5;104m███████║█████╔╝ ██║██████╔╝██║   ██║   ██║   "
    echo -e "\e[38;5;105m██╔══██║██╔═██╗ ██║██╔══██╗██║   ██║   ██║   "
    echo -e "\e[38;5;111m██║  ██║██║  ██╗██║██████╔╝╚██████╔╝   ██║   "
    echo -e "\e[38;5;147m╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═════╝  ╚═════╝    ╚═╝   "
    echo -e "\e[0m"
}

# =============================================================================
# Setup Functions
# =============================================================================

check_dependencies() {
    log "Checking dependencies..."
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is not installed. Please install Python $REQUIRED_PYTHON_VERSION or later."
    fi
    
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if [ $(echo "$python_version < $REQUIRED_PYTHON_VERSION" | bc -l) -eq 1 ]; then
        error "Python $REQUIRED_PYTHON_VERSION or later is required. Found version $python_version"
    fi
    
    success "All dependencies satisfied"
}

setup_directories() {
    log "Setting up directories..."
    
    # Create necessary directories
    mkdir -p "$CONFIG_DIR" "$LOG_DIR" || error "Failed to create required directories"
    success "Directories created successfully"
}

create_config() {
    log "Creating configuration file..."
    
    if [ -f "$CONFIG_FILE" ]; then
        warning "Configuration file already exists. Skipping creation."
        return 0
    fi

    # Create the config.json file with the specified content
    cat > "$CONFIG_FILE" <<EOL
{
    "allowed_users": [
        "YOUR ACCOUNT ID HERE"
    ],
    "gemini_model": "gemini-2.0-flash-exp",
    "generation_config": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "max_output_tokens": 1024,
        "response_mime_type": "text/plain"
    },
    "safety_settings": [
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE"
        }
    ],
    "system_prompt_file": "system/default.txt"
}
EOL

    if [ $? -eq 0 ]; then
        success "Configuration file created successfully"
    else
        error "Failed to create configuration file"
    fi
}

run_main_application() {
    log "Starting AkiBot application..."
    
    if [ ! -f "main.py" ]; then
        error "main.py not found in the current directory"
    fi
    
    clear
    print_akibot_logo
    echo -e "AkiBot v${VERSION}"
    echo -e "Running main.py...\n"
    
    if python main.py; then
        success "Application completed successfully"
    else
        error "Application exited with an error"
    fi
}

cleanup() {
    log "Cleaning up and exiting..."
    echo -e "\nApplication terminated. Cleaning up..."
    # Add any cleanup tasks here
    # exit 0
}

# =============================================================================
# Main Script Execution
# =============================================================================

main() {
    # Set up error handling
    set -euo pipefail
    trap cleanup SIGINT SIGTERM

    # Clear screen and show logo
    clear
    print_akibot_logo
    
    # Initialize logging
    mkdir -p "$LOG_DIR"
    touch "$LOG_FILE"
    
    # Run setup steps
    check_dependencies
    setup_directories
    create_config
    
    # Prompt for main.py execution
    read -p "Run main.py? [Y/n]: " run_main
    
    case ${run_main,,} in
        "y"|"yes"|"")
            run_main_application
            ;;
        "n"|"no")
            log "User chose not to run main.py"
            echo "Exiting script."
            ;;
        *)
            error "Invalid input received: $run_main"
            ;;
    esac
}

# Execute main function
main "$@"

# #!/bin/bash
# clear

# print_akibot_logo() {
    # echo -e "\e[38;5;93m █████╗ ██╗  ██╗██╗██████╗  ██████╗ ████████╗"
    # echo -e "\e[38;5;98m██╔══██╗██║ ██╔╝██║██╔══██╗██╔═══██╗╚══██╔══╝"
    # echo -e "\e[38;5;104m███████║█████╔╝ ██║██████╔╝██║   ██║   ██║   "
    # echo -e "\e[38;5;105m██╔══██║██╔═██╗ ██║██╔══██╗██║   ██║   ██║   "
    # echo -e "\e[38;5;111m██║  ██║██║  ██╗██║██████╔╝╚██████╔╝   ██║   "
    # echo -e "\e[38;5;147m╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═════╝  ╚═════╝    ╚═╝   "
    # echo -e "\e[0m"
# }

# print_akibot_logo

# # Define the directory and file path
# CONFIG_DIR="config"
# CONFIG_FILE="$CONFIG_DIR/config.json"

# # Function to handle Ctrl+C
# cleanup() {
    # echo -e "\nApplication terminated. Exiting script."
    # exit 0
# }

# # Trap Ctrl+C and call cleanup function
# trap cleanup SIGINT

# # Check if the configuration file exists
# if [ ! -f "$CONFIG_FILE" ]; then
    # # Create the directory if it doesn't exist
    # mkdir -p "$CONFIG_DIR"

    # # Create the config.json file with the specified content
    # cat > "$CONFIG_FILE" <<EOL
# {
    # "allowed_users": [
        # "YOUR ACCOUNT ID HERE"
    # ],
    # "gemini_model": "gemini-2.0-flash-exp",
    # "generation_config": {
        # "temperature": 0.7,
        # "top_p": 0.9,
        # "top_k": 40,
        # "max_output_tokens": 1024,
        # "response_mime_type": "text/plain"
    # },
    # "safety_settings": [
        # {
            # "category": "HARM_CATEGORY_HATE_SPEECH",
            # "threshold": "BLOCK_NONE"
        # },
        # {
            # "category": "HARM_CATEGORY_HARASSMENT",
            # "threshold": "BLOCK_NONE"
        # },
        # {
            # "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            # "threshold": "BLOCK_NONE"
        # },
        # {
            # "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            # "threshold": "BLOCK_NONE"
        # }
    # ],
    # "system_prompt_file": "system/default.txt"
# }
# EOL

    # echo "Configuration file created at $CONFIG_FILE"
# else
    # echo "Configuration file already exists at $CONFIG_FILE"
# fi

# # Ask if the user wants to run main.py
# read -p "Run main.py? [Y/n]: " run_main

# if [[ "$run_main" == "y" || "$run_main" == "yes" || -z "$run_main" ]]; then
    # # Run the main.py application
    # clear
    # print_akibot_logo
    # echo -e "AkiBot v1.0.2"
    # echo -e "Running main.py...\n"
    # python main.py
    # clear

    # # If the script reaches this point, notify the user
    # echo "Script completed. Exiting."
# elif [[ "$run_main" == "n" || "$run_main" == "no" ]]; then
    # echo "Exiting script."
    # clear
    # # exit 0
# else
    # echo "Invalid input. Exiting script."
    # clear
    # exit 1
# fi
