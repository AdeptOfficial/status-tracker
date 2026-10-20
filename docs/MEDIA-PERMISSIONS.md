# Media permissions and deletion setup

Validate access before enabling cross-service deletion. Status Tracker sends API
requests; Radarr/Sonarr perform filesystem operations under their own service
identities. A working dashboard, readable movie, or accepted DELETE response does
not prove that those services can remove files.

## Access required by each service

| Service | Required access |
| --- | --- |
| Status Tracker | Write its `/config` SQLite directory; reach service APIs with configured credentials. No media mount or Docker socket is required. |
| Radarr | Read and traverse movie folders; write and traverse the directories containing files it imports, renames or deletes. Removing a movie directory also requires write/traverse access to its parent. |
| Sonarr | The same filesystem access for TV imports. TV deletion in this tracker is currently blocked until season scope is implemented. |
| Download client | Create downloads that Radarr/Sonarr can read and import. Shared groups/creation modes must work across all writers. |
| Jellyfin | Read video files and traverse library directories. A read-only media mount is supported; deletion happens through Radarr, followed by library verification. |
| Shoko (anime) | Read/traverse configured import paths. Verify separately before enabling anime cleanup; the live movie deletion test below was not an anime test. |
| Jellyseerr | Reach its APIs for request and availability management. It does not need filesystem access from Status Tracker. |

