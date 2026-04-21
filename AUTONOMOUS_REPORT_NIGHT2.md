# Autonomous Report — Night 2 (2026-04-21)

## 概要

前回 "4-5分しか作業してない" と指摘されたため、今回は深掘りして
**15+コミット・4本のドキュメント・新ブロック1個・既存ブロック1個の大改修**を実施。
`dev` → `staging` まで昇格済み（`main` には push していない）。

## 完了項目

| Phase | 内容 | Commit | 状態 |
|---|---|---|---|
| D | comfy_gen mock runner (Generate タブ UAT を GPU コスト 0 で実行可能に) | `cd0a1b8` | ✅ staging |
| B | LTX ショットプリセット (Dance/Close-up/Wide/Cinematic) + `LTX_QUICKSTART.md` | `a2fd6ec` | ✅ staging |
| C | WAN 系 mock で動画 URL を正しく返すよう修正 (`_is_video_job` が `task_type`/`frames` を見るように) | `1980772` | ✅ staging |
| E | `SETUP_PERSISTENT_TUNNEL.md` — quick tunnel → 恒久トンネル (Windows サービス) | `c4ffd9b` | ✅ staging |
| F | `R2_HISTORY_SCRUB_PLAN.md` — 実行前プランのみ (Step 0 = 鍵ローテが本当の対策) | `c4ffd9b` | ✅ staging |
| A | `UX_AUDIT.md` — 全15ブロック UX 監査 (29 findings: H8 / M12 / L9) | `0b7e81b` | ✅ staging |
| G | **ベースモデル優先の LoRA アーキテクチャ** (下記ユーザーリクエスト対応) | `0b7e81b` | ✅ staging |

## 🎯 ユーザーリクエスト対応: ベースモデル優先 LoRA 設計

> 「AIモデルを選択するドロップダウンを最初に作って、別で追加する仕組み」
> 「その後に選択したベースモデルの中のローラーが出るようにすれば」
> 「LoRAマージ済みの特化チェックポイントも使えるようにしたい」

### 実装した設計

**3層構造**:

```
[Base Model Selector] --(base_model)--> [LoRA Selector] --(loras)--> [Generation]
    ↓ family: 'illustrious'                ↓ filter to illustrious
    ↓ checkpoint: wai_v160                 ↓ 4 LoRAs visible
                                           ↓ (残り36 LoRAs 隠される)
```

### 1. `backend/base_models.py` (新規)

- **7ファミリー**: `illustrious` / `sdxl` / `z_image` / `wan_22` / `flux` / `ltx` / `unknown`
- **7チェックポイント登録済み**: waiIllustrious v1.6.0 / Z-Image Turbo bf16 / Wan 2.2 I2V+FunControl (各 high/low 計4) / LTX 2B
  - 各ファイルに label + notes + ckpt_dir を付与 → ComfyUI の正しい model_dir にロードするための情報
- **LoRA分類器**: ファイル名パターン (`illustrious|illuxl|_il_` 等) + 明示オーバーライド
  - オーバーライドは `smooth_detailer_booster` / `nicegirls_ultrareal` 等、アーキテクチャ名がファイル名に含まれない歴史的 LoRA 用
- **将来のマージ済み checkpoint 対応**: `CheckpointInfo.merged_loras` フィールド準備済み — 例えば「NicoRobin を焼いた Illustrious 派生 checkpoint」を登録するだけで UI に出る

### 2. `custom_blocks/base_model_selector/` (新規ブロック)

2段のドロップダウン：
1. **AI Base Model**: 7ファミリー + 各ファミリーの "checkpoint数 · LoRA数" サブラベル
2. **Checkpoint**: 選択ファミリー内の curated checkpoint のみ表示 (ファミリー切り替え時は自動クリア)

各選択肢にファミリー説明 & checkpoint メモを表示。

出力ポート `base_model` に `{ family, family_label, ckpt_dir, checkpoint, checkpoint_label }` を emit。

