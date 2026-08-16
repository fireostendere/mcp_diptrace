#!/usr/bin/env bash
set -euo pipefail

REPO="${DIPTRACE_MCP_REPOSITORY:-fireostendere/mcp_diptrace}"
MCP_VERSION="${DIPTRACE_MCP_VERSION:-0.4.0}"
DIPTRACE_VERSION="${DIPTRACE_VERSION:-5.3.0.3}"
DIPTRACE_DMG_URL="${DIPTRACE_DMG_URL:-https://diptrace.com/downloads/DipTrace.dmg}"
DIPTRACE_DMG_SHA256="${DIPTRACE_DMG_SHA256:-c70ff54786ac4301a0b70aae37800ba30f14f77d40cd441aa8c54635ba9d88d4}"
APP_PATH="${DIPTRACE_APP_PATH:-$HOME/Applications/DipTrace.app}"
INSTALL_ROOT="${DIPTRACE_MCP_INSTALL_ROOT:-$HOME/Library/Application Support/DipTrace MCP}"
RUNTIME_ROOT="$INSTALL_ROOT/runtime"
WORKSPACE="${DIPTRACE_MCP_WORKSPACE:-$HOME/DipTrace}"
STATE_DIR="${DIPTRACE_MCP_STATE_DIR:-$INSTALL_ROOT/state}"
BIN_DIR="${DIPTRACE_MCP_BIN_DIR:-$HOME/.local/bin}"
CACHE_DIR="${DIPTRACE_MCP_CACHE_DIR:-$HOME/Library/Caches/DipTrace MCP}"
LOCAL_BUNDLE="${DIPTRACE_MCP_BUNDLE_PATH:-}"
LOCAL_DMG="${DIPTRACE_DMG_PATH:-}"
ACCEPT_DIPTRACE_LICENSE=0
ACCEPT_ROSETTA_LICENSE=0
SKIP_DIPTRACE=0

usage() {
  cat <<'EOF'
Usage: install_macos.sh [options]

Installs DipTrace MCP and the official DipTrace macOS application into user-owned
locations. The installed command wrappers use DipTrace's bundled Wine runtime,
so Homebrew Wine/XQuartz is not required.

Options:
  --accept-diptrace-license  Confirm that you accept the DipTrace license terms.
  --accept-rosetta-license   Allow installation of Rosetta when Apple Silicon needs it.
  --skip-diptrace            Reuse an existing DipTrace.app at DIPTRACE_APP_PATH.
  -h, --help                 Show this help.

Useful environment overrides:
  DIPTRACE_APP_PATH
  DIPTRACE_MCP_INSTALL_ROOT
  DIPTRACE_MCP_WORKSPACE
  DIPTRACE_MCP_STATE_DIR
  DIPTRACE_MCP_BIN_DIR
  DIPTRACE_MCP_BUNDLE_PATH    Local portable ZIP, used by CI/pre-release testing.
  DIPTRACE_DMG_PATH           Local official DMG, used by CI/idempotence testing.
EOF
}

while (($#)); do
  case "$1" in
    --accept-diptrace-license) ACCEPT_DIPTRACE_LICENSE=1 ;;
    --accept-rosetta-license) ACCEPT_ROSETTA_LICENSE=1 ;;
    --skip-diptrace) SKIP_DIPTRACE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

