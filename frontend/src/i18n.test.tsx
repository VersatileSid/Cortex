import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import as from "./locales/as.json";
import bn from "./locales/bn.json";
import brx from "./locales/brx.json";
import doi from "./locales/doi.json";
import en from "./locales/en.json";
import gu from "./locales/gu.json";
import hi from "./locales/hi.json";
import kn from "./locales/kn.json";
import kok from "./locales/kok.json";
import ks from "./locales/ks.json";
import mai from "./locales/mai.json";
import ml from "./locales/ml.json";
import mni from "./locales/mni.json";
import mr from "./locales/mr.json";
import ne from "./locales/ne.json";
import or from "./locales/or.json";
import pa from "./locales/pa.json";
import sa from "./locales/sa.json";
import sat from "./locales/sat.json";
import sd from "./locales/sd.json";
import ta from "./locales/ta.json";
import te from "./locales/te.json";
import ur from "./locales/ur.json";
import { I18nProvider, LANGUAGE_STORAGE_KEY, UI_LANGUAGES, useI18n } from "./i18n";

const localeFiles = { en, hi, as, bn, brx, doi, gu, kn, ks, kok, mai, ml, mni, mr, ne, or, pa, sa, sat, sd, ta, te, ur };
const translatedUiKeys = Object.keys(en).filter((key) => !["appName", "mrp"].includes(key)) as Array<keyof typeof en>;

function assertNativeUiValues(locale: typeof en, code: string) {
  translatedUiKeys.forEach((key) => {
    if (locale[key] === en[key]) throw new Error(`${code}.${key} copies the English UI value`);
  });
}

function LanguageProbe() {
  const { locale, setLocale, t } = useI18n();
  return <><p>{t("dashboard")}</p><select aria-label={t("language")} value={locale} onChange={(event) => setLocale(event.target.value as typeof locale)}>{UI_LANGUAGES.map(({ code, nativeName }) => <option key={code} value={code}>{nativeName}</option>)}</select></>;
}

function renderApp() { return render(<I18nProvider><App /></I18nProvider>); }

describe("translations", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => { cleanup(); localStorage.clear(); vi.unstubAllGlobals(); });

  it("renders English values by default", () => {
    renderApp();
    expect(screen.getByText(en.dashboard)).toBeTruthy();
    expect(screen.getByText(en.tagline)).toBeTruthy();
    expect(screen.getByText(en.uploadImage)).toBeTruthy();
  });

  it.each([["hi", hi], ["gu", gu], ["ta", ta], ["doi", doi], ["ur", ur]] as const)("immediately renders native %s UI values and persists the selection", (code, locale) => {
    renderApp();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: code } });
    expect(screen.getByText(locale.dashboard)).toBeTruthy();
    expect(screen.getByText(locale.tagline)).toBeTruthy();
    expect(screen.getByText(locale.uploadImage)).toBeTruthy();
    expect(screen.getByText(locale.imagePreview)).toBeTruthy();
    expect(screen.queryByText(en.tagline)).toBeNull();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe(code);
  });

  it("restores a persisted locale and uses RTL for Urdu", () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "ur");
    renderApp();
    expect(screen.getByText(ur.dashboard)).toBeTruthy();
    expect(document.documentElement.lang).toBe("ur");
    expect(document.documentElement.dir).toBe("rtl");
  });

  it("rejects an invalid stored locale and restores English", () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "unsupported");
    render(<I18nProvider><LanguageProbe /></I18nProvider>);
    expect(screen.getByText(en.dashboard)).toBeTruthy();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
  });

  it("includes all 23 languages in its selector", () => {
    renderApp();
    expect(screen.getAllByRole("option")).toHaveLength(23);
  });

  it("requires complete locale files with actual non-English UI values", () => {
    const englishKeys = Object.keys(en).sort();
    UI_LANGUAGES.filter(({ code }) => code !== "en").forEach(({ code }) => {
      const locale = localeFiles[code];
      expect(Object.keys(locale).sort()).toEqual(englishKeys);
      expect(() => assertNativeUiValues(locale, code)).not.toThrow();
    });
  });

  it("detects an English-copy dashboard translation", () => {
    const badHindi = { ...hi, dashboard: en.dashboard };
    expect(() => assertNativeUiValues(badHindi, "hi")).toThrow("hi.dashboard copies the English UI value");
  });

  it("keeps OCR output unchanged when the UI language changes", async () => {
    const rawText = "MRP ₹100\nManufactured by ABC Foods";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ id: "inspection-1", inspection_number: "INSP-001" }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ id: "image-1", original_filename: "label.png" }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ raw_text: rawText, languages: ["en"], results: [] }) }));
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:label"), revokeObjectURL: vi.fn() });
    renderApp();
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [new File(["image"], "label.png", { type: "image/png" })] } });
    await screen.findByRole("status");
    fireEvent.click(screen.getByRole("button", { name: en.scanLabel }));
    await waitFor(() => expect(document.querySelector(".raw-text")?.textContent).toBe(rawText));
    for (const code of ["hi", "gu", "ta", "doi", "ur"]) fireEvent.change(screen.getByRole("combobox"), { target: { value: code } });
    expect(document.querySelector(".raw-text")?.textContent).toBe(rawText);
  });

  it("renders translated extraction labels while preserving extracted values", async () => {
    const rawText = "MRP ₹100\nManufactured by ABC Foods";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ id: "inspection-1", inspection_number: "INSP-001" }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ id: "image-1", original_filename: "label.png" }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ raw_text: rawText, languages: ["en"], results: [] }) }).mockResolvedValueOnce({ ok: true, json: async () => ({ fields: { manufacturer: { value: "ABC Foods", confidence: 0.94, needs_review: false }, importer: { value: null, confidence: 0, needs_review: false } } }) }));
    vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:label"), revokeObjectURL: vi.fn() });
    renderApp();
    fireEvent.change(document.querySelector('input[type="file"]')!, { target: { files: [new File(["image"], "label.png", { type: "image/png" })] } });
    await screen.findByRole("status");
    fireEvent.click(screen.getByRole("button", { name: en.scanLabel }));
    await waitFor(() => expect(document.querySelector(".raw-text")?.textContent).toBe(rawText));
    fireEvent.click(screen.getByRole("button", { name: en.extractInformation }));
    expect(await screen.findByText("ABC Foods")).toBeTruthy();
    expect(screen.getByText(en.extractionManufacturer)).toBeTruthy();
    expect(screen.getByText(en.extractionImporter)).toBeTruthy();
    expect(screen.getByText(en.notDetected)).toBeTruthy();
    for (const [code, locale] of [["hi", hi], ["gu", gu], ["ta", ta], ["doi", doi], ["ur", ur]] as const) {
      fireEvent.change(screen.getByRole("combobox"), { target: { value: code } });
      expect(screen.getByText(locale.extractionManufacturer)).toBeTruthy();
      expect(screen.getByText(locale.extractionImporter)).toBeTruthy();
      expect(screen.getByText(locale.notDetected)).toBeTruthy();
      expect(screen.getByText("ABC Foods")).toBeTruthy();
    }
    expect(document.querySelector(".raw-text")?.textContent).toBe(rawText);
  });
});
