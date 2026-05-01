# RunPod worker bug report — civitai DL via aria2c hits 403

**Status:** ⛔ Active blocker. Affects every civitai download attempt
through the BlockFlow scripts (and any other tool that uses the worker's
``download_handler``). 2026-05-01 confirmed twice on endpoint
``xio27s12llqzpa``.

## TL;DR

`/handler/download_handler.py:176` (the ``_download_url`` path) calls
``aria2c`` to fetch civitai signed URLs. ``aria2c`` follows civitai's
302 redirect to ``b2.civitai.com`` (Backblaze B2 storage), and **B2
returns HTTP 403 to the redirected request**. The civitai-API-side
auth itself succeeded (the redirect was issued correctly with a B2
signed token). Almost certainly Cloudflare WAF on ``b2.civitai.com``
is rejecting ``aria2c``'s default User-Agent.

## Reproduce

```bash
# On the worker (or any aria2c installation):
aria2c "https://civitai.com/api/download/models/1576956?token=<CIVITAI_KEY>"
```

Expected: file lands at ./onepiece_nami_illustriousXL-000005.safetensors
Actual: aria2c follows the 302, gets 403 on b2.civitai.com, exits 22.

Same model fetched via curl/wget/browser succeeds. Same model fetched
via aria2c with ``--user-agent="Mozilla/5.0 ..."`` succeeds (suspected;
needs confirmation on a worker shell).

## Trace excerpt

```
05/01 12:07:35 [NOTICE] CUID#7 - Redirecting to
  https://b2.civitai.com/file/civitai-modelfiles/model/124387/
    onepieceNami.bF1k.safetensors?Authorization=3_20260501120735_<sig>_004_20260501130735_0042_dnld
05/01 12:07:35 [ERROR]  CUID#7 - Download aborted.
  URI=https://civitai.com/api/download/models/1576956?token=civitai_<...>
Exception: [AbstractCommand.cc:351] errorCode=22
  URI=https://b2.civitai.com/file/...?Authorization=...
  -> [HttpSkipResponseCommand.cc:239] errorCode=22
     The response status is not successful. status=403
```

Note the timestamps: redirect issued at ``12:07:35``, B2 expiry at
``13:07:35`` (1-hour signed URL). aria2c follows immediately, so the
URL is fresh when the 403 happens. **Not an expiry issue.**

## Suggested fixes (any one fixes the symptom)

In rough order of effort:

1. **Pass a browser User-Agent to aria2c.** Cheapest fix. Inside
   ``download_handler._download_url``, add
   ``--user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"``
   (or any current browser UA) to the aria2c argv.

2. **Replace aria2c with ``requests``** for civitai-style flows
   (single file, no parallelism needed). ``requests`` sends
   ``python-requests/x.y.z`` UA which is also blocked by some WAFs,
   so still set a browser UA explicitly.

3. **Pre-resolve the redirect server-side** with ``requests`` (which
   handles the 302 and stores the unsigned-cookie session), then
   stream the body directly to disk. Bypasses aria2c entirely.

While we're in there, the ``--source civitai`` path
(``download_handler.py:56``) also throws an unrelated bug:

```
python3: can't open file '/tools/civitai-downloader/download_with_aria.py':
  [Errno 2] No such file or directory
```

That helper script is missing from the worker image. Either re-add it
or remove the ``--source civitai`` branch entirely (BlockFlow can stay
on ``--source url``).

## Workaround until patched

- Manual download from civitai (browser, while logged in).
- Upload the .safetensors to the network volume's ``loras/`` folder
  via ``runpodctl send`` or the RunPod Console file browser.
- ``comfy-gen list loras`` to confirm; press Sync on the ComfyGen
  block to refresh BlockFlow's ``comfy_gen_info_cache.json``.

## Affected BlockFlow surface

- ``scripts/dl_onepiece_loras.py`` (added 2026-05-01) — silently fails
  with FAILED status until this is fixed.
- Any future use of the ``input.command="download"`` JSON shape with
  ``downloads[].source="url"`` against civitai.com URLs.

## Verification after fix

Re-run on the mini PC:

```powershell
cd C:\Users\sato\BlockFlow
uv run scripts/dl_onepiece_loras.py --execute --endpoint-id <ENDPOINT_ID>
```

Expected: ``final status: COMPLETED`` and 6 LoRA files appear in
``comfy-gen list loras`` output.
