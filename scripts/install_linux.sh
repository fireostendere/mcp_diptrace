#!/usr/bin/env bash
set -euo pipefail

PRODUCT="DipTrace MCP"
MCP_VERSION="${DIPTRACE_MCP_VERSION:-0.4.0}"
MCP_BUNDLE_NAME="DipTrace-MCP-Portable-${MCP_VERSION}.zip"
MCP_RELEASE_BASE="https://github.com/fireostendere/mcp_diptrace/releases/download/v${MCP_VERSION}"
MCP_BUNDLE_URL="${MCP_RELEASE_BASE}/${MCP_BUNDLE_NAME}"
MCP_SUMS_URL="${MCP_RELEASE_BASE}/SHA256SUMS.txt"
LOCAL_MCP_BUNDLE="${DIPTRACE_MCP_BUNDLE_PATH:-}"
DIPTRACE_VERSION="5.3.0.3"
DIPTRACE_INSTALLER_URL="https://diptrace.com/downloads/dipfree_en64.exe"
DIPTRACE_INSTALLER_SHA256="87a9d4cb14e01b0561d6a88d540a5775d92d011359b465d12c7c5d0f0e527e74"

ACCEPT_DIPTRACE_LICENSE=0
SKIP_DIPTRACE=0
FORCE_DIPTRACE=0
INSTALL_DESKTOP=1

usage() {
    cat <<'EOF'
Install DipTrace Freeware and DipTrace MCP into one isolated Wine prefix.

Usage:
  install_linux.sh --accept-diptrace-license [options]

Options:
  --accept-diptrace-license  Required for unattended installation of DipTrace.
                             Review DipTrace's license before using this flag.
  --skip-diptrace            Do not download/install DipTrace; require it to
                             already exist in the selected Wine prefix.
  --force-diptrace           Re-run the pinned DipTrace installer even when the
                             expected executables already exist.
  --no-desktop               Do not create Linux desktop launchers.
  -h, --help                 Show this help.

Environment overrides:
  DIPTRACE_MCP_WINEPREFIX       Wine prefix location.
  DIPTRACE_MCP_LINUX_DATA_ROOT  Runtime/data root.
  DIPTRACE_MCP_LINUX_WORKSPACE  Default MCP workspace.
  DIPTRACE_MCP_LINUX_STATE_DIR  MCP state directory.
  DIPTRACE_MCP_LINUX_BIN_DIR    Wrapper installation directory.
  DIPTRACE_MCP_BUNDLE_PATH      Local portable ZIP for CI/pre-release testing.
  DIPTRACE_MCP_HEADLESS_SCREEN  Private headless display, default 1920x1080x24.
EOF
}

log() {
    printf '[diptrace-mcp] %s\n' "$*"
}

fail() {
    printf '[diptrace-mcp] ERROR: %s\n' "$*" >&2
    exit 1
}

while (($#)); do
    case "$1" in
        --accept-diptrace-license)
            ACCEPT_DIPTRACE_LICENSE=1
            ;;
        --skip-diptrace)
            SKIP_DIPTRACE=1
            ;;
        --force-diptrace)
            FORCE_DIPTRACE=1
            ;;
        --no-desktop)
            INSTALL_DESKTOP=0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
    shift
done

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    fail "run this installer as a regular desktop user; it invokes sudo only for OS packages"
fi

case "$(uname -s)" in
    Linux) ;;
    *) fail "this installer is for Linux" ;;
esac

[[ "$(uname -m)" == "x86_64" ]] || fail "only x86_64 Linux is validated for the Wine deployment"
command -v apt-get >/dev/null 2>&1 || fail "this installer currently supports Debian/Ubuntu apt-based systems"
command -v dpkg >/dev/null 2>&1 || fail "dpkg is required"
command -v sudo >/dev/null 2>&1 || fail "sudo is required to install Wine dependencies"