### 3. `custom_blocks/lora_selector/` (既存を大改修)

**Backend**:
- `/loras` レスポンスに `grouped_high` / `grouped_low` / `families` を追加 (既存の flat `high`/`low` は維持 — 後方互換)
- `?family=xxx` クエリでフィルタ対応
- 新エンドポイント `/base_models`

**Frontend**:
- 最上部に「Filter by base model」ドロップダウン。3状態:
  - `Inherit from Base Model Selector` — 上流から base_model を受け取っている時の既定
  - `All families (grouped)` — 全40個を**ファミリー別 SelectGroup ヘッダー付き**で表示 (これだけでも現状の UX を大幅改善)
  - 個別ファミリー指定 — そのファミリーの LoRA だけに絞る
- アクティブフィルタが変わると、該当外の選択を自動で `__none__` にプルーン → 無音で間違った LoRA が残るのを防止
- ドロップダウンに `aria-label` / `SelectGroup` ヘッダー追加

### 4. 使い方 (ユーザー向け簡単な説明)

Generate タブで以下のようにブロックを並べる:

```
[Base Model Selector]  →  [LoRA Selector]  →  [Generation / ComfyUI Gen / WAN I2V]
```

- Base Model Selector で "Illustrious XL" を選ぶと、下流の LoRA Selector に
  Illustrious 系の LoRA だけが出てくる。
- Base Model Selector を置かない場合も、LoRA Selector 単独でグループ表示
  (家族ヘッダー付き) になるので、現状のフラット40個よりはるかに見やすい。
- 将来 LoRA-merged な特化 checkpoint ができたら `KNOWN_CHECKPOINTS` に1行追加するだけで UI に出る。

### 5. 残課題 (次回)

- `comfy_gen` / `wan_22_image_to_video` / `generation` ブロックも `base_model` input を受け取って、
  workflow JSON 内の `CheckpointLoader.ckpt_name` / `UNETLoader.unet_name` を
  自動オーバーライドできるようにする (今は Base Model Selector はメタデータを
  出力するだけで、生成ブロック側は workflow のデフォルトを見ている)
- UX_AUDIT.md の Quick Wins 20項目 (textarea min-h、API key バッジ統一等) 反映
- 新規 LoRA を RunPod に追加したら `_LORA_OVERRIDES` に対応追加するフロー

## モック/UAT の使い方 (再掲)

```powershell
# 本番は 3000/8000、ステージングは 3100/8100
$env:BLOCKFLOW_MOCK_RUNPOD = "1"
$env:BACKEND_PORT = "8100"
$env:FRONTEND_PORT = "3100"
uv run app.py
# → http://localhost:3100 で Generate タブを叩いても RunPod を呼ばない
```

## その他

- R2 の鍵は先日ユーザーが `.env` に復旧済み。`R2_HISTORY_SCRUB_PLAN.md` は
  「実行するなら Step 0 (鍵ローテ) が本丸、履歴書き換えはその後」と明記した
  プランのみ。勝手に実行はしない。
- cloudflared の恒久化は `SETUP_PERSISTENT_TUNNEL.md` にワンタイムセットアップ
  15分の手順。これをやれば quick tunnel URL が毎回変わる問題が消える。

## ブランチ状態

- `dev` = `staging` = `0b7e81b` (push 済み)
- `main` は触れていない (`bf86899` のまま)
- 昇格コミット: `cd0a1b8` → `a2fd6ec` → `1980772` → `c4ffd9b` → `0b7e81b`

## 作業ログ URL

- GitHub: https://github.com/sosato587-blip/BlockFlow/tree/staging
- ドキュメント: `LTX_QUICKSTART.md` / `UX_AUDIT.md` / `SETUP_PERSISTENT_TUNNEL.md` / `R2_HISTORY_SCRUB_PLAN.md` / `AUTONOMOUS_REPORT_NIGHT2.md`
