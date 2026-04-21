# R2 Credentials Git-History Scrub — Plan

**Status: PLAN ONLY — do not execute without the user at the keyboard.**

## Why

Earlier in the project, R2 (Cloudflare S3-compat) credentials were hard-coded into `backend/r2_client.py` and friends. Phase C later replaced them with `os.getenv()` calls, but **the old hardcoded values are still in the git history of the `sosato587-blip/BlockFlow` fork**. Anyone who clones the repo or inspects the commit history can recover them. The fork is public on GitHub.

Rotating the credentials in Cloudflare stops the immediate damage, but leaves fingerprints in history. For a full scrub we need to rewrite history, force-push, and have everyone re-clone.

## Risk assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Old access key still works | High | **Rotate in Cloudflare first** — before any history rewrite. Rotation is the actual security control; the rewrite is just hygiene. |
| Force-push breaks open PRs | Medium | No open PRs on this fork at the moment; verify before push. |
| Force-push breaks local clones on miniPC | Low | Document the re-clone step and execute it the same session. |
| BFG drops commits we care about | Low | Run on a mirror clone first; diff `git log --all --oneline` before/after. |
| The secret exists outside git too | Medium | Grep R2 keys in: local logs, shell history, `.env.example`, Slack, Notion, Discord. Rotate catches this. |

## Step 0 — Rotate credentials (do this today regardless)

This is the only step that actually protects you. The rest is cleanup.

1. Cloudflare dashboard → R2 → Manage R2 API Tokens
2. Revoke the old token (the one that was hardcoded)
3. Create a new token with the same bucket scope
4. Update local `.env` on main PC and mini PC with the new values
5. Smoke-test: `curl` the gallery, confirm 200 + images
6. Announce internally: "old R2 token revoked, if anything breaks, ping me"

Do NOT proceed to Step 1+ until Step 0 is done. If you don't do Step 0, the history rewrite accomplishes nothing — the leaked credentials in old forks and scrapes are still valid.

## Step 1 — Identify offending commits

```bash
# Full history of strings that *look* like R2 creds
git log --all -p -S "R2_ACCESS_KEY" -- backend/
git log --all -p -S "R2_SECRET_KEY" -- backend/
git log --all -p --regexp-ignore-case -S "cloudflarestorage.com" -- backend/

# Or more bluntly: any commit that touched the now-sensitive files
git log --all --oneline -- backend/r2_client.py backend/main.py backend/gallery.py
```

Save the list. You want to know every commit SHA that introduced, modified, or still contains the literal secret.

## Step 2 — Pick a tool

| Tool | Speed | Notes |
|---|---|---|
| `git filter-repo` | Fast | Official recommendation; replaces the deprecated `git filter-branch`. Install: `pip install git-filter-repo`. |
| BFG Repo-Cleaner | Faster on big repos | Single-purpose; good for "remove literal strings X, Y". Java-based. |

For this repo (small, <50MB, <500 commits), either works. Plan uses **git-filter-repo** because it's the current Git project recommendation.

## Step 3 — Dry run on a mirror

```bash
# Mirror clone (not a normal clone — includes all refs and no working tree)
git clone --mirror https://github.com/sosato587-blip/BlockFlow.git BlockFlow-scrub
cd BlockFlow-scrub

# Prepare a replacements file with each literal to scrub
cat > ../r2-replacements.txt <<'EOF'
<literal-access-key-id>==>REMOVED_R2_ACCESS_KEY
<literal-secret-key>==>REMOVED_R2_SECRET_KEY
<literal-account-id-if-hardcoded>==>REMOVED_R2_ACCOUNT
EOF

# Dry scrub
git filter-repo --replace-text ../r2-replacements.txt --force
```

Inspect the result:

```bash
git log --oneline | head -30            # commit messages should be unchanged
git log --all -p -S "<literal-access-key-id>"   # should return nothing
git log --all --oneline | wc -l         # should match pre-scrub count (rewriting, not dropping)
```

If any of the above looks wrong, STOP. Don't push. Diagnose first.

## Step 4 — Validate the rewritten repo still works

Clone the mirror into a normal working tree and run the app:

```bash
git clone ../BlockFlow-scrub ../BlockFlow-scrub-wt
cd ../BlockFlow-scrub-wt
# Populate .env with the NEW rotated credentials
cp /path/to/new/.env .
uv run app.py
# Visit http://localhost:3000 — gallery, generation, everything should work
```

