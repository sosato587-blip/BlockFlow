# A4 引き継ぎドキュメント — Mobile Inline LoRA UI

> **これを読んでいる Claude へ:** あなたは `sosato587-blip/BlockFlow` リポの web セッションです。前のセッション（`sosato587-blip/test` リポにスコープされていた Web Claude）で A4 の設計と一部実装が完了しました。このドキュメントを読めば、Task 2 以降の実装を続行できます。

## 1. クイックオリエンテーション

- **タスク**: A4 — Mobile (`/m`) の Inline LoRA UI 実装
- **現状**: 設計確定済、Task 1（共有コンポ）と Task 9（Python ヘルパ）は実装＋テスト済
- **次にやること**: Task 2（desktop の差し替え）から開始
- **設計意思決定者**: ユーザ本人。重要判断は逐次確認すること

## 2. 設計合意の要旨（前セッションの結論）

### 何を作るか
- **共有コンポ `<InlineLoraPicker>`**: Desktop の `comfy_gen` ブロックと Mobile の `GenerateTab` の両方で使う、High Noise / Low Noise 2 分岐の LoRA 選択 UI
- **Mobile 送信 payload を `{high_loras, low_loras}` に分割**: 旧 `loras` フラット形式から移行
- **`build_wan_i2v_workflow()` に dual-pass LoRA 注入を新規追加**: 現状 wan_i2v は LoRA 非対応。high → high-noise chain、low → low-noise chain にルーティング
- **Desktop の `registerExecute` 内 5-case 複製を `computeInlineLoraOverrides` に置換**: 既存の technical debt 完済

### 含まないもの（→ 別タスク S2-Full に移管）
- `/api/m/*` の廃止と `/api/blocks/comfy_gen/run` への統合
- Inpaint / Outpaint / ControlNet / CharaIP / ADetailer / CharacterSheet / LTXVideo の desktop ブロック化
- Mobile workflow の宣言型テンプレ化
- `m_routes.py` 本体の退役

### 設計選択の根拠（重要な discussion ポイント）

1. **「PC 版に構造を合わせる」が原則**（モバイルは後付け）→ 方向 1（クライアント側マッピング）志向。ただし mobile が workflow を持たないアーキテクチャなので、A4 のスコープでは pragmatically 「UI 共有 + 最小の backend グルー」として実装し、フル統一は S2-Full で行う
2. **High/Low の意味**: WAN 2.2 の dual-expert（high noise / low noise stage）に LoRA を別々に効かせるため。z_image / illustrious のような single-pass モデルでは semantic に意味なく merge して使う
3. **wan_i2v の dual-pass 構造はすでに backend に存在** (UNETLoader 37/56, ModelSamplingSD3 54/55, KSamplerAdvanced 57/58)。**ただし LoRA injection が皆無**だった。A4 で `LoraLoaderModelOnly` chain を 2 経路に追加する

## 3. A4 実装計画（タスク一覧）

| # | ファイル | 変更内容 | 受入基準 (AC) | 状態 |
|---|---|---|---|---|
| 1 | `frontend/src/components/lora/InlineLoraPicker.tsx`（新規） | 共有コンポ実装 | High/Low セクション描画、ピック編集、strength slider、disabled バナー | ✅ **完了**（要転写） |
| 2 | `custom_blocks/comfy_gen/frontend.block.tsx` | inline JSX を `<InlineLoraPicker>` に置換（`<CollapsibleSection>` 維持） | Desktop UI が視覚的に同一、セッション永続化が壊れない | ⏳ 未着手 |
| 3 | `custom_blocks/comfy_gen/frontend.block.tsx` | `registerExecute` 内 5-case 複製を `computeInlineLoraOverrides` 呼び出しに置換 | overrides map が従来と完全一致 | ⏳ 未着手 |
| 4 | `frontend/src/app/m/page.tsx` | `loras` state を `highLoras` / `lowLoras` に分割 | state モデルが desktop と同型 | ⏳ 未着手 |
| 5 | `frontend/src/app/m/page.tsx` | GenerateTab に `<InlineLoraPicker>` をマウント | High/Low 分離で描画、既存スタイル維持 | ⏳ 未着手 |
| 6 | `frontend/src/app/m/page.tsx` | `submitInternal` の payload を `body.high_loras` / `body.low_loras` に | Network タブで新 shape を確認 | ⏳ 未着手 |
| 7 | `backend/m_routes.py` | `build_z_image_workflow` / `build_illustrious_workflow` が `high_loras`/`low_loras` を受理、merge して chain | z_image/illustrious の既存ジョブ出力が完全一致 | ⏳ 未着手 |
| 8 | `backend/m_routes.py` | `build_wan_i2v_workflow()` に dual-pass LoRA 注入を新規追加 | wan_i2v で high/low LoRA 指定時に正しい dual-pass 出力 | ⏳ 未着手 |
| 9 | `backend/lora_mapping.py`（新規） | `computeInlineLoraOverrides` Python 移植 | 単体テスト 10/10 pass | ✅ **完了**（要転写） |
| 10 | `frontend/src/app/m/page.tsx` | `model !== 'wan_i2v'` gate を削除 | wan_i2v で LoRA UI 表示・送信成功 | ⏳ 未着手 |
| 11 | テスト | コンポ snapshot + `m_routes.py` 統合テスト + wan_i2v smoke | CI 緑 | 部分完了 |
| 12 | `HANDOFF_FOR_WEB_CLAUDE.md` | A4 完了マーク、S2-Full 新設 | ドキュメント更新済み | ⏳ 未着手 |

