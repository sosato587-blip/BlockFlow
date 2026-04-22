# Morning Report — 2026-04-22

おはようございます。夜間に以下を進めました。

## 1. 今夜のコミット

すべて `main` に fast-forward 済み（`dev → staging → main`）。

| ハッシュ | 内容 |
|---|---|
| `ba25d1c` | feat(labels): official-name-only family labels + hide empty families |
| `f0066a7` | feat(comfy_gen): robust LoRA-node mapping heuristic |
| `<doc>`  | docs: morning report（このファイル） |

詳細:

- **`ba25d1c`** — ベースモデルの family ラベルを「公式名のみ」に変更
  - `Illustrious (anime)` → `Illustrious XL`
  - `Z-Image Turbo (realistic)` → `Z-Image Turbo`
  - `Wan 2.2 (video)` → `Wan 2.2`
  - `LTX Video (fast video)` → `LTX Video`
  - `sdxl` / `flux` / `unknown` の 3 family を削除（checkpoint 未登録だった）
  - `base_model_selector` の family ドロップダウンが checkpoint 未登録の family を自動的に隠す（将来新 family 追加時の「空の選択肢」を防止）
  - `frontend/tests/e2e/smoke.spec.ts` の期待値を更新

- **`f0066a7`** — ComfyGen の inline LoRA ピックを loader node へマップするヒューリスティックを強化
  - LoRA loader が **1 個** のワークフロー → High/Low 両方を詰め込む（単一パスグラフでは区別不要）
  - **2 個以上** で label に `high`/`low` が含まれる → ラベルで分岐（従来通り）
  - **ちょうど 2 個** で label なし → ノード順で `[high, low]` とみなす
  - LoRA loader が **0 個** で inline ピックが設定されている場合、UI に黄色の警告を表示（無視される旨を通知）

## 2. 起床後、ミニPC で確認してほしいこと

```powershell
cd C:\Users\sato\BlockFlow
git pull origin main
# BlockFlow 再起動（ミニPC）
# 1. 既存の uv run app.py を Ctrl+C で止める
# 2. uv run app.py を再起動
# 3. npm run dev をしている場合は再起動不要（Next.js が HMR で拾う）
# 4. cloudflared tunnel は基本そのままで OK（URL 固定していれば）
```

ブラウザで確認:

- [ ] `/generate` を **Ctrl+Shift+R**（ハードリロード）で開く
- [ ] ComfyGen ブロックを展開し、「Base Model (inline)」と「LoRAs (inline)」セクションが見える
- [ ] Base Model Selector ブロックのドロップダウンが **Illustrious XL / Z-Image Turbo / Wan 2.2 / LTX Video** の 4 件のみ（`SDXL (generic)` / `Flux` / `Other / uncategorized` が消えている）
- [ ] スマホで `/m` を開き、model を切り替えると LoRA 一覧が family でフィルタされる
- [ ] Endpoint ID 入力欄が「RunPod settings」セクションに移動済み（Advanced の奥に埋もれていない）

ComfyGen の LoRA マッピング改善を確認したい場合:

- [ ] Illustrious 用の 1-loader ワークフロー（`workflow_anime_nsfw.json` など）をロード
- [ ] inline LoRA の High にキャラ LoRA、Low にディテール系 LoRA を 1 つずつ追加
- [ ] Generate して、両方ともワークフローに注入されているかログで確認

## 3. 外出前に人間がやること（Claude には不可）

- **cloudflared 恒久トンネル化**（未実施）
  - `C:\Users\sato\BlockFlow\SETUP_PERSISTENT_TUNNEL.md` の手順をミニPC で実施
  - やるメリット: URL が `*.trycloudflare.com` の固定 URL になり、cloudflared ターミナルを閉じても失効しない
  - やらないと: 毎回ユーザーに URL を聞かないといけない

- **LoRA ヒューリスティックの実動作テスト** — 上の checklist 参照。バッチを走らせる前に 1 枚単発で動作確認するのが安全

## 4. 外出後 Claude が勝手にやってよいこと

コスト・GPU を消費しない範囲:

- UX_AUDIT.md 残項目の UI ポリッシュ（ラベル調整、disabled-state hint、spinner 追加など）
- ドキュメント整理
- 型付け改善、リファクタ
- 既存 lint error（21 件残っている）の段階的解消 — ただし「本日の変更が起因ではない」pre-existing error は優先度低

**コスト発生作業は事前承認必須**:

- RunPod バッチ生成（12 枚以上）
- モデル DL（R2 経由で数 GB 単位）
- H3 Phase 3 比較テスト 15 本の再実行
- Z-Image 版リアル女性 30 パターン再実行

## 5. 動画モデル用ブロックの設計（未決・要議論）

**重要**: 今夜の「ComfyGen インライン化（案B）」は **画像生成用の設計**。動画モデルは以下の理由で同じパターンを機械的に適用しない方がよい。

- **WAN 2.2 I2V / Fun Control**: high_noise + low_noise の 2 checkpoint 2-pass 構造が物理的に必要。LoRA も high/low で明示的に振り分ける必要があり、ComfyGen のヒューリスティックとは違う専用 UI が望ましい。
- **LTX Video**: text encoder (`t5xxl`) や VAE 構成など、画像モデルと違う前処理が必要。
- 現状、動画ワークフローが本格実運用されていない（`wan_22_image_to_video` / `wan_fun_control` ブロックは存在するがユーザー側で workflow 組み立て中）ため、**最適な UI パターンを確定させる段階に達していない**。

方針: 動画ブロックは当面「専用ブロック + 明示的な high/low 入力」のまま据え置き、実ユースケース（動画ワークフロー完成後）を見てから UI を再検討。画像ブロックと同じ「1ブロックに全部インライン」は動画側では採用しない予定。

## 6. 未解決 / ユーザー判断が必要な点

1. **UX_AUDIT の残りの「H」項目** — quick wins は `f937e84` で着地済み。残りは `comfy_gen` の「shared FormField wrapper」「centralized error UI」など、アーキ寄りで仕様確認が必要。時間と優先度の確認をお願いします。

2. **LoRA ヒューリスティックの実データ検証** — 今夜のロジック改善は理論ベース。実ワークフロー（特に Wan 2.2 の 2-pass グラフ、label が `"LoraLoaderModelOnly_HighNoise"` のようなケース）で正しく分岐するかは実行してみるまで不明。

3. **`smoke.spec.ts` のテスト実行環境** — Playwright の実行はこの PC（dev/code）では行わず、モック環境が立っているミニPC で走らせる想定。`npm run test:e2e` 相当を回してもらえると、今夜の family 変更でテストが通るか確定できます。

4. **`lora_selector` の `base_model` 未接続時の挙動** — 現状「family=illustrious を default にして動く」。ユーザー的にそれで OK か、それとも「family 未指定なら全 LoRA を alphabetical で出す」ほうが良いか、要判断。

---

**要注意**: このブランチ（`main` / `dev` / `staging` 全部）は今夜の 3 コミットで先行しているので、ミニPC の pull 順序は `git pull origin main` 一発で OK。お疲れさまでした。