Deleting a file usually depends on permissions on its **containing directory**.
Making the file writable does not repair a directory that the service cannot
modify. All ancestors must also allow traversal; ACLs, sticky bits, read-only
mounts, NAS policy, SELinux and LXC user mappings can add constraints beyond mode
bits. See [Linux unlink semantics](https://man7.org/linux/man-pages/man2/unlink.2.html).

## Choose an identity and creation policy

Record the actual numeric UID, primary GID and supplementary groups for each
running writer. Check the process, not only the container's default exec user or
an example Compose file. For LinuxServer Radarr, these commands show the account,
process name/owner, and directory modes without printing environment variables:

```bash
docker exec radarr id abc
docker top radarr -eo uid,gid,comm
docker exec radarr stat -c '%a %u:%g %n' /data /data/movies '/data/movies/Example Movie'
```

The username/process tools vary by image. `docker exec radarr id` may describe
root used by init/exec instead of the application. PUID/PGID are image-specific;
setting them on an image that does not support them has no effect.

Two common policies are a shared media UID, or distinct service UIDs with a shared
media group. A shared group avoids changing every file's owner: writers need that
group, group write/traverse on relevant directories, and compatible creation modes.
Use the policy already established for your filesystem.

For a **new, empty LinuxServer media setup**, an illustrative configuration is
`PUID=1000`, `PGID=1000`, `UMASK=002` on the relevant writer services. Substitute
your chosen IDs; do not copy the DEV server's UID911 into another deployment.
Create reviewed library/download directories in that group with mode `2775`
(group writable, setgid). Setgid preserves the directory group; the umask normally
allows group write on newly created files/directories. Confirm what the application
actually creates, including downloaded/hardlinked files; a umask does not repair
existing permissions. File execute bits are not needed for media playback.

See [LinuxServer PUID/PGID](https://docs.linuxserver.io/general/understanding-puid-and-pgid/)
and [Radarr's image settings and umask](https://docs.linuxserver.io/images/docker-radarr/#umask-for-running-applications).
These variables belong to the **media services**, not Status Tracker. Follow your
image's identity mechanism; avoid adding a blanket Docker `user:` override to an
image whose init needs root.

For existing data, record ownership/modes first and adjust only reviewed paths.
If the intended group is already correct, a targeted `chmod g+w` on a containing
directory may be sufficient. Do not use `chmod -R 777` or recursively change all
media ownership as a setup step. Keep credentials and app configuration directories
outside broad media permission changes.

## Run a disposable preflight

On the Docker host, from this repository, select the running writer's UID and a
group it actually holds. The script creates a unique temporary subdirectory and
one small file, renames/deletes that file, then removes its own directory:

```bash
./scripts/check-media-permissions.sh \
  --container radarr --uid 1000 --gid 1000 --path /data/movies
```

Use the **container** path, not its host bind-mount path. Repeat for download roots
and representative existing movie/show directories, and for each writer identity.
The script requires Bash/Docker on the host and `sh`, `mktemp`, `mv`, `rm`, `rmdir`
in the selected container. It rejects UID0, exits nonzero on failure, and never
reads/deletes existing media or changes ownership/modes. A failed check may leave
its uniquely named temporary directory if cleanup itself is denied.

This is an explicit UID:GID permission probe. It does not discover or change the
application's identity, reproduce every supplementary group, prove access to
other directories, or guarantee deletion of files protected by a sticky bit/ACL.
Verify that the service process really has the tested group. Test newly imported
folders after changing creation policy. Check readers separately, and confirm
actual playback when validating an end-to-end request.

## Enable deletion and understand its results

1. Back up Status Tracker's SQLite data and identify an expendable movie. Database
   backups preserve history/configuration, not deleted video files.
2. Complete the identity/directory checks above and configure service API access.
3. Set `ENABLE_DELETION_SYNC=true` only when ready to allow service-side deletion.
   Authenticate as a configured administrator. With synchronization disabled,
   deletion removes only the selected tracker record.
4. For a **movie** test, keep “Delete files” checked. Compare the audit against
   actual disk inventory, Radarr state, Jellyfin library state and Jellyseerr
   availability. Check unrelated requests remain unchanged.
5. Submit a fresh request only as a separate intentional step; an empty Jellyseerr
   record alone does not prove a new download/import/playback cycle.

Movie deletion now stores the Radarr directory before mutation. It deletes the
registered movie file, verifies video absence through Radarr's filesystem API,
then removes the Radarr movie record. A stale/404 movie ID cannot prove file
removal: the saved directory must be verified. Subdirectories or ambiguous disk
responses require manual review; unregistered video files require re-import.

Jellyfin is scanned and the item must disappear before Jellyseerr is cleared.
Verification waits up to ten checks spaced one second apart. A longer scan may
leave an Incomplete audit; retry after the scan finishes. API/transport errors are
failures, not evidence of absence. Jellyseerr request and media removal are checked
again before completion. Keeping files preserves Jellyfin and media availability.

An Incomplete operation retains the tracker request. Inspect the last failed
service in **Deletions**, fix the cause, then retry from the request's delete
control. Earlier service operations may already have completed. The saved directory
supports safe verification on retry; it does not automatically re-create missing
Radarr records or import unregistered files. If a legacy attempt lost the Radarr
record while leaving media, re-add that same movie/path **without search**, scan
its existing file, and reconcile its tracker service ID before retrying. Do not
blindly restore an entire old database over other activity.

TV deletion, including bulk selections containing TV, remains blocked. Season-only
delete and explicit whole-show confirmation are still release blockers. Do not
bypass the guard to test a movie workflow on a show.

## Tested evidence and release plan

On DEV with Radarr6.4.4.10685 on October20, Interstellar's original deletion exposed the permission bug:
Radarr ran as UID911/GID911 with supplementary group1000; the movie directory and
its parent were owned1000:1000 with mode0755. Its movie record disappeared even
though the4.21GiB file remained. Audit69 was corrected to Incomplete.

After granting group write **only to those two directories**, re-importing the
same file without search and deploying the verification fix, audit70 completed.
An independent check found the real file absent, Radarr404, no matching Jellyfin
item, no Jellyseerr request/media entry, and no tracker record. Other request
IDs/titles/states were unchanged; both Cyberpunk seasons were preserved. DEV free
space was22.11GiB. The directory repair was0775, not a fleet-wide2775/umask rollout.
No new request/download was submitted and production was not changed.

226 isolated regressions, the exact runtime image and Firefox acceptance passed.
The preflight script independently reproduced failure at0755 and success at2775
for a different UID sharing the directory group; existing sentinel data remained
untouched and temporary probes were removed. Root probes were rejected. A second
isolated test confirmed setgid group inheritance,2775 directories/0664 files with
umask002, and cross-user rename/deletion by UID911 and UID1000 sharing GID1000.
This validates the Linux directory policy; real application creation modes remain
a separate deployment check.

Before a production release: verify fresh-import creation modes; test intentional
re-request/import; implement TV scope; validate anime cleanup; and repeat through
the supported proxy/device paths. Obtain the deployment owner's approval for
production. DEV success does not constitute a production release.