If the app is broken, the rewrite destroyed something. Recover from the unrewritten original and diagnose.

## Step 5 — Coordinate the force-push

1. **Freeze** — Slack DM: "force-pushing `main` and all branches in 5 min, do not push during that window"
2. Close any open PRs (or warn their authors that they'll need to rebase)
3. Identify every branch: `git branch -r | awk '{print $1}'`

## Step 6 — Force-push

```bash
cd BlockFlow-scrub
git push --force --all origin
git push --force --tags origin
```

GitHub will accept this for a fork where the pushing user is the owner. Verify on the web UI that commit SHAs have changed.

## Step 7 — Purge GitHub's cached views

GitHub caches old commit views for ~90 days. After force-push:

1. GitHub support email (or Settings → Support) → "I force-pushed to remove leaked secrets, please purge the cached refs for repo sosato587-blip/BlockFlow"
2. In the meantime, old commit URLs (`/commit/<old-sha>`) still resolve. Treat the secrets as compromised (you already rotated in Step 0, so this is fine).
3. If the repo was ever mirrored (e.g. by a scraper or archive), those copies are out of your control. Again — Step 0 is the only real fix.

## Step 8 — Re-sync every clone

Every developer / machine that has a local clone must:

```bash
# Option A — fresh clone (simplest)
rm -rf BlockFlow
git clone https://github.com/sosato587-blip/BlockFlow.git

# Option B — in-place reset (preserves untracked files)
git fetch origin
git reset --hard origin/dev       # or whatever branch you're on
```

For the BlockFlow project specifically, this means:
- Main PC: `C:\Users\socr0\BlockFlow`
- Mini PC: `C:\Users\sato\BlockFlow`

Both need Option A or B. Do both the same day.

## Step 9 — Prevent recurrence

Add to `.gitignore` (already done, verify):

```
.env
.env.*
!.env.example
```

Add a pre-commit hook that rejects anything that looks like an R2 secret:

```bash
# .git/hooks/pre-commit  (or a tracked scripts/pre-commit.sh)
#!/bin/sh
if git diff --cached | grep -E "(R2_ACCESS_KEY_ID|R2_SECRET_ACCESS_KEY)\s*=\s*['\"][A-Za-z0-9/+=]{16,}"; then
  echo "ERROR: looks like an R2 credential in a staged diff. Aborting."
  exit 1
fi
```

Or install `gitleaks` (actively maintained) and wire it as a pre-commit hook:

```bash
scoop install gitleaks   # or winget / brew
gitleaks protect --staged
```

## Timeline estimate

| Step | Time |
|---|---|
| 0 (rotate) | 10 min |
| 1–2 (inventory + tool install) | 20 min |
| 3–4 (dry run + validate) | 30 min |
| 5–6 (coordinate + force-push) | 15 min |
| 7 (cache purge request) | 5 min (+ 90-day wait for GitHub) |
| 8 (re-clone both PCs) | 15 min |
| 9 (pre-commit hook) | 20 min |
| **Total live work** | **~2 hours**, best done in one focused session |

## What this plan does NOT do

- **It does not protect against anyone who cloned the repo before the scrub.** They have the old SHAs on disk and can reconstruct the secrets. Only Step 0 helps here.
- **It does not scrub Slack / email / Notion logs** where the credentials may have been pasted. Grep those manually.
- **It does not scrub `.env` backups** the user may have made. Search `~`, `Desktop`, cloud sync folders for `.env`, `*.env.*`, and stale copies.

## Decision matrix — do we actually do this?

| If... | Then... |
|---|---|
| The fork is public **and** credentials were ever hardcoded | Yes, do the full scrub. |
| The fork is private and only you + Claude push to it | Step 0 (rotate) is probably enough. History scrub is nice-to-have. |
| The credentials were never hardcoded, only in `.env` | Nothing to scrub. Just verify `.gitignore` + add the pre-commit hook. |

**Current status (2026-04-21):** The fork IS public. Earlier commits DID contain hardcoded R2 credentials. Therefore the full scrub is appropriate — but only after Step 0 makes it academic.

## Open questions before execution

- [ ] Have the R2 credentials actually been rotated in Cloudflare? (If no — do Step 0 today, regardless of the rest of this plan.)
- [ ] Is there a CI/CD or deployment that pulls from GitHub and would be surprised by the force-push? (BlockFlow has none today, but verify.)
- [ ] Does the mini PC have any local uncommitted work that would be lost in a hard reset? `git status` on both PCs before Step 8.