DATA_ROOT="${DIPTRACE_MCP_LINUX_DATA_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/diptrace-mcp}"
WINEPREFIX="${DIPTRACE_MCP_WINEPREFIX:-$DATA_ROOT/wineprefix}"
RUNTIME_ROOT="$DATA_ROOT/runtime"
RUNTIME_VERSION="$RUNTIME_ROOT/$MCP_VERSION"
CURRENT_RUNTIME="$RUNTIME_ROOT/current"
WORKSPACE="${DIPTRACE_MCP_LINUX_WORKSPACE:-$HOME/DipTrace}"
STATE_DIR="${DIPTRACE_MCP_LINUX_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/diptrace-mcp}"
BIN_DIR="${DIPTRACE_MCP_LINUX_BIN_DIR:-$HOME/.local/bin}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/diptrace-mcp"
DIPTRACE_DIR="$WINEPREFIX/drive_c/Program Files/DipTrace"
HEADLESS_HELPER="$CURRENT_RUNTIME/app/tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe"

export WINEPREFIX
export WINEARCH=win64
export WINEDEBUG=-all
# Suppress Wine's interactive Mono/Gecko installer prompts. DipTrace MCP does not
# depend on those runtimes.
export WINEDLLOVERRIDES='mscoree,mshtml='

mkdir -p "$DATA_ROOT" "$RUNTIME_ROOT" "$WORKSPACE" "$STATE_DIR" "$BIN_DIR" "$CACHE_DIR"

log "installing validated Wine and GUI dependencies through apt"
if ! dpkg --print-foreign-architectures | grep -qx i386; then
    sudo dpkg --add-architecture i386
fi
sudo apt-get update
DEBIAN_FRONTEND=noninteractive sudo apt-get install -y --no-install-recommends \
    wine wine64 wine32:i386 \
    xvfb xauth unzip curl ca-certificates fonts-wine \
    libgl1 libgl1:i386 \
    libgl1-mesa-dri libgl1-mesa-dri:i386 \
    libsdl2-2.0-0 libsdl2-2.0-0:i386 \
    libvulkan1 libvulkan1:i386 \
    libxcomposite1 libxcomposite1:i386 \
    libxcursor1 libxcursor1:i386 \
    libxfixes3 libxfixes3:i386 \
    libxi6 libxi6:i386 \
    libxinerama1 libxinerama1:i386 \
    libxrandr2 libxrandr2:i386 \
    libxrender1 libxrender1:i386 \
    libxxf86vm1 libxxf86vm1:i386

for command_name in wine wineboot winepath wineserver xvfb-run unzip curl sha256sum realpath; do
    command -v "$command_name" >/dev/null 2>&1 || fail "required command was not installed: $command_name"
done

log "Wine: $(wine --version)"

run_with_display() {
    if [[ -n "${DISPLAY:-}" ]]; then
        "$@"
    else
        xvfb-run -a -s '-screen 0 1920x1080x24 -nolisten tcp' "$@"
    fi
}

if [[ ! -f "$WINEPREFIX/system.reg" ]]; then
    log "initializing isolated Wine prefix: $WINEPREFIX"
    run_with_display wineboot -u
    wineserver -k || true
fi

sha256_file() {
    sha256sum "$1" | awk '{print $1}'
}

download_pinned() {
    local url="$1"
    local output="$2"
    local expected_sha="$3"
    local label="$4"
    local actual_sha=""

    if [[ -f "$output" ]]; then
        actual_sha="$(sha256_file "$output")"
    fi
    if [[ "$actual_sha" != "$expected_sha" ]]; then
        rm -f "$output"
        log "downloading $label"
        curl --fail --location --retry 3 --proto '=https' --tlsv1.2 "$url" --output "$output"
        actual_sha="$(sha256_file "$output")"
    fi
    if [[ "$actual_sha" != "$expected_sha" ]]; then
        rm -f "$output"
        fail "$label SHA-256 mismatch: expected $expected_sha, got $actual_sha"
    fi
}

have_diptrace=1
for executable in Pcb.exe Schematic.exe CompEdit.exe PattEdit.exe; do
    [[ -f "$DIPTRACE_DIR/$executable" ]] || have_diptrace=0
done

if ((SKIP_DIPTRACE)); then
    ((have_diptrace)) || fail "--skip-diptrace was requested but DipTrace is incomplete in $DIPTRACE_DIR"