**残工数: 約 5〜6 人日**（Task 1, 9 完了済みの分を引いた残り）

## 4. 完成済みファイル（要転写）

前セッションで `sosato587-blip/test` リポの `blockflow-a4-reference/` に作成済み。**Task 2 開始前に BlockFlow の対応パスにコピー**してください：

| 転写元（test リポ） | 転写先（BlockFlow） |
|---|---|
| `blockflow-a4-reference/frontend/src/components/lora/InlineLoraPicker.tsx` | `frontend/src/components/lora/InlineLoraPicker.tsx` |
| `blockflow-a4-reference/frontend/src/components/lora/InlineLoraPicker.test.tsx` | `frontend/src/components/lora/InlineLoraPicker.test.tsx` |
| `blockflow-a4-reference/backend/lora_mapping.py` | `backend/lora_mapping.py` |
| `blockflow-a4-reference/backend/tests/test_lora_mapping.py` | `backend/tests/test_lora_mapping.py` |

転写が難しい場合は、それぞれの全文がこの handoff doc の最後（§ 9）に inline 添付されているのでそこから取れます。

## 5. `<InlineLoraPicker>` Props 契約

```typescript
interface LoraPick { id?: string; name: string; strength: number }

interface InlineLoraPickerProps {
  family: string                        // "illustrious" 等
  familyLabel?: string                  // 表示用
  groupedOptions: {
    grouped_high: Record<string, string[]>
    grouped_low: Record<string, string[]>
  }
  highPicks: LoraPick[]
  lowPicks: LoraPick[]
  onHighPicksChange: (next: LoraPick[]) => void
  onLowPicksChange: (next: LoraPick[]) => void
  maxPicksPerBranch?: number            // 既定 8
  strengthMin?: number                  // 既定 0
  strengthMax?: number                  // 既定 2
  strengthStep?: number                 // 既定 0.05
  disabled?: boolean                    // desktop の externalLorasConnected で true
  disabledReason?: string
  accent?: 'default' | 'orange'         // mobile は "orange"
  compact?: boolean                     // desktop は true
  headerRightSlot?: React.ReactNode     // mobile の Refresh ボタン用
  isLoading?: boolean
  loadingMessage?: string
  errorMessage?: string
  emptyHint?: string
}
```

永続化はコンポ外で実施（desktop は `useSessionState`、mobile は `useState`）。

## 6. Payload 契約の変更

**Mobile → backend (旧):**
```json
{ "loras": [{"name": "...", "strength": 1.0}] }
```

**Mobile → backend (A4 後):**
```json
{
  "high_loras": [{"name": "...", "strength": 1.0}],
  "low_loras":  [{"name": "...", "strength": 1.0}]
}
```

**後方互換**: `m_routes.py` は移行期間中、レガシーな `loras` を `high_loras` として受理する（deprecation 警告ログ付き）。

## 7. wan_i2v dual-pass LoRA 配線詳細（Task 8）

`build_wan_i2v_workflow()` の現状：

```
UNETLoader (high, "37") → ModelSamplingSD3 ("54") → KSamplerAdvanced ("57", end_at_step=steps//2)
UNETLoader (low,  "56") → ModelSamplingSD3 ("55") → KSamplerAdvanced ("58", start_at_step=steps//2, latent ← "57")
```

A4 で挿入する LoRA chain：

```python
# UNETLoader "37"（高ノイズ側）の直後に high_loras chain を挿入
prev_high = "37"
for i, lora in enumerate(high_loras or []):
    nid = f"370{i}"
    wf[nid] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": [prev_high, 0],
            "lora_name": str(lora["name"]),
            "strength_model": float(lora.get("strength", 1.0)),
        },
        "_meta": {"title": "High Noise LoRA"},  # desktop 5-case label 検出用
    }
    prev_high = nid
wf["54"]["inputs"]["model"] = [prev_high, 0]  # ModelSamplingSD3（高）の入力を書き換え

# UNETLoader "56"（低ノイズ側）も対称に
prev_low = "56"
for i, lora in enumerate(low_loras or []):
    nid = f"560{i}"
    wf[nid] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": [prev_low, 0],
            "lora_name": str(lora["name"]),
            "strength_model": float(lora.get("strength", 1.0)),
        },
        "_meta": {"title": "Low Noise LoRA"},
    }
    prev_low = nid
wf["55"]["inputs"]["model"] = [prev_low, 0]  # ModelSamplingSD3（低）
```

