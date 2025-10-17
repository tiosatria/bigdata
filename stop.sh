#!/bin/bash

# Tmux Spider Shutdown Script
# Usage: ./stop.sh [OPTIONS]

set -e

# Default values
SESSION_NAME="scrapy-cluster"
FORCE=false
WAIT_TIME=10

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -S|--session)
            SESSION_NAME="$2"
            shift 2
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -w|--wait)
            WAIT_TIME="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -S, --session NAME     Tmux session name (default: scrapy-cluster)"
            echo "  -f, --force            Force kill without graceful shutdown"
            echo "  -w, --wait SECONDS     Wait time for graceful shutdown (default: 10)"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                     # Graceful shutdown with 10s wait"
            echo "  $0 --force             # Immediate kill"
            echo "  $0 --wait 30           # Wait 30 seconds for graceful shutdown"
            echo "  $0 -S my-session       # Stop specific session"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Check if session exists
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo -e "${YELLOW}Session '$SESSION_NAME' does not exist or is already stopped${NC}"
    exit 0
fi

# Get number of panes/windows
NUM_PANES=$(tmux list-panes -t "$SESSION_NAME" -a 2>/dev/null | wc -l)
NUM_WINDOWS=$(tmux list-windows -t "$SESSION_NAME" 2>/dev/null | wc -l)

echo -e "${BLUE}Found session '$SESSION_NAME' with $NUM_WINDOWS window(s) and $NUM_PANES pane(s)${NC}"

if [ "$FORCE" = true ]; then
    echo -e "${RED}Force killing session...${NC}"
    tmux kill-session -t "$SESSION_NAME"
    echo -e "${GREEN}✓ Session killed${NC}"
    exit 0
fi

# Graceful shutdown
echo -e "${YELLOW}Initiating graceful shutdown...${NC}"
echo -e "${YELLOW}Sending Ctrl+C to all spider processes...${NC}"

# Detect if it's multi-screen (check for "spider-cluster" window with many panes) or multi-window mode
CLUSTER_WINDOW=$(tmux list-windows -t "$SESSION_NAME" -F '#{window_name}' | grep -c "spider-cluster")

if [ "$CLUSTER_WINDOW" -gt 0 ]; then
    # Multi-screen mode: spider-cluster window exists with multiple panes
    echo -e "${BLUE}Detected multi-screen mode${NC}"
    CLUSTER_PANES=$(tmux list-panes -t "$SESSION_NAME:spider-cluster" -F '#{pane_index}' | wc -l)
    echo -e "${BLUE}Found $CLUSTER_PANES panes in spider-cluster window${NC}"

    # Send Ctrl+C to all panes in spider-cluster window
    tmux list-panes -t "$SESSION_NAME:spider-cluster" -F '#{pane_index}' | while read pane; do
        tmux send-keys -t "$SESSION_NAME:spider-cluster.$pane" C-c
        echo -e "  ${GREEN}→${NC} Sent Ctrl+C to pane $pane"
    done
else
    # Multi-window mode: send Ctrl+C to all windows except monitoring
    echo -e "${BLUE}Detected multi-window mode${NC}"
    tmux list-windows -t "$SESSION_NAME" -F '#{window_index}:#{window_name}' | while IFS=: read window_idx window_name; do
        # Skip monitoring window
        if [[ "$window_name" != "monitoring" ]]; then
            tmux send-keys -t "$SESSION_NAME:$window_idx" C-c
            echo -e "  ${GREEN}→${NC} Sent Ctrl+C to window $window_idx ($window_name)"
        fi
    done
fi

echo ""
echo -e "${YELLOW}Waiting ${WAIT_TIME} seconds for spiders to shutdown gracefully...${NC}"

# Wait and show countdown
for ((i=WAIT_TIME; i>0; i--)); do
    printf "\r${YELLOW}  %2d seconds remaining...${NC}" $i
    sleep 1
done
printf "\r${GREEN}  ✓ Wait completed          ${NC}\n"

echo ""

# Check if processes are still running
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    REMAINING=$(tmux list-panes -t "$SESSION_NAME" -a -F '#{pane_pid}' 2>/dev/null | wc -l)

    if [ "$REMAINING" -gt 0 ]; then
        echo -e "${YELLOW}Some processes are still running${NC}"
        read -p "Force kill remaining processes? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}Force killing session...${NC}"
            tmux kill-session -t "$SESSION_NAME"
            echo -e "${GREEN}✓ Session killed${NC}"
        else
            echo -e "${BLUE}Leaving session active. You can kill it manually with:${NC}"
            echo -e "  ${YELLOW}tmux kill-session -t $SESSION_NAME${NC}"
        fi
    else
        echo -e "${GREEN}✓ All processes shutdown gracefully${NC}"
        tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
    fi
else
    echo -e "${GREEN}✓ All spiders stopped successfully${NC}"
fi

echo ""
echo -e "${GREEN}Shutdown complete!${NC}"