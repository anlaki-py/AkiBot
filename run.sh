#!/bin/bash

# =============================================================================
# AkiBot Setup Script
# Version: 1.1.5
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
readonly VERSION="1.0.8"
readonly CONFIG_DIR="config"
readonly CONFIG_FILE="$CONFIG_DIR/config.json"
readonly LOG_DIR="logs"
readonly LOG_FILE="$LOG_DIR/setup.log"
readonly REQUIRED_PYTHON_VERSION="3.11"
readonly MAIN_PYTHON_FILE="main.py"

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

    # Collect user IDs
    echo -e "${YELLOW}User ID Configuration:${NC}"
    echo -e "• Enter user IDs one by one"
    echo -e "• Press Enter with no input to finish"
    echo -e "• If you leave the first entry empty, it will default to 'YOUR_ACCOUNT_ID'\n"

    user_ids=()
    first_entry=true
    
    while true; do
        if [ "$first_entry" = true ]; then
            read -p "Enter first user ID (Empty for default placeholder): " user_id
            if [ -z "$user_id" ]; then
                user_ids+=("\"YOUR_ACCOUNT_ID\"")
                echo -e "${YELLOW}Using default placeholder 'YOUR_ACCOUNT_ID'${NC}"
                break
            fi
        else
            read -p "Enter additional user ID (Empty to finish): " user_id
            if [ -z "$user_id" ]; then
                break
            fi
        fi

        # Validate user ID format
        if [[ ! "$user_id" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
            warning "Invalid user ID format. Use only letters, numbers, dots, underscores, and hyphens."
            continue
        fi

        user_ids+=("\"$user_id\"")
        first_entry=false
    done

    # Join user IDs with commas
    allowed_users=$(printf "%s," "${user_ids[@]}" | sed 's/,$//')

    echo -e "\n${YELLOW}Creating config file with ${#user_ids[@]} user(s)...${NC}"

    # Create the config.json file with the specified content
    if ! cat > "$CONFIG_FILE" <<EOL
{
    "allowed_users": [
        ${allowed_users}
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
    "system_prompt_file": "system/telegramV4.txt"
}
EOL
    then
        error "Failed to write configuration file"
        return 1
    fi

    # Verify the JSON syntax
    if command -v python3 >/dev/null 2>&1; then
        if ! python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
            error "Generated config file contains invalid JSON"
            rm -f "$CONFIG_FILE"
            return 1
        fi
    fi

    success "Configuration file created successfully with ${#user_ids[@]} user(s)"
    if [[ "${user_ids[0]}" == "\"YOUR_ACCOUNT_ID\"" ]]; then
        echo -e "${YELLOW}Remember to replace 'YOUR_ACCOUNT_ID' in $CONFIG_FILE with your actual user ID${NC}"
    fi
}

run_main_application() {
    log "Starting AkiBot application..."
    
    if [ ! -f "${MAIN_PYTHON_FILE}" ]; then
        error "${MAIN_PYTHON_FILE} not found in the current directory"
    fi
    
    clear
    print_akibot_logo
    echo -e "AkiBot v${VERSION}"
    echo -e "Running ${MAIN_PYTHON_FILE}...\n"
    
    if python ${MAIN_PYTHON_FILE}; then
        success "Application completed successfully"
    else
        error "Application exited with an error"
    fi
}

cleanup() {
    log "Cleaning up and exiting..."
    echo -e "\nApplication terminated. Cleaning up..."
    # Add any cleanup tasks here (nothing to clean for now)
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
    
    # Prompt for ${MAIN_PYTHON_FILE} execution
    read -p "Run ${MAIN_PYTHON_FILE}? [Y/n]: " run_main
    
    case ${run_main,,} in
        "y"|"yes"|"")
            run_main_application
            ;;
        "n"|"no")
            log "User chose not to run ${MAIN_PYTHON_FILE}"
            echo "Exiting script."
            ;;
        *)
            error "Invalid input received: $run_main"
            ;;
    esac
}

# Execute main function
main "$@"
