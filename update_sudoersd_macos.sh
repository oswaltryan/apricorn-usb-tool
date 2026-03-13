#!/bin/sh
set -eu

show_usage() {
    cat <<'USAGE'
Usage: sudo ./update_sudoersd_macos.sh [--command <path>] [--remove]

Installs or removes an opt-in sudoers.d rule on macOS so the usb CLI can be
run via `sudo -n` without an interactive password prompt.

Options:
  --command PATH  Absolute command path to allow (default: /usr/local/bin/usb)
  --remove        Remove the managed sudoers rule instead of installing it
  -h, --help      Show this message
USAGE
}

COMMAND_PATH="/usr/local/bin/usb"
REMOVE_RULE=0
DEST_DIR="/etc/sudoers.d"
DEST_FILE="$DEST_DIR/usb-tool-nopasswd"
VISUDO="${VISUDO:-/usr/sbin/visudo}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --command)
            shift
            [ -n "${1-}" ] || { echo "Missing value for --command" >&2; exit 1; }
            COMMAND_PATH="$1"
            ;;
        --remove)
            REMOVE_RULE=1
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            show_usage
            exit 1
            ;;
    esac
    shift
done

if [ "$(id -u)" != "0" ]; then
    echo "This helper must be run as root." >&2
    exit 1
fi

if [ ! -d "$DEST_DIR" ]; then
    echo "Directory not found: $DEST_DIR" >&2
    exit 1
fi

if [ ! -x "$VISUDO" ]; then
    echo "visudo not found at $VISUDO" >&2
    exit 1
fi

if [ "$REMOVE_RULE" -eq 1 ]; then
    rm -f "$DEST_FILE"
    echo "Removed $DEST_FILE"
    exit 0
fi

case "$COMMAND_PATH" in
    /*) ;;
    *)
        echo "--command must be an absolute path." >&2
        exit 1
        ;;
esac

case "$COMMAND_PATH" in
    *[[:space:]]*)
        echo "--command cannot contain whitespace." >&2
        exit 1
        ;;
esac

tmp_file="$(mktemp "$DEST_DIR/usb-tool-nopasswd.XXXXXX")"
trap 'rm -f "$tmp_file"' EXIT INT TERM

cat >"$tmp_file" <<EOF
ALL ALL=(root) NOPASSWD: $COMMAND_PATH
EOF

chmod 0440 "$tmp_file"
chown root:wheel "$tmp_file"

if ! "$VISUDO" -cf "$tmp_file" >/dev/null 2>&1; then
    echo "Generated sudoers rule failed validation." >&2
    exit 1
fi

mv "$tmp_file" "$DEST_FILE"
trap - EXIT INT TERM

echo "Installed $DEST_FILE"
echo "Allowed command: $COMMAND_PATH"
echo "Use 'sudo -n $COMMAND_PATH --json' to verify noninteractive sudo."
