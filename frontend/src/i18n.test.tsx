import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import App from "./App";
import { I18nProvider, LANGUAGE_STORAGE_KEY, UI_LANGUAGES, useI18n } from "./i18n";

function LanguageProbe() {
  const { locale, setLocale, t } = useI18n();
  return <><p>{t("dashboard")}</p><select aria-label={t("language")} value={locale} onChange={(event) => setLocale(event.target.value as typeof locale)}>{UI_LANGUAGES.map(({ code, nativeName }) => <option key={code} value={code}>{nativeName}</option>)}</select></>;
}

describe("translations", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => { cleanup(); localStorage.clear(); });

  it("loads English by default", () => {
    render(<I18nProvider><LanguageProbe /></I18nProvider>);
    expect(screen.getByText("Dashboard")).toBeTruthy();
  });

  it("switches the rendered UI to Hindi and persists the choice", () => {
    render(<I18nProvider><LanguageProbe /></I18nProvider>);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "hi" } });
    expect(screen.getByText("डैशबोर्ड")).toBeTruthy();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("hi");
  });

  it("loads the persisted Hindi selection", () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "hi");
    render(<I18nProvider><LanguageProbe /></I18nProvider>);
    expect(screen.getByText("डैशबोर्ड")).toBeTruthy();
  });

  it("falls back to English for an invalid stored language", () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "unsupported");
    render(<I18nProvider><LanguageProbe /></I18nProvider>);
    expect(screen.getByText("Dashboard")).toBeTruthy();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
  });

  it("lists all configured languages in one accessible selector", () => {
    render(<I18nProvider><App /></I18nProvider>);
    expect(screen.getAllByRole("combobox")).toHaveLength(1);
    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(UI_LANGUAGES.length);
    UI_LANGUAGES.forEach(({ nativeName }) => expect(screen.getByRole("option", { name: new RegExp(nativeName) })).toBeTruthy());
  });

  it("can select every UI language without crashing and preserves OCR text", () => {
    const printedPackageText = "निर्माता ₹50";
    render(<I18nProvider><><LanguageProbe /><pre>{printedPackageText}</pre></></I18nProvider>);
    const selector = screen.getByRole("combobox");
    UI_LANGUAGES.forEach(({ code }) => fireEvent.change(selector, { target: { value: code } }));
    expect(screen.getByText(printedPackageText)).toBeTruthy();
  });
});
