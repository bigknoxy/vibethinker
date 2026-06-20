#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_OWNER="REPO_OWNER"
REPO_NAME="REPO_NAME"
RAW_BASE="https://raw.githubusercontent.com/${REPO_OWNER}/${REPO_NAME}/main"
INSTALL_DIR="/opt/vibethinker"
BIN_PATH="/usr/local/bin/vibe"
SERVICE_NAME="vibethinker"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
MODELS_DIR="${INSTALL_DIR}/models"

REPO_FILES=(
  "vibecli.py"
  "server.py"
  "worker.py"
  "watchdog.py"
)

usage() {
    cat <<EOF
VibeThinker Installer

Usage: $0 [OPTIONS]

Options:
  --install     Install VibeThinker (default)
  --uninstall   Remove VibeThinker
  --help        Show this help message

Examples:
  curl -sL https://vibethinker.dev/install.sh | bash
  curl -sL https://vibethinker.dev/install.sh | bash -s -- --uninstall
EOF
    exit 0
}

log_success() { echo -e "${GREEN}[✓] $1${NC}"; }
log_error()   { echo -e "${RED}[✗] $1${NC}"; }
log_info()    { echo -e "${YELLOW}[i] $1${NC}"; }
log_step()    { echo -e "\n${GREEN}==>${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)."
        exit 1
    fi
}

check_deps() {
    local missing=0
    for cmd in curl python3 pip3; do
        if ! command -v "$cmd" &>/dev/null; then
            log_error "Required command not found: ${cmd}"
            missing=1
        fi
    done
    if [[ $missing -eq 1 ]]; then
        exit 1
    fi
    log_success "All required commands available."
}

detect_platform() {
    local os arch
    os=$(uname -s | tr '[:upper:]' '[:lower:]')
    arch=$(uname -m)
    case "$arch" in
        x86_64)  arch="amd64" ;;
        aarch64) arch="arm64"  ;;
        armv7l)  arch="armv7"  ;;
    esac
    if [[ "$os" != "linux" ]]; then
        log_error "Unsupported OS: ${os} (only Linux is supported)."
        exit 1
    fi
    log_success "Platform: ${os}/${arch}"
}

check_python() {
    local py_version major minor
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
    IFS='.' read -r major minor _ <<< "$py_version"
    if [[ "$major" -lt 3 ]] || { [[ "$major" -eq 3 ]] && [[ "$minor" -lt 10 ]]; }; then
        log_error "Python 3.10+ required (found ${py_version})."
        exit 1
    fi
    log_success "Python ${py_version} detected."
}

check_llama_cpp() {
    log_info "Checking llama-cpp-python..."
    if python3 -c "import llama_cpp" 2>/dev/null; then
        log_success "llama-cpp-python is already installed."
        return
    fi
    log_info "Installing llama-cpp-python via pip..."
    pip3 install llama-cpp-python --break-system-packages 2>/dev/null || pip3 install llama-cpp-python
    log_success "llama-cpp-python installed."
}

download_files() {
    log_step "Downloading VibeThinker files..."
    mkdir -p "$INSTALL_DIR"
    for file in "${REPO_FILES[@]}"; do
        local url="${RAW_BASE}/${file}"
        log_info "Downloading ${file}..."
        if curl -sL --fail -o "${INSTALL_DIR}/${file}" "$url"; then
            chmod 755 "${INSTALL_DIR}/${file}"
            log_success "Downloaded ${file}"
        else
            log_error "Failed to download ${file} from ${url}"
            exit 1
        fi
    done
    log_success "All files saved to ${INSTALL_DIR}/"
}

install_symlink() {
    log_step "Installing vibe CLI symlink..."
    if [[ -f "$BIN_PATH" ]] && [[ ! -L "$BIN_PATH" ]]; then
        log_info "Backing up existing file at ${BIN_PATH} to ${BIN_PATH}.bak"
        mv "$BIN_PATH" "${BIN_PATH}.bak"
    fi
    ln -sf "${INSTALL_DIR}/vibecli.py" "$BIN_PATH"
    chmod +x "${INSTALL_DIR}/vibecli.py"
    log_success "Symlink: ${BIN_PATH} -> ${INSTALL_DIR}/vibecli.py"
}

install_systemd() {
    log_step "Setting up systemd service..."
    local svc_url="${RAW_BASE}/vibethinker.service"
    if ! curl -sL --fail -o "$SERVICE_FILE" "$svc_url" 2>/dev/null; then
        log_info "Using embedded systemd service template."
        cat > "$SERVICE_FILE" << 'SERVICE'
[Unit]
Description=VibeThinker Model Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/vibethinker
ExecStart=/usr/bin/python3 /opt/vibethinker/server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1

[Install]
WantedBy=multi-user.target
SERVICE
    else
        log_success "Downloaded systemd service file from repo."
    fi
    chmod 644 "$SERVICE_FILE"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME" 2>/dev/null || systemctl start "$SERVICE_NAME" 2>/dev/null || \
        log_info "Server will start on next boot (enabled)."
    log_success "Systemd service '${SERVICE_NAME}' installed and enabled."
}

install() {
    log_step "Starting VibeThinker installation..."
    check_root
    check_deps
    detect_platform
    check_python
    check_llama_cpp
    download_files
    install_symlink
    install_systemd

    echo ""
    log_success "VibeThinker installed."
    echo ""
    echo "  Run:        vibe prompt 'hello'"
    echo "  Start:      sudo systemctl start vibethinker"
    echo "  Status:     sudo systemctl status vibethinker"
    echo "  Logs:       sudo journalctl -u vibethinker -f"
}

uninstall() {
    log_step "Starting VibeThinker uninstallation..."
    check_root

    if systemctl list-units --full -all 2>/dev/null | grep -q "$SERVICE_NAME"; then
        log_info "Stopping and disabling systemd service..."
        systemctl stop "$SERVICE_NAME" 2>/dev/null || true
        systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        log_success "Service stopped and disabled."
    fi

    if [[ -f "$SERVICE_FILE" ]]; then
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        log_success "Removed systemd service file."
    fi

    if [[ -L "$BIN_PATH" ]]; then
        rm -f "$BIN_PATH"
        log_success "Removed symlink: ${BIN_PATH}"
    fi

    local gguf_files=()
    if [[ -d "$MODELS_DIR" ]]; then
        while IFS= read -r -d '' f; do
            gguf_files+=("$f")
        done < <(find "$MODELS_DIR" -name '*.gguf' -print0 2>/dev/null || true)
    fi

    if [[ ${#gguf_files[@]} -gt 0 ]]; then
        echo ""
        log_info "GGUF model files found:"
        for f in "${gguf_files[@]}"; do
            echo "  ${f}"
        done
        local response="n"
        if [[ -t 0 ]]; then
            read -r -p "Remove model files? [y/N] " response
        else
            read -r -p "Remove model files? [y/N] " response < /dev/tty 2>/dev/null || response="n"
        fi
        if [[ "$response" =~ ^[yY] ]]; then
            rm -f "${gguf_files[@]}"
            log_success "Model files removed."
        else
            log_info "Model files kept."
        fi
    fi

    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        log_success "Removed ${INSTALL_DIR}/"
    fi

    echo ""
    log_success "VibeThinker uninstalled."
}

main() {
    case "${1:-}" in
        --install|"")
            install
            ;;
        --uninstall)
            uninstall
            ;;
        --help|-h)
            usage
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--install|--uninstall|--help]"
            exit 1
            ;;
    esac
}

main "$@"
