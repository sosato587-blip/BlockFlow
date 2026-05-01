# Handoff for Web / Mobile Claude

**目的**: デスクトップの Claude Code セッションから Web / モバイル Claude (claude.ai) に作業を引き継ぐためのドキュメント。Max プランなら web/mobile も同じアカウントで使えるので、このファイルを読み込ませれば出先でも設計相談・ドキュメント作成・コードレビューができる。

**Web / Mobile Claude の制限**:
- ✅ GitHub のファイル URL を fetch して読める（GitHub connector が有効な場合は repo 直読みも可）
- ✅ 設計議論・コードレビュー・ドキュメントドラフト・プロンプト設計 OK
- ❌ ファイル書き込み・git コミット・`uv run`・実機動作確認は不可（→ 実作業はデスクトップ版 Claude Code に戻ってやる）

---

## 1. プロジェクト基本情報

- **Repo**: https://github.com/sosato587-blip/BlockFlow
- **ブランチ戦略**: `dev` → `staging` → `main` (fast-forward merge のみ)
- **稼働ホスト**: **ミニPC (`C:\Users\sato\BlockFlow`) 専用**。メインPC (`C:\Users\socr0\BlockFlow`) は **git 操作・編集のみで起動厳禁**
- **起動コマンド** (ミニPC): `uv run app.py` + `cloudflared tunnel --url http://localhost:3000`
- **スタック**: Next.js 16 + React 19 + TypeScript (frontend) / FastAPI + Python 3.12 (backend) / RunPod Serverless (GPU) / R2 (storage)

## 2. 絶対ルール（CLAUDE.md 由来・違反厳禁）

### 🔴 ルール1: BlockFlow 稼働ホスト固定
- ミニPC でのみ `uv run app.py` / `npm run dev` / `cloudflared tunnel`
- メインPC で上記コマンドを**絶対に提案しない**
- リモートアクセス URL はミニPC の cloudflared ターミナルにしか存在しない → 聞かれたら「知りません、貼ってください」

### 🔴 ルール2: フロントエンド二重実装同期
- デスクトップ版 `custom_blocks/*/frontend.block.tsx` と モバイル版 `frontend/src/app/m/page.tsx` (3600+ 行モノリス) は**完全に別実装**
- UX 変更は**必ず両方に入れる**。過去 2 回「モバイル忘れた」事故あり
- `custom_blocks/` を触る前に必ず `m/page.tsx` を grep

### 🔴 ルール3: コスト発生作業は事前承認必須
- RunPod バッチ生成（12枚以上）
- モデル DL（数 GB 単位）
- 実行して $ が飛ぶものは全部ユーザー確認

## 3. 現在の状態（2026-04-23 時点）

### 今朝のセッションでやったこと（main に push 済み）
| Commit | 内容 |
|---|---|
| `a64ef80` | fix(app): PEP 723 から `comfy-gen` 除去（起動不能バグ修正） |
| `556fd2a` / `4769026` | chore: 自動生成ファイル `generated/` を `.gitignore` + untrack |
| `ba68f95` | feat(m): モバイル LoRA セクションに公式 family ラベル反映 |
| `856b697` | feat(comfy_gen): CLI 警告 dismissible + Sync ボタン disabled tooltip |
| `bfe0be9` | test: base_models / cache fallback / LoRA mapping 3 スイート 36 ケース |
| `7926de1` | fix(lint): set-state-in-effect を 2 件解消（21→19） |
| `e926ca7` | docs(readme): Base Model / LoRA Selector / inline LoRA 追記 |

### 検収済み（ユーザー確認済み）
- ミニPC で `git pull origin main` → 衝突なし
- `uv run app.py` 起動成功
- ブラウザで動作確認済み

## 4. 残タスク（優先度順）

