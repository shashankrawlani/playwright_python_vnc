# Migrating PyPlayVNC safely

Chrome profiles contain cookies, active sessions, browsing history, and other credentials. **Never commit `profiles/` to Git**, even in a private repository. The entire runtime directory is ignored by this project.

## Back up local runtime data

Stop the service first so Chrome databases are consistent:

```bash
pyplayvnc down
umask 077
tar -C "$HOME/repos/playwright_python_vnc" -czf "$HOME/pyplayvnc-private-backup.tgz" \
  profiles .env playwright-scripts shared
chmod 600 "$HOME/pyplayvnc-private-backup.tgz"
```

The archive contains credentials. Store it in encrypted storage or encrypt it before transfer. Do not upload it to GitHub, Docker Hub, issue trackers, chat, or public object storage.

## Transfer over SSH

```bash
scp "$HOME/pyplayvnc-private-backup.tgz" user@new-host:~/
```

On the new host:

```bash
git clone https://github.com/OWNER/playwright_python_vnc.git ~/repos/playwright_python_vnc
cd ~/repos/playwright_python_vnc
tar -xzf ~/pyplayvnc-private-backup.tgz
chmod 600 .env
pyplayvnc up
```

Delete transfer copies after verifying the migration.

## Alternative: encrypted rsync transport

```bash
pyplayvnc down
rsync -a --chmod=F600,D700 -e ssh \
  profiles/ user@new-host:~/repos/playwright_python_vnc/profiles/
```

## Verification

1. Confirm `git status --ignored --short profiles/` reports the runtime tree as ignored.
2. Confirm `git ls-files profiles/` prints nothing.
3. Start the service and check health/status.
4. Open each persona manually through VNC and reauthenticate if the provider requires it after the host/IP change.
5. Stop the service when finished.

## If profile data was ever committed

Do not fix this with a normal deletion commit: old blobs remain downloadable. Temporarily make the repository private, rewrite every ref with `git-filter-repo`, force-push the cleaned refs, remove cached release artifacts, and have collaborators clone again. See `docs/HISTORY_REMEDIATION.md`.