[[ "$(uname -s)" == "Darwin" ]] || { echo "This installer requires macOS." >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required." >&2; exit 1; }
command -v hdiutil >/dev/null || { echo "hdiutil is required." >&2; exit 1; }
command -v ditto >/dev/null || { echo "ditto is required." >&2; exit 1; }
command -v shasum >/dev/null || { echo "shasum is required." >&2; exit 1; }

if [[ "$SKIP_DIPTRACE" != "1" && "$ACCEPT_DIPTRACE_LICENSE" != "1" ]]; then
  cat >&2 <<'EOF'
DipTrace is third-party software with its own license terms.
Re-run with --accept-diptrace-license only after reviewing and accepting them.
EOF
  exit 2
fi

if [[ "$(uname -m)" == "arm64" ]]; then
  if ! arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
    if [[ "$ACCEPT_ROSETTA_LICENSE" != "1" ]]; then
      cat >&2 <<'EOF'
This DipTrace macOS build contains an x86_64 Wine runtime. Rosetta is required.
Review Apple's Rosetta license terms, then re-run with --accept-rosetta-license
to allow the installer to invoke Apple's supported Rosetta installer.
EOF
      exit 2
    fi
    echo "Installing Apple Rosetta..."
    /usr/sbin/softwareupdate --install-rosetta --agree-to-license
    arch -x86_64 /usr/bin/true >/dev/null 2>&1 || {
      echo "Rosetta installation did not make x86_64 execution available." >&2
      exit 1
    }
  fi
fi

mkdir -p "$INSTALL_ROOT" "$WORKSPACE" "$STATE_DIR" "$BIN_DIR" "$CACHE_DIR" "$(dirname "$APP_PATH")"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/diptrace-mcp-macos.XXXXXX")"
MOUNT_DIR="$TMP_DIR/dmg"
cleanup() {
  hdiutil detach "$MOUNT_DIR" -quiet >/dev/null 2>&1 || true
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

sha256_file() {
  shasum -a 256 "$1" | awk '{print $1}'
}

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

if [[ "$SKIP_DIPTRACE" != "1" ]]; then
  DMG="$TMP_DIR/DipTrace.dmg"
  if [[ -n "$LOCAL_DMG" ]]; then
    cp "$LOCAL_DMG" "$DMG"
  elif [[ -f "$CACHE_DIR/DipTrace-$DIPTRACE_VERSION.dmg" ]] && \
       [[ "$(sha256_file "$CACHE_DIR/DipTrace-$DIPTRACE_VERSION.dmg")" == "$DIPTRACE_DMG_SHA256" ]]; then
    cp "$CACHE_DIR/DipTrace-$DIPTRACE_VERSION.dmg" "$DMG"
  else
    echo "Downloading official DipTrace $DIPTRACE_VERSION DMG..."
    curl --fail --location --retry 3 --proto '=https' --tlsv1.2 "$DIPTRACE_DMG_URL" -o "$DMG"
  fi
  ACTUAL_DMG_SHA="$(sha256_file "$DMG")"
  [[ "$ACTUAL_DMG_SHA" == "$DIPTRACE_DMG_SHA256" ]] || {
    echo "DipTrace DMG SHA-256 mismatch: $ACTUAL_DMG_SHA" >&2
    exit 1
  }
  cp "$DMG" "$CACHE_DIR/DipTrace-$DIPTRACE_VERSION.dmg"

  mkdir -p "$MOUNT_DIR"
  hdiutil attach "$DMG" -nobrowse -readonly -mountpoint "$MOUNT_DIR" >/dev/null
  [[ -d "$MOUNT_DIR/DipTrace.app" ]] || { echo "DipTrace.app is missing from the official DMG." >&2; exit 1; }
  BUNDLE_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$MOUNT_DIR/DipTrace.app/Contents/Info.plist")"
  [[ "$BUNDLE_VERSION" == "$DIPTRACE_VERSION" ]] || {
    echo "Expected DipTrace $DIPTRACE_VERSION, DMG contains $BUNDLE_VERSION." >&2
    exit 1
  }
  rm -rf "$APP_PATH"
  ditto "$MOUNT_DIR/DipTrace.app" "$APP_PATH"
  hdiutil detach "$MOUNT_DIR" -quiet
fi

WINE="$APP_PATH/Contents/SharedSupport/wine/bin/wine"
PREFIX="$APP_PATH/Contents/SharedSupport/prefix"
DIPTRACE_ROOT="$PREFIX/drive_c/Program Files/DipTrace"
LIBINOTIFY="$APP_PATH/Contents/Frameworks/libinotify.0.dylib"
for required in "$WINE" "$LIBINOTIFY" "$DIPTRACE_ROOT/Schematic.exe" "$DIPTRACE_ROOT/Pcb.exe" "$DIPTRACE_ROOT/CompEdit.exe" "$DIPTRACE_ROOT/PattEdit.exe"; do
  [[ -e "$required" ]] || { echo "Required DipTrace runtime file is missing: $required" >&2; exit 1; }
done

BUNDLE_ZIP="$TMP_DIR/DipTrace-MCP-Portable-$MCP_VERSION.zip"
if [[ -n "$LOCAL_BUNDLE" ]]; then
  cp "$LOCAL_BUNDLE" "$BUNDLE_ZIP"
else
  RELEASE_BASE="https://github.com/$REPO/releases/download/v$MCP_VERSION"
  SUMS="$TMP_DIR/SHA256SUMS.txt"
  echo "Downloading DipTrace MCP v$MCP_VERSION portable runtime..."
  curl --fail --location --retry 3 --proto '=https' --tlsv1.2 "$RELEASE_BASE/SHA256SUMS.txt" -o "$SUMS"
  EXPECTED_BUNDLE_SHA="$(tr -d '\r' < "$SUMS" | awk -v f="DipTrace-MCP-Portable-$MCP_VERSION.zip" '$2 == f || $2 == "*" f {print $1; exit}')"
  [[ "$EXPECTED_BUNDLE_SHA" =~ ^[0-9a-fA-F]{64}$ ]] || {
    echo "Release checksum manifest does not contain DipTrace-MCP-Portable-$MCP_VERSION.zip." >&2
    exit 1
  }
  curl --fail --location --retry 3 --proto '=https' --tlsv1.2 \
    "$RELEASE_BASE/DipTrace-MCP-Portable-$MCP_VERSION.zip" -o "$BUNDLE_ZIP"
  ACTUAL_BUNDLE_SHA="$(sha256_file "$BUNDLE_ZIP")"
  [[ "$(lower "$ACTUAL_BUNDLE_SHA")" == "$(lower "$EXPECTED_BUNDLE_SHA")" ]] || {
    echo "DipTrace MCP bundle SHA-256 mismatch: $ACTUAL_BUNDLE_SHA" >&2
    exit 1
  }
fi

rm -rf "$RUNTIME_ROOT.new"
mkdir -p "$RUNTIME_ROOT.new"
ditto -x -k "$BUNDLE_ZIP" "$RUNTIME_ROOT.new"
for required in \
  app/diptrace_mcp_server.exe \
  app/tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe \
  bridge/diptrace_mcp_bridge.exe \
  settings-templates/pcb.settings.xml \
  settings-templates/schematic.settings.xml \
  settings-templates/component.settings.xml \
  settings-templates/pattern.settings.xml \
  SHA256SUMS.txt; do
  [[ -f "$RUNTIME_ROOT.new/$required" ]] || { echo "Portable runtime is missing: $required" >&2; exit 1; }
done
# Windows release assets use CRLF-compatible manifests. Normalize only the
# manifest line endings before macOS shasum reads file names; hashed payload
# bytes are never modified.
tr -d '\r' < "$RUNTIME_ROOT.new/SHA256SUMS.txt" > "$RUNTIME_ROOT.new/SHA256SUMS.lf"
mv "$RUNTIME_ROOT.new/SHA256SUMS.lf" "$RUNTIME_ROOT.new/SHA256SUMS.txt"
(
  cd "$RUNTIME_ROOT.new"
  shasum -a 256 -c SHA256SUMS.txt >/dev/null
) || { echo "Portable runtime internal checksum verification failed." >&2; exit 1; }
rm -rf "$RUNTIME_ROOT"
mv "$RUNTIME_ROOT.new" "$RUNTIME_ROOT"

install_plugin_for_module() {
  module="$1"
  template="$2"
  target="$DIPTRACE_ROOT/Plugins/$module/DipTraceMCP"
  mkdir -p "$target"
  cp "$RUNTIME_ROOT/bridge/diptrace_mcp_bridge.exe" "$target/diptrace_mcp_bridge.exe"
  cp "$RUNTIME_ROOT/settings-templates/$template" "$target/settings.xml"
}
install_plugin_for_module Pcb pcb.settings.xml
install_plugin_for_module Schematic schematic.settings.xml
install_plugin_for_module CompEdit component.settings.xml
install_plugin_for_module PattEdit pattern.settings.xml

COMMON_ENV="$INSTALL_ROOT/macos-runtime-env.sh"
cat >"$COMMON_ENV" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export DIPTRACE_MCP_APP_PATH=$(printf '%q' "$APP_PATH")
export DIPTRACE_MCP_RUNTIME_ROOT=$(printf '%q' "$RUNTIME_ROOT")
export DIPTRACE_MCP_MACOS_WORKSPACE=\${DIPTRACE_MCP_MACOS_WORKSPACE:-$(printf '%q' "$WORKSPACE")}
export DIPTRACE_MCP_MACOS_STATE_DIR=\${DIPTRACE_MCP_MACOS_STATE_DIR:-$(printf '%q' "$STATE_DIR")}
export WINEPREFIX=$(printf '%q' "$PREFIX")
export WINE=$(printf '%q' "$WINE")
export PATH=$(printf '%q' "$APP_PATH/Contents/SharedSupport/wine/bin"):\$PATH
export DYLD_FALLBACK_LIBRARY_PATH=$(printf '%q' "$APP_PATH/Contents/Frameworks"):\${DYLD_FALLBACK_LIBRARY_PATH:-}
export WINEDEBUG=\${WINEDEBUG:--all}
EOF
chmod 700 "$COMMON_ENV"

write_wrapper() {
  name="$1"
  shift
  dest="$BIN_DIR/$name"
  {
    echo '#!/usr/bin/env bash'
    echo 'set -euo pipefail'
    printf 'source %q\n' "$COMMON_ENV"
    printf '%s\n' "$@"
  } >"$dest"
  chmod 755 "$dest"
}

runtime_env_lines=(
  'mkdir -p "$DIPTRACE_MCP_MACOS_WORKSPACE" "$DIPTRACE_MCP_MACOS_STATE_DIR"'
  'win_workspace="$($WINE winepath -w "$DIPTRACE_MCP_MACOS_WORKSPACE" | tr -d "\r")"'
  'win_state="$($WINE winepath -w "$DIPTRACE_MCP_MACOS_STATE_DIR" | tr -d "\r")"'
  'win_profile="$($WINE cmd /c "echo %USERPROFILE%" 2>/dev/null | tr -d "\r")"'
  'export DIPTRACE_MCP_WORKSPACE="$win_workspace" DIPTRACE_MCP_STATE_DIR="$win_state" DIPTRACE_MCP_ALLOWED_ROOTS="$win_workspace;$win_profile"'
)

write_wrapper diptrace-mcp \
  "${runtime_env_lines[@]}" \
  'exec "$WINE" "$DIPTRACE_MCP_RUNTIME_ROOT/app/diptrace_mcp_server.exe" "$@"'

write_wrapper diptrace-mcp-bridge \
  "${runtime_env_lines[@]}" \
  'exec "$WINE" "$DIPTRACE_MCP_RUNTIME_ROOT/bridge/diptrace_mcp_bridge.exe" "$@"'

write_gui_wrapper() {
  command_name="$1"
  exe_name="$2"
  write_wrapper "$command_name" \
    "${runtime_env_lines[@]}" \
    "exe=\"\$WINEPREFIX/drive_c/Program Files/DipTrace/$exe_name\"" \
    'if (($#)); then project="$1"; shift; win_project="$($WINE winepath -w "$project" | tr -d "\r")"; exec "$WINE" "$exe" "$win_project" "$@"; fi' \
    'exec "$WINE" "$exe"'
}
write_gui_wrapper diptrace-schematic Schematic.exe
write_gui_wrapper diptrace-pcb Pcb.exe
write_gui_wrapper diptrace-component-editor CompEdit.exe
write_gui_wrapper diptrace-pattern-editor PattEdit.exe

write_wrapper diptrace-gui-headless \
  "${runtime_env_lines[@]}" \
  'helper="$DIPTRACE_MCP_RUNTIME_ROOT/app/tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe"' \
  'args=("$@")' \
  'for ((i=0; i<${#args[@]}; i++)); do if [[ "${args[$i]}" == "--project" && $((i+1)) -lt ${#args[@]} ]]; then project="${args[$((i+1))]}"; [[ -e "$project" ]] || { echo "Project does not exist: $project" >&2; exit 2; }; args[$((i+1))]="$($WINE winepath -w "$project" | tr -d "\r")"; fi; done' \
  'exec "$WINE" "$helper" "${args[@]}"'

write_wrapper diptrace-mcp-doctor \
  "${runtime_env_lines[@]}" \
  'helper="$DIPTRACE_MCP_RUNTIME_ROOT/app/tools/diptrace_mcp_headless_gui/diptrace_mcp_headless_gui.exe"' \
  'echo "DipTrace app: $DIPTRACE_MCP_APP_PATH"' \
  'echo "MCP runtime: $DIPTRACE_MCP_RUNTIME_ROOT"' \
  'echo "Workspace: $DIPTRACE_MCP_MACOS_WORKSPACE"' \
  'echo "State: $DIPTRACE_MCP_MACOS_STATE_DIR"' \
  '"$WINE" --version' \
  '"$WINE" "$DIPTRACE_MCP_RUNTIME_ROOT/app/diptrace_mcp_server.exe" --version' \
  '"$WINE" "$helper" doctor --diptrace-root "C:\\Program Files\\DipTrace" --require-automation'

cat >"$INSTALL_ROOT/installation-manifest.txt" <<EOF
platform=macOS
mcp_version=$MCP_VERSION
diptrace_version=$DIPTRACE_VERSION
diptrace_app=$APP_PATH
runtime_root=$RUNTIME_ROOT
workspace=$WORKSPACE
state_dir=$STATE_DIR
bin_dir=$BIN_DIR
headless_backend=hidden-win32-desktop
EOF

cat <<EOF
DipTrace MCP v$MCP_VERSION for macOS is installed.
DipTrace $DIPTRACE_VERSION: $APP_PATH
Commands: $BIN_DIR/diptrace-mcp, diptrace-schematic, diptrace-pcb,
          diptrace-gui-headless, diptrace-mcp-doctor

If $BIN_DIR is not already in PATH, add it to your shell PATH.
Run: $BIN_DIR/diptrace-mcp-doctor
EOF
