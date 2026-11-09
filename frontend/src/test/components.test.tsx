import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JobProgress, SevChip, StatusChip, fmt, pct } from "../components/ui";
import { mergeSeries } from "../components/charts";
import { api, ApiError } from "../services/api";
import type { Finding, Job } from "../types/api";

vi.mock("../app/AppState", () => ({ useApp: () => ({ project: null }) }));
import { FindingsTable } from "../features/findings";

const f = (id: string, severity: Finding["severity"], status: Finding["status"], title: string): Finding => ({
  id, rule: "X.Y", category: "dataset", severity, status, title, evidence: {}, source: "a.jsonl", explanation: "e", recommendation: "r",
});

describe("formatting", () => {
  it("formats numbers without inventing values", () => {
    expect(fmt(null)).toBe("—");
    expect(fmt(1234)).toBe("1,234");
    expect(fmt(0.12345678)).toBe("0.1235");
    expect(fmt(0.00002)).toBe("2.00e-5");
    expect(pct(0.1154)).toBe("11.54%");
    expect(pct(undefined)).toBe("—");
  });
});

describe("chips", () => {
  it("renders severity and status labels", () => {
    render(<><SevChip s="CRITICAL" /><StatusChip s="POTENTIAL" /></>);
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getByText("POTENTIAL")).toBeInTheDocument();
  });
});

describe("JobProgress", () => {
  const base: Job = { id: "j", kind: "audit", status: "running", created: "", project_id: "p", message: "step", progress_done: null, progress_total: null };
  it("uses an indeterminate bar when progress is unknown", () => {
    const { container } = render(<JobProgress job={base} />);
    expect(container.querySelector(".progress-indeterminate")).not.toBeNull();
  });
  it("shows real progress and a cancel button", () => {
    const onCancel = vi.fn();
    render(<JobProgress job={{ ...base, progress_done: 2, progress_total: 4 }} onCancel={onCancel} />);
    expect(screen.getByText(/2\/4/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalled();
  });
});

describe("FindingsTable", () => {
  it("filters by severity and text", () => {
    render(<FindingsTable findings={[f("DMI-001", "HIGH", "CONFIRMED", "Exact duplicates"), f("DMI-002", "LOW", "POTENTIAL", "Plateau")]} />);
    expect(screen.getByText("Exact duplicates")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter by severity"), { target: { value: "LOW" } });
    expect(screen.queryByText("Exact duplicates")).toBeNull();
    expect(screen.getByText("Plateau")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search findings"), { target: { value: "zzz" } });
    expect(screen.getByText(/No findings for the current filters/)).toBeInTheDocument();
  });
});

describe("mergeSeries", () => {
  it("aligns series by step", () => {
    const rows = mergeSeries({ a: [[1, 2], [2, 3]], b: [[2, 5]] }, ["a", "b"]);
    expect(rows).toEqual([{ step: 1, a: 2 }, { step: 2, a: 3, b: 5 }]);
  });
});

describe("api client", () => {
  it("surfaces backend error details", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "security: path outside authorized roots" }), { status: 403 })));
    await expect(api.status()).rejects.toThrow("security: path outside authorized roots");
  });
  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    await expect(api.status()).rejects.toBeInstanceOf(ApiError);
  });
});
