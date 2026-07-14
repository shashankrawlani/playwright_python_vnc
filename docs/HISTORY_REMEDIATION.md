# Removing sensitive data from Git history

Use this procedure only from a fresh mirror clone after making the remote private. History rewriting changes commit IDs and requires a force-push.

## Preconditions

1. Make the GitHub repository private.
2. Disable pushes temporarily and notify collaborators.
3. Back up the remote to encrypted storage.
4. Install `git-filter-repo` from its official package/repository.
5. Record branch-protection settings; temporarily permit an administrator force-push.

## Rewrite runtime profile paths

```bash
git clone --mirror https://github.com/OWNER/playwright_python_vnc.git pyplayvnc-clean.git
cd pyplayvnc-clean.git

git filter-repo --force \
  --path profiles/ \
  --invert-paths

# Verify no profile paths remain in any reachable ref.
git log --all --name-only --pretty=format: -- profiles/
git rev-list --objects --all | grep -E '(^| )profiles/' && exit 1 || true
```

If other PII appears in commit metadata or documentation, use a mailmap callback and/or a replacement file as documented by `git-filter-repo`. Never put the original sensitive values in a committed cleanup script.

## Rescan before publishing

Run a secret scanner such as Gitleaks and verify manually:

```bash
git log --all --format='%H %an <%ae>'
git ls-tree -r --name-only --full-tree HEAD
gitleaks git . --redact --no-banner
```

Then force-push the rewritten mirror:

```bash
git push --force --mirror origin
```

Delete obsolete GitHub releases/artifacts and rotate any credential whose value or verifier was exposed. Ask GitHub Support about cached sensitive objects if necessary. All collaborators must delete old clones and clone again.

Only restore public visibility after a second independent scan.
