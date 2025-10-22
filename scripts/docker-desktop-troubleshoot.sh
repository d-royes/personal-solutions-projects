#!/bin/bash

################################################################################
# Docker Desktop Troubleshooting Script
#
# This script diagnoses common Docker Desktop issues by checking:
# - System requirements and resources
# - Docker installation status
# - Docker Desktop logs and status
# - Virtualization support
# - Common configuration issues
# - Permissions
#
# Usage: ./docker-desktop-troubleshoot.sh [--save-logs]
#
# Options:
#   --save-logs    Save all output to a timestamped log file
################################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Flags
SAVE_LOGS=false
LOG_FILE=""

# Parse arguments
for arg in "$@"; do
    case $arg in
        --save-logs)
            SAVE_LOGS=true
            LOG_FILE="docker-troubleshoot-$(date +%Y%m%d-%H%M%S).log"
            ;;
    esac
done

# Redirect output if saving logs
if [ "$SAVE_LOGS" = true ]; then
    exec > >(tee -a "$LOG_FILE")
    exec 2>&1
    echo "Saving output to: $LOG_FILE"
fi

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        print_info "Operating System: Linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        print_info "Operating System: macOS"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
        print_info "Operating System: Windows"
    else
        OS="unknown"
        print_warning "Unknown operating system: $OSTYPE"
    fi
}

################################################################################
# System Information
################################################################################

check_system_info() {
    print_header "System Information"

    # OS and Kernel
    echo "OS Details:"
    uname -a
    echo ""

    if [ "$OS" == "linux" ]; then
        if [ -f /etc/os-release ]; then
            cat /etc/os-release
        fi
    elif [ "$OS" == "macos" ]; then
        sw_vers
    fi
    echo ""

    # Memory
    echo "Memory:"
    if [ "$OS" == "linux" ]; then
        free -h
    elif [ "$OS" == "macos" ]; then
        vm_stat | perl -ne '/page size of (\d+)/ and $size=$1; /Pages\s+([^:]+)[^\d]+(\d+)/ and printf("%-16s % 16.2f Mi\n", "$1:", $2 * $size / 1048576);'
    fi
    echo ""

    # Disk Space
    echo "Disk Space:"
    df -h
    echo ""

    # CPU Info
    if [ "$OS" == "linux" ]; then
        echo "CPU Info:"
        lscpu | grep -E "^CPU\(s\)|Model name|Thread|Core"
    elif [ "$OS" == "macos" ]; then
        echo "CPU Info:"
        sysctl -n machdep.cpu.brand_string
        sysctl -n hw.ncpu
    fi
    echo ""
}

################################################################################
# Docker Installation Check
################################################################################

check_docker_installation() {
    print_header "Docker Installation Check"

    # Check for docker command
    if command -v docker &> /dev/null; then
        print_success "Docker command found: $(which docker)"

        # Try to get version
        echo ""
        echo "Docker version:"
        docker version 2>&1 || print_error "Unable to get Docker version (daemon may not be running)"
        echo ""

        # Try to get info
        echo "Docker info:"
        docker info 2>&1 || print_error "Unable to get Docker info (daemon may not be running)"
        echo ""
    else
        print_error "Docker command not found in PATH"
        echo "Docker may not be installed or not in PATH"
        echo "PATH: $PATH"
    fi

    # Check for docker-compose
    echo ""
    if command -v docker-compose &> /dev/null; then
        print_success "docker-compose found: $(which docker-compose)"
        docker-compose version
    else
        print_warning "docker-compose not found (may not be needed for Docker Compose V2)"
    fi

    # Check for docker compose (V2)
    echo ""
    if docker compose version &> /dev/null; then
        print_success "Docker Compose V2 available"
        docker compose version
    fi
}

################################################################################
# Docker Desktop Status
################################################################################