elif ((!have_diptrace || FORCE_DIPTRACE)); then
    ((ACCEPT_DIPTRACE_LICENSE)) || fail "unattended DipTrace installation requires --accept-diptrace-license"
    installer="$CACHE_DIR/dipfree_en64-${DIPTRACE_VERSION}.exe"
    download_pinned "$DIPTRACE_INSTALLER_URL" "$installer" "$DIPTRACE_INSTALLER_SHA256" "DipTrace Freeware $DIPTRACE_VERSION"
    log "installing DipTrace Freeware $DIPTRACE_VERSION into the isolated Wine prefix"
    run_with_display wine "$installer" /silent /hide
    wineserver -k || true
    for executable in Pcb.exe Schematic.exe CompEdit.exe PattEdit.exe; do
        [[ -f "$DIPTRACE_DIR/$executable" ]] || fail "DipTrace installer did not create $DIPTRACE_DIR/$executable"
    done
else
    log "DipTrace is already installed in the isolated Wine prefix"
fi

bundle="$CACHE_DIR/$MCP_BUNDLE_NAME"
if [[ -n "$LOCAL_MCP_BUNDLE" ]]; then
    cp "$LOCAL_MCP_BUNDLE" "$bundle"
else
    sums="$CACHE_DIR/SHA256SUMS-${MCP_VERSION}.txt"
    log "downloading DipTrace MCP $MCP_VERSION release checksum manifest"
    curl --fail --location --retry 3 --proto '=https' --tlsv1.2 "$MCP_SUMS_URL" --output "$sums"
    expected_bundle_sha="$(tr -d '\r' < "$sums" | awk -v f="$MCP_BUNDLE_NAME" '$2 == f || $2 == "*" f {print $1; exit}')"
    [[ "$expected_bundle_sha" =~ ^[0-9a-fA-F]{64}$ ]] || fail "release checksum manifest does not contain $MCP_BUNDLE_NAME"
    download_pinned "$MCP_BUNDLE_URL" "$bundle" "$expected_bundle_sha" "DipTrace MCP $MCP_VERSION portable bundle"
fi

staging="$RUNTIME_ROOT/.${MCP_VERSION}.staging.$$"
rm -rf "$staging"
mkdir -p "$staging"
unzip -q "$bundle" -d "$staging"
for required in \
    app/diptrace_mcp_server.exe \
    app/tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe \
    bridge/diptrace_mcp_bridge.exe \
    settings-templates/pcb.settings.xml \
    settings-templates/schematic.settings.xml \
    settings-templates/component.settings.xml \
    settings-templates/pattern.settings.xml \
    SHA256SUMS.txt; do
    [[ -f "$staging/$required" ]] || fail "portable bundle is missing $required"
done
(
    cd "$staging"
    sha256sum -c SHA256SUMS.txt >/dev/null
) || fail "portable bundle internal checksum verification failed"
rm -rf "$RUNTIME_VERSION"
mv "$staging" "$RUNTIME_VERSION"
ln -sfn "$RUNTIME_VERSION" "$CURRENT_RUNTIME"

install_plugin_for_module() {
    local module="$1"
    local template="$2"
    local target="$DIPTRACE_DIR/Plugins/$module/DipTraceMCP"
    mkdir -p "$target"
    install -m 0644 "$CURRENT_RUNTIME/settings-templates/$template" "$target/settings.xml"
    install -m 0755 "$CURRENT_RUNTIME/bridge/diptrace_mcp_bridge.exe" "$target/diptrace_mcp_bridge.exe"
}

install_plugin_for_module Pcb pcb.settings.xml
install_plugin_for_module Schematic schematic.settings.xml
install_plugin_for_module CompEdit component.settings.xml
install_plugin_for_module PattEdit pattern.settings.xml

