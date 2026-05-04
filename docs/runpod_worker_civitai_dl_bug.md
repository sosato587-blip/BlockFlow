# RunPod worker bug report — civitai DL via aria2c hits 403

**Status:** ✅ Resolved 2026-05-01 by shipping
``satoso2/comfyui-serverless:v11-curl-wrapper``. Endpoint
``xio27s12llqzpa`` template updated, workers recycled, end-to-end
verification passed (6/6 One Piece LoRAs landed in
``/runpod-volume/ComfyUI/models/loras/``). See **Resolution** section
below for the post-mortem. Original triage kept verbatim above
"Resolution" for the historical record.

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

---

## Resolution (2026-05-01)

The first attempted fix (v10) added ``--user-agent`` to the aria2c
invocation by editing ``download_handler.py``. **This was insufficient**:
Cloudflare's WAF in front of ``b2.civitai.com`` fingerprints aria2c's
TLS handshake (JA3) and the absence of browser-only request headers, not
just the User-Agent string. The redirected fetch still came back 403.
End-to-end re-test confirmed.

The successful fix (v11) routes the actual fetch through curl, which
uses a different TLS stack and a fuller header set that Cloudflare lets
through. Critically, this is done **without modifying Hearmeman's Python
handler**:

```dockerfile
COPY aria2c-wrapper.sh /usr/local/bin/aria2c-wrapper.sh
RUN chmod +x /usr/local/bin/aria2c-wrapper.sh && \
    mv /usr/bin/aria2c /usr/bin/aria2c-real && \
    cp /usr/local/bin/aria2c-wrapper.sh /usr/bin/aria2c && \
    chmod +x /usr/bin/aria2c
```

The shim parses ``-d <dir>`` / ``-o <filename>`` from aria2c's argv,
ignores benign flags (``--summary-interval=…``, ``--user-agent=…``,
``--allow-overwrite=…``, ``--console-log-level=…``), and runs:

```bash
curl --location --fail --silent --show-error --retry 3 \
     --user-agent "Mozilla/5.0 ... Chrome/126.0.0.0 ..." \
     -H "Accept: */*" \
     -H "Accept-Language: en-US,en;q=0.9" \
     -H "Accept-Encoding: identity" \
     -o "$dest_dir/$filename" "$url"
```

Unknown flags fall through to the renamed real binary at
``/usr/bin/aria2c-real`` so interactive debugging on the worker is
unaffected.

### Why a shim instead of editing the Python

The handler is a verbatim copy of
[``Hearmeman24/remote-comfy-gen-handler``](https://github.com/Hearmeman24/remote-comfy-gen-handler)
(MD5 ``5223f55c22276a9e55e2cf4583765c41`` matches GitHub HEAD on
2026-05-01). Editing it in place would create merge friction every time
upstream ships a fix. The shim is purely a Dockerfile-level concern and
leaves the vendored Python pristine.

### Limitations (acceptable for now)

- The handler's per-chunk progress parser (``_parse_aria2c_progress``)
  expects aria2c's ``[#xxx 1.2GiB/3.5GiB(34%) DL:…]`` format. curl
  doesn't emit those lines, so in-flight progress events stop firing
  during a download. The handler's pre-download / post-download
  progress events still work. If we need granular progress later,
  rewrite the shim in Python and emit aria2c-shaped lines.
- The shim only translates the small subset of aria2c flags the handler
  uses today. New flags introduced by an upstream Hearmeman update
  would fall through to ``aria2c-real`` and re-trigger the original
  WAF 403. Add the new flag(s) to the case statement when that happens.

### Secondary bug — ``--source civitai`` path

``CIVITAI_SCRIPT`` in ``download_handler.py`` points at
``/tools/civitai-downloader/download_with_aria.py`` which does not
exist in our image. Callers should use ``source="url"`` with
``https://civitai.com/api/download/models/<vid>?token=…`` instead, which
goes through the patched ``_download_url`` and works. We did NOT fix
this in 2026-05-01 — it would require either re-adding the helper
script or rewriting ``_download_civitai`` to delegate to
``_download_url``.

### Verification

```bash
# On the mini PC (or any machine with the env vars)
cd C:\Users\sato\BlockFlow
$env:CIVITAI_API_KEY = "..."  # if not in .env
uv run scripts/dl_onepiece_loras.py --execute --endpoint-id xio27s12llqzpa

# Then on RunPod (after the job completes):
curl -X POST https://api.runpod.ai/v2/xio27s12llqzpa/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"command":"list_models","model_type":"loras"}}' \
  | jq '.output.files[] | select(.filename | test("Boa_Hancock|NicoRobin_OnePiece|One_Piece_Manga|PeronaOnePiece|onepiece_nami|yamato"))'
```

Expected: 6 entries returned, all in ``/runpod-volume/ComfyUI/models/loras/``.
