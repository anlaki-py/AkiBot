import os

def clear_screen():
    # Check the operating system and execute the appropriate command
    if os.name == 'nt':  # For Windows
        os.system('cls')
    else:  # For macOS, Linux, and other Unix-like systems
        os.system('clear')

def print_akibot_logo():
    print("")
    print("\033[38;5;93m █████╗ ██╗  ██╗██╗██████╗  ██████╗ ████████╗")
    print("\033[38;5;98m██╔══██╗██║ ██╔╝██║██╔══██╗██╔═══██╗╚══██╔══╝")
    print("\033[38;5;104m███████║█████╔╝ ██║██████╔╝██║   ██║   ██║   ")
    print("\033[38;5;105m██╔══██║██╔═██╗ ██║██╔══██╗██║   ██║   ██║   ")
    print("\033[38;5;111m██║  ██║██║  ██╗██║██████╔╝╚██████╔╝   ██║   ")
    print("\033[38;5;147m╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═════╝  ╚═════╝    ╚═╝   ")
    print("\033[0m")

