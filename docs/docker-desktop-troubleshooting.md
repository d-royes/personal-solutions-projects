# Docker Desktop Troubleshooting Guide

This guide provides comprehensive troubleshooting for Docker Desktop issues across Linux, macOS, and Windows.

## Quick Start

### Running the Troubleshooting Script

1. **Download the script:**
   ```bash
   # The script is located at: scripts/docker-desktop-troubleshoot.sh
   ```

2. **Make it executable:**
   ```bash
   chmod +x scripts/docker-desktop-troubleshoot.sh
   ```

3. **Run the script:**
   ```bash
   # Basic run (output to terminal)
   ./scripts/docker-desktop-troubleshoot.sh

   # Save output to a log file
   ./scripts/docker-desktop-troubleshoot.sh --save-logs
   ```

## What the Script Checks

The troubleshooting script performs comprehensive diagnostics:

### 1. System Information
- Operating system and kernel version
- Available memory and disk space
- CPU information and core count

### 2. Docker Installation
- Checks if Docker is installed and in PATH
- Verifies Docker version
- Tests Docker daemon connectivity
- Checks for Docker Compose (both V1 and V2)

### 3. Docker Desktop Status
- Process status (is Docker Desktop running?)
- Docker daemon/service status
- Docker socket availability
- System service status (systemd on Linux)

### 4. Virtualization Support
- **Linux**: KVM module, /dev/kvm, CPU virtualization flags
- **macOS**: Hypervisor.framework availability
- User permissions for virtualization

### 5. Docker Configuration
- User config files (~/.docker/)
- System-wide daemon configuration
- Docker contexts

### 6. Conflicting Installations
- Multiple Docker installations (snap, apt, docker-ce, etc.)
- Different Docker binaries in PATH
- Package manager installations

### 7. Permissions
- User group membership (docker, kvm groups)
- Docker socket permissions
- File ownership issues

### 8. Resource Usage
- Disk space in Docker data directories
- Docker image/container disk usage
- Available system resources

### 9. Network Configuration
- Docker networks
- Network interfaces
- Docker bridge (docker0)

### 10. Docker Desktop Logs
- Collects recent logs from Docker Desktop
- System logs (journalctl on Linux)
- Kernel messages related to Docker

## Common Issues and Solutions

### Issue 1: Docker Desktop Won't Start

**Symptoms:**
- Docker Desktop shows "Starting..." indefinitely
- Error message: "Docker Desktop failed to start"
- Docker daemon not responding

**Solutions:**

1. **Check the logs from the script output** - Look in the "Docker Desktop Logs" section for specific errors

2. **Restart Docker Desktop:**
   ```bash
   # Linux
   systemctl --user restart docker-desktop

   # macOS
   # Quit Docker Desktop and restart from Applications

   # Or kill the process and restart
   pkill -SIGHUP -f Docker
   ```

3. **Reset Docker context:**
   ```bash
   docker context use default
   docker context ls
   ```

4. **Check disk space:**
   - Ensure you have at least 10GB free space
   - Run: `docker system prune -a --volumes` (Warning: removes all unused data)

5. **Factory reset Docker Desktop:**
   - Docker Desktop → Troubleshoot → Reset to factory defaults
   - **Warning:** This removes all containers, images, and volumes

### Issue 2: "Cannot connect to the Docker daemon"

**Symptoms:**
- Error: "Cannot connect to the Docker daemon at unix:///var/run/docker.sock"
- Docker commands fail with connection errors

**Solutions:**

1. **Check if Docker Desktop is running:**
   ```bash
   # Linux
   ps aux | grep -i docker

   # macOS
   pgrep -x Docker
   ```

2. **Check Docker socket permissions:**
   ```bash
   ls -la /var/run/docker.sock
   sudo chmod 666 /var/run/docker.sock  # Temporary fix
   ```

3. **Add user to docker group (Linux):**
   ```bash
   sudo usermod -aG docker $USER
   # Log out and back in for changes to take effect
   newgrp docker  # Or use this to avoid logging out
   ```

4. **Check Docker context:**
   ```bash
   docker context ls
   docker context use default
   ```

### Issue 3: Virtualization Not Available (Linux)

**Symptoms:**
- Error: "KVM is not available"
- Error: "/dev/kvm not found"
- Docker Desktop fails to start with virtualization errors

**Solutions:**

1. **Check CPU virtualization support:**
   ```bash
   egrep -c '(vmx|svm)' /proc/cpuinfo
   # Should return a number > 0
   ```