### ✅ 完了（A4 — 2026-04-25）
- **A4**: モバイル版 (`/m`) への inline LoRA UI 実装 — **完了**
  - 共有コンポ `frontend/src/components/lora/InlineLoraPicker.tsx` をデスクトップとモバイル両方で使用
  - Mobile 送信 payload を `high_loras` / `low_loras` に分割（旧 `loras` は backend で legacy fallback として受理、deprecation log 付き）
  - `backend/lora_mapping.py` に Python 移植 + 10 ケース pytest
  - `backend/m_routes.py` の `build_z_image_workflow` / `build_illustrious_workflow` を `high_loras` / `low_loras` 対応にして single-pass merge、`build_wan_i2v_workflow` には dual-pass LoRA 注入を新規追加
  - 統合テスト 17 ケース追加（`backend/tests/test_m_routes_loras.py`）
  - 詳細は `docs/handoffs/A4_HANDOFF.md` 参照

### 🟠 高優先度
- **B3**: LoRA loader=0 の警告に具体的アクション提案（workflow に `LoraLoaderModelOnly` 追加方法）
- **A7**: `m/page.tsx` 3600行モノリス分割（`m/sections/base-model.tsx` 等）
- **S2-Full**: Desktop/Mobile アーキテクチャ完全統一（A4 完了後の長期構想、§ 8 参照）

### 🟡 中優先度
- **C3**: `backend/services.py` 分割（`services/lora.py`, `services/runs.py`, `services/runpod.py`）
- **C4**: `base_models.py` の `_LORA_OVERRIDES` / `_LORA_PATTERNS` を JSON 化
- **C5**: `comfy_gen/frontend.block.tsx` の未使用 `loraOverrides` state 完全削除
- **D4**: Playwright E2E テスト追加（ComfyGen workflow ロード → Generate 有効化遷移）
- **D5**: モバイル版 Playwright test
- **残り 19 件の lint error**（set-state-in-effect / rules-of-hooks）
- **G2**: `.env.example` 作成
- **E2**: `CONTRIBUTING.md` 新規作成（二重実装ルール / ブランチ flow）

### 🟢 低優先度（ポリッシュ）
- UX_AUDIT 残項目（`shared FormField wrapper` 等のアーキ寄り項目）
- ダークモード contrast 調整
- キーボードショートカット（Ctrl+Enter で generate）
- ドキュメントのスクショ追加

### ⛔ Active blockers (worker side, BlockFlow からは直せない)
- **RunPod worker の civitai DL が壊れている**（2026-05-01 確認）: `/handler/download_handler.py` が aria2c で `b2.civitai.com` を叩くと 403（Cloudflare WAF が aria2c のデフォルト User-Agent を bot 判定）。`--source civitai` パスは別バグ（`/tools/civitai-downloader/download_with_aria.py` が image に存在しない）。**詳細・再現・修正案は [`docs/runpod_worker_civitai_dl_bug.md`](docs/runpod_worker_civitai_dl_bug.md)**。ユーザーが worker メンテナにエスカレ予定。それまで `scripts/dl_onepiece_loras.py --execute` は失敗する（dry-run は OK）。ワークアラウンド: ブラウザ DL → `runpodctl send` か Network Volume 直アップ。

### 💬 ユーザー判断待ち
- **動画モデル用ブロックの設計**: WAN 2.2 I2V / LTX Video 用 UI を画像ブロックと同じ「1ブロック全部インライン」パターンにするか、専用 high/low 入力の別パターンにするか
- **`lora_selector` の base_model 未接続時の挙動**: 現状 illustrious デフォルト。「全 LoRA alphabetical で出す」に変えるか
- **pyproject.toml 移行**: 現状 PEP 723 inline deps。dev deps (pytest 等) を足すなら移行すべきか
- **`comfy-gen` CLI のインストール元**: PyPI には無い。ローカルパスか git URL で入れるはず。未調査

## 5. アーキテクチャ要点（Web Claude が知っておくべきこと）