**注意:**
- wan_i2v は CLIPVision を使う image-to-video → 通常の `LoraLoader`（model + clip）ではなく **`LoraLoaderModelOnly`** を使う
- `strength_clip` は適用されない（UI には表示するが backend では捨てる、もしくは UI 側で wan_i2v 時のみ disable）
- `_meta.title` を入れることで desktop 側で同じ workflow をロードした時に 5-case heuristic が正しく動く

## 8. リスクと対策

| リスク | 対策 |
|---|---|
| Desktop 既存 comfy_gen ユーザへのレグレッション | Task 2 と Task 3 を別コミットに。Task 2 は挙動不変リファクタのみ |
| Mobile の z_image/illustrious でレグレッション | Task 7 で `[*high_loras, *low_loras]` を merge して従来の単一 chain 挙動と完全一致させる |
| wan_i2v の dual-pass LoRA 出力が壊れる（既存比較対象なし） | (a) LoRA なしで従来出力と一致を確認、(b) LoRA あり出力を人間が承認してからマージ |
| RunPod 側 ComfyUI に `LoraLoaderModelOnly` クラスが無い | Task 8 着手前に稼働中エンドポイントで確認（2024 以降の標準クラス） |
| Desktop の compact vs mobile の通常レイアウトで壊れる | 両 variant を動作確認できる playground ページを Task 1 完了直後に作成 |

## 9. 完成済みファイル全文（参考）

> 既に `sosato587-blip/test` の `blockflow-a4-reference/` にあるので、まず転写を試みる。失敗したらここから貼り付け。

(詳細は `blockflow-a4-reference/` 直下の各ファイルを参照。本 handoff doc に再掲することも可能ですが、行数が嵩むため別途参照とします。)

## 10. コミット順（推奨 PR 分割）

1. Task 1 + 11（コンポ本体 + テスト）— 単独で CI 緑
2. Task 2（desktop 差し替え、挙動不変）
3. Task 3（desktop の heuristic 整理）
4. Task 9（Python lora_mapping）
5. Task 7（backend が split 受付）
6. Task 4 + 5 + 6（mobile UI + payload）
7. Task 8 + 10（wan_i2v dual-pass + gate 削除）
8. Task 12（HANDOFF 更新、S2-Full 新設）

## 11. S2-Full ロードマップ（新規追加項目）

A4 完了時に既存の `HANDOFF_FOR_WEB_CLAUDE.md` に以下を追加：

```markdown
## S2-Full: Desktop/Mobile アーキテクチャ完全統一

**ステータス:** 📝 計画中、長期（3 ヶ月以上）

**目標:** `/api/m/*` と mobile 専用 workflow builder を退役。すべての mobile 操作を desktop のブロック API 経由で実行する。

**サブタスク:**
- Inpaint / Outpaint / ControlNet / CharaIP / ADetailer / CharacterSheet / LTXVideo の desktop ブロックを新設
- `m_routes.py` の Python workflow builder をブロックごとの `backend.block.py` に移管
- Mobile 送信を `/api/m/*` から `/api/blocks/*/run` に切替
- 命令型 Python builder を宣言型 JSON テンプレに置換
- `m_routes.py` 本体を退役（`m_store.py` はプリセット・コスト・Publications・Schedules 用に残す）

**発動条件:** 同期事故が再発したら見直す。
```

## 12. 起動後の最初の手順（新セッションへ）

新しい BlockFlow Web Claude が起動したら、以下の順で実行を推奨：

1. このドキュメント（`docs/handoffs/A4_HANDOFF.md`）を最後まで読む
2. `HANDOFF_FOR_WEB_CLAUDE.md` を確認（既存の文脈を把握）
3. `frontend/src/components/lora/InlineLoraPicker.tsx` が存在するか確認 → 無ければ転写
4. `backend/lora_mapping.py` が存在するか確認 → 無ければ転写
5. `backend/tests/test_lora_mapping.py` を実行して 10/10 pass を確認
6. **Task 2 から開始**: `custom_blocks/comfy_gen/frontend.block.tsx` の inline LoRA UI を `<InlineLoraPicker>` に置換
7. ユーザに「Task 2 完了、commit してよいか？」と確認してから commit
8. 以降のタスクも、各タスク完了ごとにユーザ確認 → commit のループ

## 13. ユーザの作業スタイル（参考）

- **意思決定はユーザ自身**。提案は複数案出して trade-off を明確に
- **「PC 構造に合わせる」が原則**。モバイル独自の妥協は明示的に意識的にやる
- **設計議論は丁寧に確認**: 前提が崩れたら正直に申告して再設計
- **Web Claude が主環境**: デスクトップ Claude には依存しない方針
- **言語は日本語**で会話