2. **Enable virtualization in BIOS:**
   - Restart computer
   - Enter BIOS/UEFI settings (usually F2, F10, Del key)
   - Find and enable "Intel VT-x" or "AMD-V"
   - Save and exit

3. **Install and load KVM modules:**
   ```bash
   # Ubuntu/Debian
   sudo apt install qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils

   # Load KVM module
   sudo modprobe kvm
   sudo modprobe kvm_intel  # For Intel CPUs
   # OR
   sudo modprobe kvm_amd    # For AMD CPUs

   # Check if loaded
   lsmod | grep kvm
   ```

4. **Add user to kvm group:**
   ```bash
   sudo usermod -aG kvm $USER
   # Log out and back in
   ```

5. **Check /dev/kvm permissions:**
   ```bash
   ls -la /dev/kvm
   sudo chmod 666 /dev/kvm  # If needed
   ```

### Issue 4: High CPU or Memory Usage

**Symptoms:**
- Docker Desktop consuming 100% CPU
- System becomes slow when Docker is running
- High memory usage

**Solutions:**

1. **Check which containers are using resources:**
   ```bash
   docker stats
   docker ps -a
   ```

2. **Stop unnecessary containers:**
   ```bash
   docker stop $(docker ps -q)
   docker container prune
   ```

3. **Adjust Docker Desktop resource limits:**
   - Docker Desktop → Settings → Resources
   - Reduce CPU cores or memory allocation
   - Recommended: 4 CPUs, 4-8GB RAM

4. **Check for runaway processes:**
   ```bash
   docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Size}}"
   ```

### Issue 5: Disk Space Issues

**Symptoms:**
- Error: "No space left on device"
- Docker Desktop slow or unresponsive
- Cannot pull images or create containers

**Solutions:**

1. **Check Docker disk usage:**
   ```bash
   docker system df
   docker system df -v  # Verbose output
   ```

2. **Clean up unused resources:**
   ```bash
   # Remove stopped containers
   docker container prune

   # Remove unused images
   docker image prune -a

   # Remove unused volumes
   docker volume prune

   # Remove everything unused
   docker system prune -a --volumes
   ```

3. **Increase disk allocation (Docker Desktop):**
   - Docker Desktop → Settings → Resources → Disk image size
   - Increase the limit (requires Docker Desktop restart)

4. **Move Docker data directory (Linux):**
   ```bash
   # Stop Docker
   sudo systemctl stop docker

   # Edit daemon.json
   sudo nano /etc/docker/daemon.json
   # Add: {"data-root": "/new/path/to/docker"}

   # Move data
   sudo rsync -aP /var/lib/docker/ /new/path/to/docker/

   # Start Docker
   sudo systemctl start docker
   ```

### Issue 6: Conflicting Docker Installations

**Symptoms:**
- Multiple Docker versions installed
- Docker commands point to wrong installation
- Unexpected Docker behavior

**Solutions:**

1. **Identify all Docker installations:**
   ```bash
   which -a docker
   dpkg -l | grep docker    # Debian/Ubuntu
   rpm -qa | grep docker    # RHEL/Fedora
   snap list | grep docker  # Snap
   ```

2. **Remove conflicting installations:**
   ```bash
   # Remove docker.io (old package)
   sudo apt remove docker docker.io containerd runc

   # Remove snap version
   sudo snap remove docker

   # Keep only Docker Desktop or only docker-ce
   ```

3. **Clean up Docker contexts:**
   ```bash
   docker context ls
   docker context rm <unwanted-context>
   docker context use default
   ```

### Issue 7: Network Issues

**Symptoms:**
- Containers cannot reach the internet
- DNS resolution fails in containers
- Port mapping not working

**Solutions:**

1. **Check Docker networks:**
   ```bash
   docker network ls
   docker network inspect bridge
   ```

2. **Test container connectivity:**
   ```bash
   docker run --rm alpine ping -c 4 8.8.8.8
   docker run --rm alpine nslookup google.com
   ```

3. **Reset Docker networking:**
   ```bash
   docker network prune
   # Restart Docker Desktop
   ```

4. **Configure DNS (Linux):**
   ```bash
   # Edit /etc/docker/daemon.json
   sudo nano /etc/docker/daemon.json
   ```

   Add:
   ```json
   {
     "dns": ["8.8.8.8", "8.8.4.4"]
   }
   ```

5. **Check firewall settings:**
   ```bash
   sudo ufw status
   sudo iptables -L -n
   ```