write_runtime_wrapper() {
    local output="$1"
    local windows_executable="$2"
    cat >"$output" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export WINEPREFIX=$(printf '%q' "$WINEPREFIX")
export WINEARCH=win64
export WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
WORKSPACE_LINUX=\${DIPTRACE_MCP_LINUX_WORKSPACE:-$(printf '%q' "$WORKSPACE")}
STATE_LINUX=\${DIPTRACE_MCP_LINUX_STATE_DIR:-$(printf '%q' "$STATE_DIR")}
mkdir -p "\$WORKSPACE_LINUX" "\$STATE_LINUX"
win_workspace=\$(winepath -w "\$WORKSPACE_LINUX" | tr -d '\r')
win_state=\$(winepath -w "\$STATE_LINUX" | tr -d '\r')
win_profile=\$(wine cmd /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')
export DIPTRACE_MCP_WORKSPACE="\$win_workspace"
export DIPTRACE_MCP_STATE_DIR="\$win_state"
export DIPTRACE_MCP_ALLOWED_ROOTS="\$win_workspace;\$win_profile"
exec wine $(printf '%q' "$windows_executable") "\$@"
EOF
    chmod 0755 "$output"
}

write_runtime_wrapper "$BIN_DIR/diptrace-mcp" "$CURRENT_RUNTIME/app/diptrace_mcp_server.exe"
write_runtime_wrapper "$BIN_DIR/diptrace-mcp-bridge" "$CURRENT_RUNTIME/bridge/diptrace_mcp_bridge.exe"
write_runtime_wrapper "$BIN_DIR/diptrace-pcb" "$DIPTRACE_DIR/Pcb.exe"
write_runtime_wrapper "$BIN_DIR/diptrace-schematic" "$DIPTRACE_DIR/Schematic.exe"
write_runtime_wrapper "$BIN_DIR/diptrace-component-editor" "$DIPTRACE_DIR/CompEdit.exe"
write_runtime_wrapper "$BIN_DIR/diptrace-pattern-editor" "$DIPTRACE_DIR/PattEdit.exe"

cat >"$BIN_DIR/diptrace-gui-headless" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export WINEPREFIX=$(printf '%q' "$WINEPREFIX")
export WINEARCH=win64
export WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
HELPER=$(printf '%q' "$HEADLESS_HELPER")
DIPTRACE_ROOT_LINUX=$(printf '%q' "$DIPTRACE_DIR")
WORKSPACE_LINUX=\${DIPTRACE_MCP_LINUX_WORKSPACE:-$(printf '%q' "$WORKSPACE")}
STATE_LINUX=\${DIPTRACE_MCP_LINUX_STATE_DIR:-$(printf '%q' "$STATE_DIR")}
SCREEN=\${DIPTRACE_MCP_HEADLESS_SCREEN:-1920x1080x24}

fail() {
    printf 'diptrace-gui-headless: %s\n' "\$*" >&2
    exit 2
}

[[ "\$SCREEN" =~ ^[0-9]+x[0-9]+x(16|24|32)$ ]] || fail "invalid DIPTRACE_MCP_HEADLESS_SCREEN: \$SCREEN"
[[ -f "\$HELPER" ]] || fail "headless GUI helper is missing: \$HELPER"
mkdir -p "\$WORKSPACE_LINUX" "\$STATE_LINUX"
win_workspace=\$(winepath -w "\$WORKSPACE_LINUX" | tr -d '\r')
win_state=\$(winepath -w "\$STATE_LINUX" | tr -d '\r')
win_profile=\$(wine cmd /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')
export DIPTRACE_MCP_WORKSPACE="\$win_workspace"
export DIPTRACE_MCP_STATE_DIR="\$win_state"
export DIPTRACE_MCP_ALLOWED_ROOTS="\$win_workspace;\$win_profile"

args=("\$@")
if [[ "\${1:-}" == "roundtrip" ]]; then
    converted=("roundtrip")
    project_seen=0
    i=1
    while ((i < \${#args[@]})); do
        arg="\${args[i]}"
        case "\$arg" in
            --project)
                ((i + 1 < \${#args[@]})) || fail "--project requires a Linux path"
                project_linux=\$(realpath -e "\${args[i+1]}") || fail "project does not exist: \${args[i+1]}"
                project_win=\$(winepath -w "\$project_linux" | tr -d '\r')
                converted+=(--project "\$project_win")
                project_seen=1
                ((i += 2))
                ;;
            --project=*)
                project_raw="\${arg#--project=}"
                project_linux=\$(realpath -e "\$project_raw") || fail "project does not exist: \$project_raw"
                project_win=\$(winepath -w "\$project_linux" | tr -d '\r')
                converted+=(--project "\$project_win")
                project_seen=1
                ((i += 1))
                ;;
            --desktop|--desktop=*|--diptrace-root|--diptrace-root=*)
                fail "\$arg is managed by the Linux headless wrapper"
                ;;
            *)
                converted+=("\$arg")
                ((i += 1))
                ;;
        esac
    done
    ((project_seen)) || fail "roundtrip requires --project with a Linux path"
    diptrace_root_win=\$(winepath -w "\$DIPTRACE_ROOT_LINUX" | tr -d '\r')
    converted+=(--diptrace-root "\$diptrace_root_win" --desktop native)
    args=("\${converted[@]}")
elif [[ "\${1:-}" == "smoke" ]]; then
    fail "Linux isolation is provided by private Xvfb; use native-smoke"
fi

exec xvfb-run -a -s "-screen 0 \$SCREEN -nolisten tcp" wine "\$HELPER" "\${args[@]}"
EOF
chmod 0755 "$BIN_DIR/diptrace-gui-headless"

cat >"$BIN_DIR/diptrace-mcp-doctor" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export WINEPREFIX=$(printf '%q' "$WINEPREFIX")
export WINEARCH=win64
export WINEDEBUG=-all
export WINEDLLOVERRIDES='mscoree,mshtml='
failures=0
check_file() {
    if [[ -f "\$1" ]]; then
        printf 'PASS  %s\n' "\$2"
    else
        printf 'FAIL  %s: %s\n' "\$2" "\$1" >&2
        failures=1
    fi
}
printf 'Wine: %s\n' "\$(wine --version)"
check_file $(printf '%q' "$DIPTRACE_DIR/Pcb.exe") 'DipTrace PCB Layout'
check_file $(printf '%q' "$DIPTRACE_DIR/Schematic.exe") 'DipTrace Schematic'
check_file $(printf '%q' "$CURRENT_RUNTIME/app/diptrace_mcp_server.exe") 'MCP server'
check_file $(printf '%q' "$HEADLESS_HELPER") 'Headless GUI worker'
check_file $(printf '%q' "$DIPTRACE_DIR/Plugins/Pcb/DipTraceMCP/diptrace_mcp_bridge.exe") 'PCB bridge plug-in'
check_file $(printf '%q' "$DIPTRACE_DIR/Plugins/Schematic/DipTraceMCP/diptrace_mcp_bridge.exe") 'Schematic bridge plug-in'
if ((failures)); then exit 1; fi
$(printf '%q' "$BIN_DIR/diptrace-mcp") --version
$(printf '%q' "$BIN_DIR/diptrace-mcp-bridge") --help >/dev/null
printf 'PASS  MCP server and bridge executables start under Wine\n'
$(printf '%q' "$BIN_DIR/diptrace-gui-headless") native-smoke --timeout 20 >/dev/null
printf 'PASS  private-Xvfb Win32 GUI worker\n'
EOF
chmod 0755 "$BIN_DIR/diptrace-mcp-doctor"

if ((INSTALL_DESKTOP)); then
    applications_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$applications_dir"
    write_desktop_entry() {
        local file="$1"
        local name="$2"
        local command="$3"
        cat >"$applications_dir/$file" <<EOF
[Desktop Entry]
Type=Application
Name=$name
Exec=$command
Terminal=false
Categories=Development;Electronics;
EOF
    }
    write_desktop_entry diptrace-pcb.desktop "DipTrace PCB Layout" "$BIN_DIR/diptrace-pcb"
    write_desktop_entry diptrace-schematic.desktop "DipTrace Schematic" "$BIN_DIR/diptrace-schematic"
    write_desktop_entry diptrace-component-editor.desktop "DipTrace Component Editor" "$BIN_DIR/diptrace-component-editor"
    write_desktop_entry diptrace-pattern-editor.desktop "DipTrace Pattern Editor" "$BIN_DIR/diptrace-pattern-editor"
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$applications_dir" >/dev/null 2>&1 || true
    fi
fi

log "running installation doctor"
"$BIN_DIR/diptrace-mcp-doctor"

cat <<EOF

$PRODUCT installation complete.

Commands:
  $BIN_DIR/diptrace-mcp
  $BIN_DIR/diptrace-mcp-doctor
  $BIN_DIR/diptrace-schematic
  $BIN_DIR/diptrace-pcb
  $BIN_DIR/diptrace-gui-headless

Visible GUI uses the current Linux DISPLAY. Headless GUI creates a private Xvfb
server with TCP disabled and runs the same Win32 automation worker inside Wine.

Wine prefix: $WINEPREFIX
MCP runtime: $CURRENT_RUNTIME
Workspace:   $WORKSPACE
State:       $STATE_DIR

If $BIN_DIR is not on PATH, add it to your shell PATH before configuring an MCP client.
EOF
