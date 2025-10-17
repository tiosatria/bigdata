#!/bin/bash

# Tmux Multi-Spider Runner
# Usage: ./run.sh -n 16 -a arg1=val1 -s SETTING=value

set -e

# Default values
NUM_INSTANCES=1
SESSION_NAME="scrapy-cluster"
SPIDER_NAME="article"
SCRAPY_ARGS=""
MULTI_SCREEN=false

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--num)
            NUM_INSTANCES="$2"
            shift 2
            ;;
        -s|--spider)
            SPIDER_NAME="$2"
            shift 2
            ;;
        -S|--session)
            SESSION_NAME="$2"
            shift 2
            ;;
        --multi-screen)
            MULTI_SCREEN=true
            shift
            ;;
        -a|-s|-o|--set)
            # Collect all scrapy arguments
            SCRAPY_ARGS="$SCRAPY_ARGS $1 $2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -n, --num NUM          Number of spider instances (default: 1)"
            echo "  -s, --spider NAME      Spider name (default: article)"
            echo "  -S, --session NAME     Tmux session name (default: scrapy-cluster)"
            echo "  --multi-screen         Create all panes in one window (side-by-side grid)"
            echo "  -a KEY=VALUE           Pass arguments to spider"
            echo "  -s KEY=VALUE           Pass settings to scrapy"
            echo "  -o FILE                Output file"
            echo "  --set KEY=VALUE        Set project settings"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 -n 16"
            echo "  $0 -n 16 --multi-screen"
            echo "  $0 -n 8 -a start_id=100 -a end_id=200"
            echo "  $0 -n 4 -s CONCURRENT_REQUESTS=32 -s DOWNLOAD_DELAY=0"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use -h or --help for usage information"
            exit 1
            ;;
    esac
done

# Validate number of instances
if ! [[ "$NUM_INSTANCES" =~ ^[0-9]+$ ]] || [ "$NUM_INSTANCES" -lt 1 ]; then
    echo -e "${RED}Error: Number of instances must be a positive integer${NC}"
    exit 1
fi

echo -e "${GREEN}Starting $NUM_INSTANCES instances of spider '$SPIDER_NAME'${NC}"
echo -e "${YELLOW}Session name: $SESSION_NAME${NC}"
if [ -n "$SCRAPY_ARGS" ]; then
    echo -e "${YELLOW}Scrapy args:$SCRAPY_ARGS${NC}"
fi
echo ""

# Kill existing session if it exists
tmux has-session -t "$SESSION_NAME" 2>/dev/null && {
    echo -e "${YELLOW}Killing existing session '$SESSION_NAME'${NC}"
    tmux kill-session -t "$SESSION_NAME"
}

# Create new tmux session (detached)
tmux new-session -d -s "$SESSION_NAME" -n "spider-cluster"

if [ "$MULTI_SCREEN" = true ]; then
    echo -e "${GREEN}Creating multi-screen layout (all panes in one window)${NC}"

    # Calculate grid dimensions
    COLS=$(echo "sqrt($NUM_INSTANCES)" | bc)
    [ "$COLS" -lt 1 ] && COLS=1
    ROWS=$(echo "($NUM_INSTANCES + $COLS - 1) / $COLS" | bc)

    echo -e "${BLUE}Creating ${ROWS}x${COLS} grid for $NUM_INSTANCES spiders${NC}"

    # Start first spider
    tmux send-keys -t "$SESSION_NAME:spider-cluster" "scrapy crawl $SPIDER_NAME$SCRAPY_ARGS" C-m

    # Build perfect grid by creating all panes and using tiled layout
    for ((i=1; i<NUM_INSTANCES; i++)); do
        tmux split-window -t "$SESSION_NAME:spider-cluster" "scrapy crawl $SPIDER_NAME$SCRAPY_ARGS"
        # Apply tiled after each pane to maintain grid
        tmux select-layout -t "$SESSION_NAME:spider-cluster" tiled
    done

    # Create monitoring window separately (easier and more flexible)
    tmux new-window -t "$SESSION_NAME" -n "monitoring"
    tmux send-keys -t "$SESSION_NAME:monitoring" "htop -d 10 --sort-key PERCENT_CPU" C-m

    # Go back to spider cluster window
    tmux select-window -t "$SESSION_NAME:spider-cluster"
    tmux select-pane -t "$SESSION_NAME:spider-cluster.0"