check_docker_desktop_status() {
    print_header "Docker Desktop Status"

    if [ "$OS" == "linux" ]; then
        # Check if Docker Desktop is running
        if pgrep -f "Docker Desktop" > /dev/null; then
            print_success "Docker Desktop process is running"
        else
            print_error "Docker Desktop process not found"
        fi

        # Check systemd service
        if command -v systemctl &> /dev/null; then
            echo ""
            echo "Docker service status:"
            systemctl status docker.service --no-pager 2>&1 || echo "Docker service not available"

            echo ""
            echo "Docker socket status:"
            systemctl status docker.socket --no-pager 2>&1 || echo "Docker socket not available"
        fi

        # Check for docker.sock
        echo ""
        if [ -S "/var/run/docker.sock" ]; then
            print_success "Docker socket exists: /var/run/docker.sock"
            ls -la /var/run/docker.sock
        else
            print_error "Docker socket not found at /var/run/docker.sock"
        fi

        # Check Docker Desktop specific socket
        if [ -S "$HOME/.docker/desktop/docker.sock" ]; then
            print_success "Docker Desktop socket exists: $HOME/.docker/desktop/docker.sock"
            ls -la "$HOME/.docker/desktop/docker.sock"
        fi

    elif [ "$OS" == "macos" ]; then
        # Check if Docker.app is running
        if pgrep -x "Docker" > /dev/null; then
            print_success "Docker Desktop is running"
        else
            print_error "Docker Desktop is not running"
        fi

        # Check Docker Desktop socket
        echo ""
        if [ -S "$HOME/.docker/run/docker.sock" ]; then
            print_success "Docker socket exists"
            ls -la "$HOME/.docker/run/docker.sock"
        else
            print_error "Docker socket not found"
        fi

    elif [ "$OS" == "windows" ]; then
        # Check if Docker Desktop is running on Windows
        if tasklist.exe 2>/dev/null | grep -i "Docker Desktop.exe" > /dev/null; then
            print_success "Docker Desktop process is running"
        else
            print_error "Docker Desktop process not found"
        fi
    fi
}

################################################################################
# Docker Desktop Logs
################################################################################