## Platform-Specific Issues

### Linux

**Docker Desktop vs docker-ce:**
- Docker Desktop for Linux is different from docker-ce
- They can conflict if both are installed
- Choose one and remove the other

**Systemd issues:**
- Check: `systemctl status docker`
- Restart: `systemctl restart docker`
- Enable on boot: `systemctl enable docker`

**AppArmor/SELinux:**
- May block Docker operations
- Check logs: `sudo ausearch -m avc -ts recent`
- May need to adjust security policies

### macOS

**Rosetta 2 (Apple Silicon):**
- Required for Intel-based containers on M1/M2 Macs
- Install: `softwareupdate --install-rosetta`

**File sharing:**
- Check Docker Desktop → Settings → Resources → File sharing
- Add directories that need to be mounted

**macOS updates:**
- Docker Desktop may break after macOS updates
- Reinstall Docker Desktop if needed

### Windows/WSL2

**WSL2 backend:**
- Ensure WSL2 is installed and updated
- Check: `wsl --status`
- Update: `wsl --update`

**Hyper-V:**
- Required for Docker Desktop on Windows
- Enable via Windows Features

**File permissions:**
- Windows file permissions can cause issues in containers
- Use WSL2 filesystem for better performance

## Getting More Help

### Sharing Diagnostic Information

When asking for help, provide the log file:

```bash
./scripts/docker-desktop-troubleshoot.sh --save-logs
```

This creates a timestamped log file with all diagnostic information.

### Official Resources

- **Docker Desktop Documentation:** https://docs.docker.com/desktop/
- **Docker Desktop Troubleshooting:** https://docs.docker.com/desktop/troubleshoot/
- **Docker Forums:** https://forums.docker.com/
- **Docker GitHub Issues:** https://github.com/docker/for-linux/issues (Linux)
  - https://github.com/docker/for-mac/issues (macOS)
  - https://github.com/docker/for-win/issues (Windows)

### Docker Support Logs

Docker Desktop has a built-in diagnostics tool:

1. Open Docker Desktop
2. Click the bug icon (🐛) in the top toolbar
3. Click "Get support"
4. Click "Gather diagnostics"
5. Share the diagnostic ID when seeking support

## Prevention and Best Practices

### Regular Maintenance

1. **Clean up regularly:**
   ```bash
   # Weekly cleanup
   docker system prune -f

   # Monthly deep clean
   docker system prune -a --volumes
   ```

2. **Monitor disk usage:**
   ```bash
   docker system df
   ```

3. **Keep Docker updated:**
   - Enable auto-updates in Docker Desktop settings
   - Or manually update regularly

### Resource Management

1. **Set reasonable limits:**
   - CPUs: 4-6 cores for most workloads
   - Memory: 4-8GB for most workloads
   - Disk: At least 20GB free space

2. **Use .dockerignore:**
   - Reduce build context size
   - Faster builds and smaller images

3. **Multi-stage builds:**
   - Smaller final images
   - Better use of build cache

### Security

1. **Keep Docker group membership minimal:**
   - Docker group = root access
   - Only add trusted users

2. **Regular security updates:**
   - Update Docker Desktop
   - Update base images

3. **Scan images:**
   ```bash
   docker scan <image-name>
   ```

## Troubleshooting Checklist

Use this checklist when troubleshooting:

- [ ] Is Docker Desktop running?
- [ ] Is the Docker daemon responding?
- [ ] Do I have enough disk space? (>10GB free)
- [ ] Do I have enough memory? (>4GB available)
- [ ] Is virtualization enabled in BIOS?
- [ ] Am I in the docker/kvm groups?
- [ ] Are there conflicting Docker installations?
- [ ] Have I checked the logs?
- [ ] Have I tried restarting Docker Desktop?
- [ ] Is my Docker Desktop version up to date?
- [ ] Have I checked for OS updates?

## Emergency Reset

If all else fails, completely reset Docker Desktop:

```bash
# Linux
docker system prune -a --volumes
rm -rf ~/.docker/desktop
# Reinstall Docker Desktop

# macOS
# Uninstall Docker Desktop
# Remove data: rm -rf ~/Library/Containers/com.docker.docker
# Reinstall Docker Desktop

# Windows
# Uninstall Docker Desktop from Settings
# Reinstall Docker Desktop
```

**Warning:** This removes all containers, images, volumes, and settings.

---

**Last Updated:** October 2025

**Script Version:** 1.0

For issues or improvements to this guide, please open an issue in the repository.
