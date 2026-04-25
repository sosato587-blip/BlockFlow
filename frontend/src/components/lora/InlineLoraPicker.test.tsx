/**
 * Minimal behavior tests for InlineLoraPicker.
 *
 * Assumes vitest + @testing-library/react (matching the pattern used by
 * `frontend/src/lib/lora-mapping.test.ts`). If BlockFlow's test setup differs,
 * adjust imports accordingly.
 */

import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"

import { InlineLoraPicker } from "./InlineLoraPicker"

const GROUPED = {
  grouped_high: {
    illustrious: ["illu_high_a.safetensors", "illu_high_b.safetensors"],
    wan_22: ["wan_high_a.safetensors"],
  },
  grouped_low: {
    illustrious: ["illu_low_a.safetensors"],
    wan_22: ["wan_low_a.safetensors"],
  },
}

function baseProps() {
  return {
    family: "illustrious",
    familyLabel: "Illustrious",
    groupedOptions: GROUPED,
    highPicks: [],
    lowPicks: [],
    onHighPicksChange: vi.fn(),
    onLowPicksChange: vi.fn(),
  }
}

describe("InlineLoraPicker", () => {
  it("renders both High Noise and Low Noise branches", () => {
    render(<InlineLoraPicker {...baseProps()} />)
    expect(screen.getByText("High Noise")).toBeInTheDocument()
    expect(screen.getByText("Low Noise")).toBeInTheDocument()
  })

  it("displays the family-aware counter in the header", () => {
    render(<InlineLoraPicker {...baseProps()} />)
    // 2 high + 1 low unique = 3 available for illustrious
    expect(
      screen.getByText(/0 added, 3 available for Illustrious/)
    ).toBeInTheDocument()
  })

  it("calls onHighPicksChange when the High Add button is clicked", () => {
    const onHigh = vi.fn()
    render(
      <InlineLoraPicker
        {...baseProps()}
        onHighPicksChange={onHigh}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: /Add High Noise LoRA/i }))
    expect(onHigh).toHaveBeenCalledTimes(1)
    const nextPicks = onHigh.mock.calls[0][0]
    expect(nextPicks).toHaveLength(1)
    expect(nextPicks[0].name).toBe("__none__")
    expect(nextPicks[0].strength).toBeCloseTo(1.0)
  })

  it("disables the Add button when maxPicksPerBranch is reached", () => {
    render(
      <InlineLoraPicker
        {...baseProps()}
        highPicks={[
          { id: "1", name: "illu_high_a.safetensors", strength: 1.0 },
          { id: "2", name: "illu_high_b.safetensors", strength: 0.8 },
        ]}
        maxPicksPerBranch={2}
      />
    )
    const addBtn = screen.getByRole("button", { name: /Add High Noise LoRA/i })
    expect(addBtn).toBeDisabled()
  })

  it("shows the disabled banner when disabled with a reason", () => {
    render(
      <InlineLoraPicker
        {...baseProps()}
        disabled
        disabledReason="External LoRA selector attached."
      />
    )
    expect(
      screen.getByText("External LoRA selector attached.")
    ).toBeInTheDocument()
  })

  it("shows the loading message when isLoading", () => {
    render(
      <InlineLoraPicker
        {...baseProps()}
        isLoading
        loadingMessage="Loading LoRA list..."
      />
    )
    expect(screen.getByText("Loading LoRA list...")).toBeInTheDocument()
  })

  it("shows the error message when errorMessage is set and not loading", () => {
    render(
      <InlineLoraPicker
        {...baseProps()}
        errorMessage="Fetch failed."
      />
    )
    expect(screen.getByText("Fetch failed.")).toBeInTheDocument()
  })

  it("renders the empty hint when there are no picks", () => {
    render(
      <InlineLoraPicker
        {...baseProps()}
        emptyHint="Add some LoRAs to get started."
      />
    )
    expect(
      screen.getByText("Add some LoRAs to get started.")
    ).toBeInTheDocument()
  })

  it("injects headerRightSlot content", () => {
    render(
      <InlineLoraPicker
        {...baseProps()}
        headerRightSlot={<button aria-label="Refresh">R</button>}
      />
    )
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument()
  })

  it("calls the correct remove handler when an X button is clicked", () => {
    const onHigh = vi.fn()
    render(
      <InlineLoraPicker
        {...baseProps()}
        highPicks={[
          { id: "a", name: "illu_high_a.safetensors", strength: 1.0 },
          { id: "b", name: "illu_high_b.safetensors", strength: 0.5 },
        ]}
        onHighPicksChange={onHigh}
      />
    )
    const removeButtons = screen.getAllByRole("button", {
      name: /Remove High Noise LoRA/i,
    })
    fireEvent.click(removeButtons[0])
    expect(onHigh).toHaveBeenCalledTimes(1)
    const next = onHigh.mock.calls[0][0]
    expect(next).toHaveLength(1)
    expect(next[0].id).toBe("b")
  })
})