collect_docker_logs() {
    print_header "Docker Desktop Logs"

    if [ "$OS" == "linux" ]; then
        DOCKER_LOGS_DIR="$HOME/.docker/desktop/log"

        if [ -d "$DOCKER_LOGS_DIR" ]; then
            print_success "Docker Desktop logs directory found: $DOCKER_LOGS_DIR"
            echo ""
            echo "Log directories:"
            ls -la "$DOCKER_LOGS_DIR"
            echo ""

            # Show recent logs from various log files
            for log_dir in "$DOCKER_LOGS_DIR"/*; do
                if [ -d "$log_dir" ]; then
                    echo "----------------------------------------"
                    echo "Logs from: $log_dir"
                    echo "----------------------------------------"

                    for log_file in "$log_dir"/*.log; do
                        if [ -f "$log_file" ]; then
                            echo ""
                            echo "=== $(basename "$log_file") (last 20 lines) ==="
                            tail -n 20 "$log_file" 2>&1 || echo "Unable to read log file"
                        fi
                    done
                fi
            done
        else
            print_warning "Docker Desktop logs directory not found at $DOCKER_LOGS_DIR"
        fi

        # Check journalctl logs
        if command -v journalctl &> /dev/null; then
            echo ""
            echo "----------------------------------------"
            echo "System logs (journalctl - docker)"
            echo "----------------------------------------"
            journalctl -u docker.service --no-pager -n 50 2>&1 || echo "Unable to get journalctl logs"
        fi

    elif [ "$OS" == "macos" ]; then
        DOCKER_LOGS_DIR="$HOME/Library/Containers/com.docker.docker/Data/log"

        if [ -d "$DOCKER_LOGS_DIR" ]; then
            print_success "Docker Desktop logs directory found"
            echo ""
            echo "Recent log files:"
            ls -lht "$DOCKER_LOGS_DIR"/*.log 2>&1 | head -10
            echo ""

            # Show recent VM logs
            if [ -f "$DOCKER_LOGS_DIR/vm.log" ]; then
                echo "=== VM logs (last 30 lines) ==="
                tail -n 30 "$DOCKER_LOGS_DIR/vm.log"
            fi

            # Show recent host logs
            if [ -f "$DOCKER_LOGS_DIR/host.log" ]; then
                echo ""
                echo "=== Host logs (last 30 lines) ==="
                tail -n 30 "$DOCKER_LOGS_DIR/host.log"
            fi
        else
            print_warning "Docker Desktop logs directory not found"
        fi
    fi

    # Check kernel logs for docker-related messages
    echo ""
    echo "----------------------------------------"
    echo "Recent kernel logs mentioning docker"
    echo "----------------------------------------"
    dmesg 2>&1 | grep -i docker | tail -n 20 || echo "No docker-related kernel messages found"
}

################################################################################
# Virtualization Support
################################################################################

check_virtualization() {
    print_header "Virtualization Support"

    if [ "$OS" == "linux" ]; then
        # Check CPU virtualization support
        if grep -E '(vmx|svm)' /proc/cpuinfo > /dev/null; then
            print_success "CPU supports virtualization (VMX/SVM)"
        else
            print_error "CPU does not support virtualization or it's disabled in BIOS"
        fi

        # Check if KVM is available
        echo ""
        if [ -e /dev/kvm ]; then
            print_success "/dev/kvm exists"
            ls -la /dev/kvm
        else
            print_error "/dev/kvm not found (KVM may not be installed or enabled)"
        fi

        # Check KVM modules
        echo ""
        echo "KVM kernel modules:"
        lsmod | grep kvm || print_warning "No KVM modules loaded"

        # Check if user has access to kvm group
        echo ""
        if groups | grep -q kvm; then
            print_success "Current user is in 'kvm' group"
        else
            print_warning "Current user is NOT in 'kvm' group (may need to run: sudo usermod -aG kvm \$USER)"
        fi

        # Check if QEMU is installed
        echo ""
        if command -v qemu-system-x86_64 &> /dev/null; then
            print_success "QEMU is installed: $(which qemu-system-x86_64)"
        else
            print_warning "QEMU not found (required for Docker Desktop on Linux)"
        fi

    elif [ "$OS" == "macos" ]; then
        # macOS uses Hypervisor.framework
        print_info "macOS uses built-in Hypervisor.framework"

        # Check if virtualization is available
        if sysctl kern.hv_support 2>/dev/null | grep -q ": 1"; then
            print_success "Hypervisor support is available"
        else
            print_warning "Unable to verify hypervisor support"
        fi
    fi
}

################################################################################
# Docker Configuration
################################################################################

check_docker_config() {
    print_header "Docker Configuration"

    # Check Docker config files
    DOCKER_CONFIG_DIR="$HOME/.docker"

    if [ -d "$DOCKER_CONFIG_DIR" ]; then
        print_success "Docker config directory exists: $DOCKER_CONFIG_DIR"
        echo ""
        ls -la "$DOCKER_CONFIG_DIR"

        # Check config.json
        if [ -f "$DOCKER_CONFIG_DIR/config.json" ]; then
            echo ""
            echo "=== config.json ==="
            cat "$DOCKER_CONFIG_DIR/config.json"
        fi

        # Check daemon.json
        if [ -f "$DOCKER_CONFIG_DIR/daemon.json" ]; then
            echo ""
            echo "=== daemon.json ==="
            cat "$DOCKER_CONFIG_DIR/daemon.json"
        fi
    else
        print_warning "Docker config directory not found"
    fi

    # Check system-wide daemon.json
    if [ "$OS" == "linux" ]; then
        if [ -f "/etc/docker/daemon.json" ]; then
            echo ""
            echo "=== /etc/docker/daemon.json ==="
            cat "/etc/docker/daemon.json"
        fi
    fi
}

################################################################################
# Conflicting Installations
################################################################################

check_conflicts() {
    print_header "Check for Conflicting Installations"

    # Check for multiple Docker installations
    echo "Searching for Docker binaries:"
    echo ""

    # Find all docker executables
    which -a docker 2>/dev/null || print_info "No docker in PATH"

    # Check common installation locations
    echo ""
    echo "Checking common Docker installation paths:"

    locations=(
        "/usr/bin/docker"
        "/usr/local/bin/docker"
        "/snap/bin/docker"
        "/opt/docker/bin/docker"
        "$HOME/.docker/bin/docker"
    )

    for loc in "${locations[@]}"; do
        if [ -f "$loc" ]; then
            print_warning "Found Docker at: $loc"
            ls -la "$loc"
        fi
    done

    # Check for snap installation
    if command -v snap &> /dev/null; then
        echo ""
        echo "Snap Docker packages:"
        snap list 2>/dev/null | grep docker || print_info "No Docker snap packages found"
    fi

    # Check for apt/dpkg installation
    if command -v dpkg &> /dev/null; then
        echo ""
        echo "Debian packages containing 'docker':"
        dpkg -l | grep docker || print_info "No Docker packages found via dpkg"
    fi

    # Check for yum/rpm installation
    if command -v rpm &> /dev/null; then
        echo ""
        echo "RPM packages containing 'docker':"
        rpm -qa | grep docker || print_info "No Docker packages found via rpm"
    fi

    # Check for homebrew installation (macOS)
    if command -v brew &> /dev/null; then
        echo ""
        echo "Homebrew Docker packages:"
        brew list | grep docker || print_info "No Docker packages found via brew"
    fi
}

################################################################################
# Permissions Check
################################################################################

check_permissions() {
    print_header "Permissions Check"

    # Check user groups
    echo "Current user: $(whoami)"
    echo "User groups: $(groups)"
    echo ""

    # Check docker group membership
    if groups | grep -q docker; then
        print_success "User is in 'docker' group"
    else
        print_warning "User is NOT in 'docker' group"
        echo "  To add yourself to docker group: sudo usermod -aG docker \$USER"
        echo "  Then log out and back in for changes to take effect"
    fi

    # Check /var/run/docker.sock permissions
    if [ -S "/var/run/docker.sock" ]; then
        echo ""
        echo "Docker socket permissions:"
        ls -la /var/run/docker.sock

        if [ -w /var/run/docker.sock ]; then
            print_success "Current user has write access to docker.sock"
        else
            print_error "Current user does NOT have write access to docker.sock"
        fi
    fi
}

################################################################################
# Resource Check
################################################################################

check_resources() {
    print_header "Resource Availability"

    # Check disk space in Docker directory
    if [ "$OS" == "linux" ]; then
        DOCKER_DATA_DIR="/var/lib/docker"
        if [ -d "$DOCKER_DATA_DIR" ]; then
            echo "Docker data directory: $DOCKER_DATA_DIR"
            du -sh "$DOCKER_DATA_DIR" 2>/dev/null || echo "Unable to check size"
            echo ""
            df -h "$DOCKER_DATA_DIR"
        fi

        # Check Docker Desktop data
        DESKTOP_DATA="$HOME/.docker/desktop"
        if [ -d "$DESKTOP_DATA" ]; then
            echo ""
            echo "Docker Desktop data directory: $DESKTOP_DATA"
            du -sh "$DESKTOP_DATA" 2>/dev/null || echo "Unable to check size"
        fi

    elif [ "$OS" == "macos" ]; then
        DOCKER_DATA="$HOME/Library/Containers/com.docker.docker/Data"
        if [ -d "$DOCKER_DATA" ]; then
            echo "Docker Desktop data directory: $DOCKER_DATA"
            du -sh "$DOCKER_DATA" 2>/dev/null || echo "Unable to check size"
        fi
    fi

    # Check for large containers or images
    echo ""
    echo "Docker disk usage:"
    docker system df 2>&1 || print_warning "Unable to get Docker disk usage"
}

################################################################################
# Network Check
################################################################################

check_network() {
    print_header "Network Configuration"

    # Check Docker networks
    echo "Docker networks:"
    docker network ls 2>&1 || print_warning "Unable to list Docker networks"

    echo ""
    echo "Network interfaces:"
    if [ "$OS" == "linux" ]; then
        ip addr show | grep -E "^[0-9]+:|inet " || ifconfig
    elif [ "$OS" == "macos" ]; then
        ifconfig | grep -E "^[a-z]+[0-9]+:|inet "
    fi

    # Check for docker0 bridge
    if [ "$OS" == "linux" ]; then
        echo ""
        if ip link show docker0 &> /dev/null; then
            print_success "docker0 bridge exists"
            ip addr show docker0
        else
            print_warning "docker0 bridge not found"
        fi
    fi
}

################################################################################
# Recommendations
################################################################################

generate_recommendations() {
    print_header "Recommendations & Next Steps"

    echo "Based on the diagnostics above, here are potential solutions:"
    echo ""

    print_info "1. If Docker Desktop won't start:"
    echo "   - Check the logs section above for specific errors"
    echo "   - Try restarting Docker Desktop completely"
    echo "   - Try: 'docker context use default'"
    echo ""

    print_info "2. If virtualization is not enabled:"
    echo "   - Enable VT-x/AMD-V in BIOS settings"
    echo "   - On Linux, ensure KVM modules are loaded"
    echo "   - Add user to kvm group: sudo usermod -aG kvm \$USER"
    echo ""

    print_info "3. If there are permission issues:"
    echo "   - Add user to docker group: sudo usermod -aG docker \$USER"
    echo "   - Log out and back in for group changes to take effect"
    echo "   - Check ownership of /var/run/docker.sock"
    echo ""

    print_info "4. If there are conflicting installations:"
    echo "   - Remove old Docker installations"
    echo "   - Keep only Docker Desktop or only docker-ce, not both"
    echo "   - Clear Docker contexts: docker context rm <context>"
    echo ""

    print_info "5. If running out of disk space:"
    echo "   - Run: docker system prune -a --volumes"
    echo "   - Increase disk allocation in Docker Desktop settings"
    echo ""

    print_info "6. If Docker Desktop is using too many resources:"
    echo "   - Adjust CPU/Memory limits in Docker Desktop settings"
    echo "   - Check for runaway containers"
    echo ""

    print_info "7. Try resetting Docker Desktop:"
    echo "   - Docker Desktop > Troubleshoot > Reset to factory defaults"
    echo "   - Warning: This will remove all containers, images, and volumes"
    echo ""

    print_info "8. Check Docker Desktop documentation:"
    echo "   - https://docs.docker.com/desktop/troubleshoot/"
    echo ""
}

################################################################################
# Main Execution
################################################################################

main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║     Docker Desktop Troubleshooting Script                  ║"
    echo "║     Version 1.0                                            ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    echo "This script will collect diagnostic information about your"
    echo "Docker Desktop installation and help identify common issues."
    echo ""

    detect_os

    # Run all checks
    check_system_info
    check_docker_installation
    check_docker_desktop_status
    check_virtualization
    check_docker_config
    check_conflicts
    check_permissions
    check_resources
    check_network
    collect_docker_logs

    # Generate recommendations
    generate_recommendations

    if [ "$SAVE_LOGS" = true ]; then
        echo ""
        print_success "All diagnostic information saved to: $LOG_FILE"
        echo "You can share this file when seeking help with Docker Desktop issues"
    fi

    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║     Diagnostics Complete                                   ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
}

# Run main function
main
