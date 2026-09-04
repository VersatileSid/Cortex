import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { I18nProvider, LANGUAGE_STORAGE_KEY, useI18n } from "./i18n";
import App from "./App";

function LanguageProbe() {
  const { locale, setLocale, t } = useI18n();
  return <><p>{t("dashboard")}</p><select aria-label={t("language")} value={locale} onChange={(event) => setLocale(event.target.value as "en" | "hi")}><option value="en">English</option><option value="hi">हिन्दी</option></select></>;
}

describe("translations", () => {
  beforeEach(() => localStorage.clear());

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

  it("renders the inspection workspace in the selected language", () => {
    render(<I18nProvider><App /></I18nProvider>);
    expect(screen.getByText("Package-label inspection assistance")).toBeTruthy();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "hi" } });
    expect(screen.getByText("पैकेज-लेबल निरीक्षण सहायता")).toBeTruthy();
    expect(screen.getByText("पैकेज चित्र अपलोड करें")).toBeTruthy();
  });
});
