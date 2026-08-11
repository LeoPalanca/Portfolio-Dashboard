#!/bin/bash

# Portfolio Dashboard Control Script
# Usage: ./dashboard.sh [start|stop|restart|status|logs|clean]

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${APP_DIR}/app.pid"
LOG_FILE="${APP_DIR}/app.log"
PORT=8050

# Setup colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Determine Python Binary
if [ -f "/opt/anaconda3/bin/python3" ]; then
    PYTHON_BIN="/opt/anaconda3/bin/python3"
else
    PYTHON_BIN="python3"
fi

show_help() {
    echo -e "${BLUE}Portfolio Dashboard Helper${NC}"
    echo -e "Usage: $0 {start|stop|restart|redeploy|status|logs|clean}"
    echo
    echo -e "  ${GREEN}start${NC}     - Start the dashboard server in the background"
    echo -e "  ${RED}stop${NC}      - Stop the dashboard server"
    echo -e "  ${YELLOW}restart${NC}   - Restart the dashboard server (same as redeploy)"
    echo -e "  ${YELLOW}redeploy${NC}  - Restart the dashboard server"
    echo -e "  ${CYAN}status${NC}    - Check if the dashboard server is running"
    echo -e "  ${BLUE}logs${NC}      - Tail the server logs"
    echo -e "  ${RED}clean${NC}     - Clean cache files (.price_cache.json, etc.)"
    echo
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        echo "$(cat "$PID_FILE")"
    else
        # Fallback: find process running app.py on port 8050
        local pid
        pid=$(lsof -t -i :$PORT -sTCP:LISTEN 2>/dev/null)
        if [ -n "$pid" ]; then
            echo "$pid"
        else
            # Try finding python process running app.py
            pid=$(pgrep -f "python.*app.py" | head -n 1)
            if [ -n "$pid" ]; then
                echo "$pid"
            fi
        fi
    fi
}

start_app() {
    echo -e "${BLUE}[*] Starting Portfolio Dashboard...${NC}"
    local pid
    pid=$(get_pid)
    
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo -e "${YELLOW}[!] Server is already running (PID: $pid) on http://127.0.0.1:$PORT${NC}"
        return 0
    fi
    
    # Start the server and redirect logs
    nohup "$PYTHON_BIN" "${APP_DIR}/app.py" > "$LOG_FILE" 2>&1 &
    local new_pid=$!
    
    # Wait a moment to check if it started successfully
    sleep 1.5
    if kill -0 "$new_pid" 2>/dev/null; then
        echo "$new_pid" > "$PID_FILE"
        echo -e "${GREEN}[+] Dashboard started successfully!${NC}"
        echo -e "${GREEN}[+] PID: $new_pid${NC}"
        echo -e "${GREEN}[+] URL: http://127.0.0.1:$PORT${NC}"
        echo -e "${GREEN}[+] Logs: tail -f app.log${NC}"
    else
        echo -e "${RED}[-] Failed to start server. Check logs for details:${NC}"
        tail -n 10 "$LOG_FILE"
        return 1
    fi
}

stop_app() {
    echo -e "${BLUE}[*] Stopping Portfolio Dashboard...${NC}"
    local pid
    pid=$(get_pid)
    
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        echo -e "${YELLOW}[!] No running server found.${NC}"
        [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
        return 0
    fi
    
    kill "$pid"
    # Wait for it to exit
    for i in {1..5}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    
    # Force kill if still running
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${YELLOW}[!] Server did not exit gracefully, force killing (SIGKILL)...${NC}"
        kill -9 "$pid"
    fi
    
    rm -f "$PID_FILE"
    echo -e "${GREEN}[+] Server stopped successfully.${NC}"
}

status_interactive() {
    local pid
    pid=$(get_pid)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo -e "Status: ${GREEN}RUNNING${NC} (PID: $pid, URL: http://127.0.0.1:$PORT)"
    else
        echo -e "Status: ${RED}STOPPED${NC}"
    fi
}

status_app() {
    local pid
    pid=$(get_pid)
    
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}[+] Portfolio Dashboard is RUNNING.${NC}"
        echo -e "${GREEN}[+] PID: $pid${NC}"
        echo -e "${GREEN}[+] Listening on: http://127.0.0.1:$PORT${NC}"
        # Print memory or cpu info if possible
        if command -v ps >/dev/null; then
            ps -p "$pid" -o %cpu,%mem,etime | sed 's/^/    /'
        fi
    else
        echo -e "${RED}[-] Portfolio Dashboard is STOPPED.${NC}"
        # Check if port is in use by something else
        local port_owner
        port_owner=$(lsof -t -i :$PORT -sTCP:LISTEN 2>/dev/null)
        if [ -n "$port_owner" ]; then
            echo -e "${YELLOW}[!] Warning: Port $PORT is in use by another process (PID: $port_owner)${NC}"
        fi
    fi
}

logs_app() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${RED}[-] Log file not found at $LOG_FILE${NC}"
        return 1
    fi
    echo -e "${BLUE}[*] Tailing logs (Press Ctrl+C to exit)...${NC}"
    tail -n 50 -f "$LOG_FILE"
}

clean_cache() {
    echo -e "${BLUE}[*] Cleaning dashboard cache files...${NC}"
    local count=0
    for cache_file in ".price_cache.json" ".price_symbol_cache.json" ".news_cache.json" ".history_cache.json"; do
        if [ -f "${APP_DIR}/${cache_file}" ]; then
            rm -f "${APP_DIR}/${cache_file}"
            echo -e "  Deleted ${cache_file}"
            count=$((count+1))
        fi
    done
    echo -e "${GREEN}[+] Cleaned $count cache file(s).${NC}"
}

# If no arguments, open the interactive menu
if [ $# -eq 0 ]; then
    while true; do
        clear
        echo -e "${BLUE}==============================================${NC}"
        echo -e "${BLUE}     Portfolio Dashboard Interactive Helper   ${NC}"
        echo -e "${BLUE}==============================================${NC}"
        status_interactive
        echo -e "${BLUE}----------------------------------------------${NC}"
        echo -e "Select an option:"
        echo -e "  ${GREEN}[1]${NC} Start Server"
        echo -e "  ${RED}[2]${NC} Stop Server"
        echo -e "  ${YELLOW}[3]${NC} Restart / Redeploy Server"
        echo -e "  ${CYAN}[4]${NC} Detailed Status Info"
        echo -e "  ${BLUE}[5]${NC} View Live Logs (Press Ctrl+C to return)"
        echo -e "  ${YELLOW}[6]${NC} Clean Cache Files"
        echo -e "  ${RED}[7]${NC} Exit Menu"
        echo -e "${BLUE}----------------------------------------------${NC}"
        read -p "Enter selection [1-7]: " choice
        echo
        case "$choice" in
            1) start_app; read -p "Press Enter to continue..." ;;
            2) stop_app; read -p "Press Enter to continue..." ;;
            3) stop_app; start_app; read -p "Press Enter to continue..." ;;
            4) status_app; read -p "Press Enter to continue..." ;;
            5) logs_app ;;
            6) clean_cache; read -p "Press Enter to continue..." ;;
            7|q|quit|exit) echo "Goodbye!"; exit 0 ;;
            *) echo -e "${RED}Invalid selection.${NC}"; sleep 1 ;;
        esac
    done
fi

# Parse command line argument
case "$1" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart|redeploy)
        stop_app
        start_app
        ;;
    status)
        status_app
        ;;
    logs)
        logs_app
        ;;
    clean)
        clean_cache
        ;;
    *)
        show_help
        exit 1
        ;;
esac
