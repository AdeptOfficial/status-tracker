#!/usr/bin/env bash
# Check directory access using disposable files in an existing container.
# No API keys, media reads/deletions, ownership changes, or container recreation.
set -euo pipefail
usage() {
    echo "Usage: $0 --container NAME --uid UID --gid GID --path /container/media/directory" >&2
    exit 2
}
container_name= permission_uid= permission_gid= media_directory=
while [[ $# -gt 0 ]]; do
    [[ $# -ge 2 ]] || usage
    case "$1" in
        --container) container_name=$2 ;;
        --uid) permission_uid=$2 ;;
        --gid) permission_gid=$2 ;;
        --path) media_directory=$2 ;;
        *) usage ;;
    esac
    shift 2
done
[[ $container_name =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || usage
[[ $permission_uid =~ ^[0-9]+$ && $permission_gid =~ ^[0-9]+$ ]] || usage
[[ $permission_uid -ne 0 ]] || { echo "Use the non-root media service UID; a root test cannot validate its permissions." >&2; exit 2; }
[[ $media_directory == /* && $media_directory != / ]] || usage
command -v docker >/dev/null || { echo "Docker CLI is required." >&2; exit 2; }
docker exec --user "$permission_uid:$permission_gid" "$container_name" sh -eu -c '
    base=$1
    [ -d "$base" ] || { echo "Directory does not exist in this container." >&2; exit 1; }
    probe=$(mktemp -d "$base/.status-tracker-permissions.XXXXXX")
    cleanup() {
        rm -f "$probe/source" "$probe/renamed"
        rmdir "$probe"
    }
    trap cleanup EXIT
    printf "permission probe\n" > "$probe/source"
    mv "$probe/source" "$probe/renamed"
    rm "$probe/renamed"
' sh "$media_directory"
echo "PASS: disposable directory/file create, rename and delete succeeded as $permission_uid:$permission_gid in $container_name."
