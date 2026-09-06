import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import en from "./locales/en.json";
import hi from "./locales/hi.json";
import { I18nProvider, LANGUAGE_STORAGE_KEY, UI_LANGUAGES } from "./i18n";

function renderApp() { return render(<I18nProvider><App /></I18nProvider>); }
const file = () => new File(["image"], "label.png", { type: "image/png" });
const result = { id: "inspection-1", inspection_number: "INSP-001", status: "COMPLETED", image: { id: "image-1", original_filename: "label.png" }, ocr: { raw_text: "MRP Rs 100", languages: ["en", "hi"], results: [] }, extraction: { fields: { manufacturer: { value: "ABC Foods", confidence: .94, needs_review: false }, mrp: { value: "Rs 100", confidence: .97, needs_review: false } } }, compliance: { overall_status: "REVIEW", summary: { passed: 1, failed: 0, review: 1 }, findings: [{ rule_id: "MRP_FORMAT", rule_name: "MRP format", status: "PASS", severity: "WARNING", message: "Valid MRP", field: "mrp", value: "Rs 100" }] } };

describe("inspection workflow UI", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });
  it("renders English and all language choices", () => { renderApp(); expect(screen.getByText(en.dashboard)).toBeTruthy(); expect(screen.getAllByRole("option")).toHaveLength(23); });
  it("persists a language choice", () => { renderApp(); fireEvent.change(screen.getByRole("combobox"), { target: { value: "hi" } }); expect(screen.getByText(hi.dashboard)).toBeTruthy(); expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("hi"); });
  it("has complete locale key sets", async () => { for (const language of UI_LANGUAGES) { const locale = await import(`./locales/${language.code}.json`); expect(Object.keys(locale.default).sort()).toEqual(Object.keys(en).sort()); } });
  it("uploads and automatically displays the complete persisted workflow", async () => {
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:label"), revokeObjectURL: vi.fn() });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ id: "inspection-1", inspection_number: "INSP-001" }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ id: "image-1", original_filename: "label.png" }) }).mockResolvedValueOnce({ ok: true, json: async () => result }));
    renderApp(); fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file()] } });
    await screen.findByText("MRP Rs 100"); expect(screen.getByText("ABC Foods")).toBeTruthy(); expect(screen.getByText("MRP format — PASS (WARNING)")).toBeTruthy(); expect(screen.getByText("Inspection complete")).toBeTruthy();
  });
  it("shows a recoverable failure", async () => {
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:label"), revokeObjectURL: vi.fn() }); vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({ detail: "Database unavailable." }) }));
    renderApp(); fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file()] } }); expect((await screen.findByRole("alert")).textContent).toContain("500: Database unavailable.");
  });
  it("starts a new inspection after completion", async () => {
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:label"), revokeObjectURL: vi.fn() }); vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ id: "inspection-1", inspection_number: "INSP-001" }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ id: "image-1" }) }).mockResolvedValueOnce({ ok: true, json: async () => result }));
    renderApp(); fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [file()] } }); await screen.findByText("Start New Inspection"); fireEvent.click(screen.getByText("Start New Inspection")); await waitFor(() => expect(screen.queryByText("MRP Rs 100")).toBeNull());
  });
});