else
    # Original window-based mode
    tmux send-keys -t "$SESSION_NAME:spider-cluster" "scrapy crawl $SPIDER_NAME$SCRAPY_ARGS" C-m
    tmux rename-window -t "$SESSION_NAME:spider-cluster" "spider-0"

    # Create additional windows for remaining instances
    for ((i=1; i<NUM_INSTANCES; i++)); do
        tmux new-window -t "$SESSION_NAME" -n "spider-$i"
        tmux send-keys -t "$SESSION_NAME:spider-$i" "scrapy crawl $SPIDER_NAME$SCRAPY_ARGS" C-m
    done

    # Create monitoring window at the end
    tmux new-window -t "$SESSION_NAME" -n "monitoring"
    tmux send-keys -t "$SESSION_NAME:monitoring" "htop -d 10 --sort-key PERCENT_CPU" C-m
fi

# Calculate grid layout (try to make it roughly square)
COLS=$(echo "sqrt($NUM_INSTANCES)" | bc)
ROWS=$(echo "($NUM_INSTANCES + $COLS - 1) / $COLS" | bc)

if [ "$MULTI_SCREEN" = true ]; then
    echo -e "${GREEN}Grid layout created: ${ROWS}x${COLS} (approximately)${NC}"
else
    echo -e "${GREEN}Creating grid layout: ${ROWS}x${COLS}${NC}"

    # Select layout based on number of instances
    if [ "$NUM_INSTANCES" -eq 1 ]; then
        # Single pane, no layout needed
        :
    elif [ "$NUM_INSTANCES" -le 4 ]; then
        tmux select-layout -t "$SESSION_NAME" tiled
    elif [ "$NUM_INSTANCES" -le 9 ]; then
        tmux select-layout -t "$SESSION_NAME" tiled
    else
        # For many instances, use tiled layout
        tmux select-layout -t "$SESSION_NAME" tiled
    fi
fi

echo ""
echo -e "${GREEN}✓ Tmux session '$SESSION_NAME' created with $NUM_INSTANCES spider instances${NC}"
if [ "$MULTI_SCREEN" = true ]; then
    echo -e "${YELLOW}  Mode: Multi-screen (all panes in one window + monitoring pane at bottom)${NC}"
else
    echo -e "${YELLOW}  Mode: Multi-window (separate windows per spider + monitoring window)${NC}"
fi
echo ""
echo "To attach to the session:"
echo -e "  ${YELLOW}tmux attach -t $SESSION_NAME${NC}"
echo ""
if [ "$MULTI_SCREEN" = true ]; then
    echo "Useful tmux commands (multi-screen mode):"
    echo "  Ctrl+b arrow   - Navigate between panes"
    echo "  Ctrl+b o       - Cycle through panes"
    echo "  Ctrl+b q       - Show pane numbers (press number to jump)"
    echo "  Ctrl+b z       - Zoom/unzoom current pane (fullscreen toggle)"
    echo "  Ctrl+b Space   - Cycle through layouts"
    echo "  Ctrl+b {/}     - Swap pane positions"
    echo "  Ctrl+b d       - Detach from session"
    echo ""
    echo "Monitoring pane (bottom):"
    echo "  - htop showing CPU, memory, and network usage"
    echo "  - Press 'q' in monitoring pane to exit htop"
else
    echo "Useful tmux commands:"
    echo "  Ctrl+b n       - Next window"
    echo "  Ctrl+b p       - Previous window"
    echo "  Ctrl+b w       - List windows"
    echo "  Ctrl+b [0-9]   - Switch to window number"
    echo "  Ctrl+b d       - Detach from session"
    echo "  Ctrl+b &       - Kill current window"
    echo ""
    echo "Last window 'monitoring' shows:"
    echo "  - htop with CPU, memory, and process info"
fi
echo ""
echo "To kill all spiders:"
echo -e "  ${YELLOW}./stop.sh${NC}                    # Graceful shutdown"
echo -e "  ${YELLOW}./stop.sh --force${NC}            # Immediate kill"
echo -e "  ${YELLOW}tmux kill-session -t $SESSION_NAME${NC}  # Manual kill"
echo ""

# Auto-attach to session
read -p "Attach to session now? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    tmux attach -t "$SESSION_NAME"
fi