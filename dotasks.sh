#!/usr/bin/env bash
#
# dotasks.sh - Run chat-ffs tasks using Claude Code
#
# Usage:
#   ./dotasks.sh              # Run all tasks
#   ./dotasks.sh 03           # Run task starting with "03"
#   ./dotasks.sh 03 04 05     # Run specific tasks
#   ./dotasks.sh --list       # List all tasks
#   ./dotasks.sh --status     # Show task completion status
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASKS_FILE="$SCRIPT_DIR/TASKS.json"
RESULTS_DIR="$SCRIPT_DIR/.task_results"
MAX_RETRIES=5
RESULT_FILE=".task_result"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check dependencies
check_deps() {
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}Error: jq is required but not installed${NC}"
        exit 1
    fi
    if ! command -v claude &> /dev/null; then
        echo -e "${RED}Error: claude CLI is required but not installed${NC}"
        exit 1
    fi
}

# List all tasks
list_tasks() {
    echo -e "${BLUE}Available tasks:${NC}"
    jq -r '.tasks[] | "  \(.id): \(.name) - \(.description)"' "$TASKS_FILE"
}

# Show task status
show_status() {
    echo -e "${BLUE}Task Status:${NC}"
    mkdir -p "$RESULTS_DIR"
    
    while IFS= read -r task_id; do
        task_name=$(jq -r ".tasks[] | select(.id == \"$task_id\") | .name" "$TASKS_FILE")
        result_file="$RESULTS_DIR/${task_id}.result"
        
        if [[ -f "$result_file" ]]; then
            result=$(cat "$result_file")
            if [[ "$result" == "PASS" ]]; then
                echo -e "  ${GREEN}✓${NC} $task_id: $task_name"
            else
                echo -e "  ${RED}✗${NC} $task_id: $task_name - $result"
            fi
        else
            echo -e "  ${YELLOW}○${NC} $task_id: $task_name (not run)"
        fi
    done < <(jq -r '.tasks[].id' "$TASKS_FILE")
}

# Get task field by ID
get_task_field() {
    local task_id="$1"
    local field="$2"
    jq -r ".tasks[] | select(.id == \"$task_id\") | .$field" "$TASKS_FILE"
}

# Run Claude Code with a prompt
run_claude() {
    local prompt="$1"
    local description="$2"
    
    echo -e "${BLUE}Running Claude: ${description}${NC}"
    
    # Run claude in print mode (one-shot, no interaction)
    # The --print flag outputs response and exits
    claude --print "$prompt"
    
    return $?
}

# Run a single task
run_task() {
    local task_id="$1"
    local task_name
    local work_prompt
    local test_prompt
    local attempt
    local result
    
    task_name=$(get_task_field "$task_id" "name")
    work_prompt=$(get_task_field "$task_id" "work_prompt")
    test_prompt=$(get_task_field "$task_id" "test_prompt")
    
    if [[ "$task_name" == "null" ]]; then
        echo -e "${RED}Error: Task '$task_id' not found${NC}"
        return 1
    fi
    
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Task: $task_id - $task_name${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    
    mkdir -p "$RESULTS_DIR"
    
    for attempt in $(seq 1 $MAX_RETRIES); do
        echo ""
        echo -e "${YELLOW}Attempt $attempt of $MAX_RETRIES${NC}"
        
        # Remove any previous result file
        rm -f "$SCRIPT_DIR/$RESULT_FILE"
        
        # Phase 1: Do the work
        echo -e "${BLUE}Phase 1: Executing work...${NC}"
        if ! run_claude "$work_prompt" "work"; then
            echo -e "${RED}Claude execution failed${NC}"
            continue
        fi
        
        # Small delay to let files settle
        sleep 1
        
        # Phase 2: Test the work
        echo ""
        echo -e "${BLUE}Phase 2: Testing...${NC}"
        rm -f "$SCRIPT_DIR/$RESULT_FILE"
        
        if ! run_claude "$test_prompt" "test"; then
            echo -e "${RED}Claude test execution failed${NC}"
            continue
        fi
        
        # Check for result file
        sleep 1
        
        if [[ -f "$SCRIPT_DIR/$RESULT_FILE" ]]; then
            result=$(cat "$SCRIPT_DIR/$RESULT_FILE")
            
            if [[ "$result" == "PASS" ]]; then
                echo -e "${GREEN}✓ Task $task_id PASSED${NC}"
                echo "PASS" > "$RESULTS_DIR/${task_id}.result"
                rm -f "$SCRIPT_DIR/$RESULT_FILE"
                return 0
            else
                echo -e "${RED}✗ Test failed: $result${NC}"
                echo "$result" > "$RESULTS_DIR/${task_id}.result"
            fi
        else
            echo -e "${YELLOW}Warning: No result file created by test${NC}"
            echo "FAIL: No result file" > "$RESULTS_DIR/${task_id}.result"
        fi
        
        if [[ $attempt -lt $MAX_RETRIES ]]; then
            echo -e "${YELLOW}Retrying...${NC}"
            sleep 2
        fi
    done
    
    echo -e "${RED}✗ Task $task_id FAILED after $MAX_RETRIES attempts${NC}"
    return 1
}

# Get all task IDs
get_all_task_ids() {
    jq -r '.tasks[].id' "$TASKS_FILE"
}

# Find task ID by prefix
find_task_by_prefix() {
    local prefix="$1"
    jq -r ".tasks[] | select(.id | startswith(\"$prefix\")) | .id" "$TASKS_FILE" | head -1
}

# Main
main() {
    check_deps
    
    if [[ ! -f "$TASKS_FILE" ]]; then
        echo -e "${RED}Error: TASKS.json not found at $TASKS_FILE${NC}"
        exit 1
    fi
    
    # Handle flags
    case "${1:-}" in
        --list|-l)
            list_tasks
            exit 0
            ;;
        --status|-s)
            show_status
            exit 0
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS] [TASK_IDS...]"
            echo ""
            echo "Options:"
            echo "  --list, -l     List all tasks"
            echo "  --status, -s   Show task completion status"
            echo "  --help, -h     Show this help"
            echo ""
            echo "Examples:"
            echo "  $0              Run all tasks in order"
            echo "  $0 03           Run task starting with '03'"
            echo "  $0 03 04 05     Run specific tasks"
            exit 0
            ;;
    esac
    
    # Determine which tasks to run
    local tasks_to_run=()
    
    if [[ $# -eq 0 ]]; then
        # Run all tasks
        while IFS= read -r task_id; do
            tasks_to_run+=("$task_id")
        done < <(get_all_task_ids)
    else
        # Run specified tasks
        for arg in "$@"; do
            task_id=$(find_task_by_prefix "$arg")
            if [[ -n "$task_id" ]]; then
                tasks_to_run+=("$task_id")
            else
                echo -e "${YELLOW}Warning: No task found matching '$arg'${NC}"
            fi
        done
    fi
    
    if [[ ${#tasks_to_run[@]} -eq 0 ]]; then
        echo -e "${RED}No tasks to run${NC}"
        exit 1
    fi
    
    echo -e "${BLUE}Running ${#tasks_to_run[@]} task(s)...${NC}"
    
    local failed=0
    for task_id in "${tasks_to_run[@]}"; do
        if ! run_task "$task_id"; then
            ((failed++))
        fi
    done
    
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Summary${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    show_status
    
    if [[ $failed -gt 0 ]]; then
        echo ""
        echo -e "${RED}$failed task(s) failed${NC}"
        exit 1
    else
        echo ""
        echo -e "${GREEN}All tasks completed successfully!${NC}"
    fi
}

main "$@"