### ディレクトリ構造
```
blockflow/
├── app.py                  # PEP 723 inline deps で uv run 起動
├── backend/
│   ├── main.py             # FastAPI エントリ
│   ├── base_models.py      # family taxonomy + LoRA classifier
│   ├── services.py         # LoRA フェッチ・R2・RunPod 呼び出し（肥大化中）
│   └── ...
├── custom_blocks/
│   └── <slug>/
│       ├── frontend.block.tsx    # ブロック UI + 実行ロジック
│       └── backend.block.py      # ブロック API sidecar (optional)
├── frontend/
│   └── src/app/m/page.tsx  # モバイル UI（モノリス、要注意）
└── tests/                  # 今朝追加した stdlib unittest
```

### base_models.py の family 体系
現在 4 family のみ（`sdxl`/`flux`/`unknown` は 2026-04-22 に削除済み）:
- `illustrious` — Illustrious XL (anime)
- `z_image` — Z-Image Turbo (realistic)
- `wan_22` — Wan 2.2 (video)
- `ltx` — LTX Video (fast video)

### inline LoRA マッピング heuristic（重要）
`frontend/src/lib/lora-mapping.ts` に抽出済み。5 ケース:
1. `loraNodes.length === 0` → no-op (UI 警告)
2. `loraNodes.length === 1` → 両 branch 統合して投入
3. labels に `high`/`low` あり → label で split
4. `loraNodes.length === 2` で label なし → 順序で `[high, low]` とみなす
5. `loraNodes.length > 2` で label なし → sequential fallback

## 6. Web Claude での相談に向いてるトピック

- 「A4（モバイル版 inline LoRA UI）の設計案を 3 つ比較して」
- 「C3（services.py 分割）の責務境界をどう引くか」
- 「動画ブロックの UI パターン、画像と分けるべき理由を整理して」
- 「`.env.example` のドラフトを書いて」
- 「CONTRIBUTING.md のドラフトを書いて」
- 「残りの lint error 19 件、カテゴリ別に潰す順序を提案して」

## 7. Web Claude での相談に**向いてない**トピック

- 「この関数直して」→ デスクトップ側で Claude Code にやらせる
- 「コミットして push して」→ デスクトップ側 or ミニPC 側
- 「RunPod 叩いて画像生成して」→ デスクトップ側（API キー所在）

## 8. S2-Full: Desktop/Mobile アーキテクチャ完全統一

**ステータス:** 📝 計画中、長期（3 ヶ月以上）

**目標:** `/api/m/*` と mobile 専用 workflow builder を退役。すべての mobile 操作を desktop のブロック API 経由で実行する。

**サブタスク:**
- Inpaint / Outpaint / ControlNet / CharaIP / ADetailer / CharacterSheet / LTXVideo の desktop ブロックを新設
- `m_routes.py` の Python workflow builder をブロックごとの `backend.block.py` に移管
- Mobile 送信を `/api/m/*` から `/api/blocks/*/run` に切替
- 命令型 Python builder を宣言型 JSON テンプレに置換
- `m_routes.py` 本体を退役（`m_store.py` はプリセット・コスト・Publications・Schedules 用に残す）

**A4 で済ませた前進:**
- 共有コンポ `<InlineLoraPicker>` を desktop / mobile 両方で利用（UI レイヤは統一済み）
- payload 形状 (`high_loras` / `low_loras`) を desktop の split UI と揃えた
- `backend/lora_mapping.py` の Python 実装で 5-case heuristic を共通化

**発動条件:** 同期事故が再発したら見直す。

---

## 使い方

Claude.ai の Web / モバイルで新規会話を開いて、以下のプロンプトを貼り付ける:

> BlockFlow というプロジェクトの設計相談をしたい。
> このドキュメントを読んで: https://github.com/sosato587-blip/BlockFlow/blob/main/HANDOFF_FOR_WEB_CLAUDE.md
> 加えて、必要に応じて以下を参照:
> - README: https://github.com/sosato587-blip/BlockFlow/blob/main/README.md
> - CLAUDE.md: （メインPC ローカルのみ、repo には無い。内容は上の handoff doc に要約してある）
> - MORNING_REPORT.md: https://github.com/sosato587-blip/BlockFlow/blob/main/MORNING_REPORT.md
>
> 今日は〇〇について相談したい。
