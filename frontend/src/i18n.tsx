import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import en from "./locales/en.json";
import hi from "./locales/hi.json";

export type Locale = "en" | "hi";
export const LANGUAGE_STORAGE_KEY = "labelguard-language";

const translations = { en, hi } as const;
type TranslationKey = keyof typeof en;

type I18nValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey) => string;
};

const I18nContext = createContext<I18nValue | null>(null);

function initialLocale(): Locale {
  return localStorage.getItem(LANGUAGE_STORAGE_KEY) === "hi" ? "hi" : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>(initialLocale);

  useEffect(() => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, locale);
    document.documentElement.lang = locale === "hi" ? "hi" : "en";
    document.documentElement.dir = "ltr";
  }, [locale]);

  const value = useMemo<I18nValue>(() => ({
    locale,
    setLocale,
    t: (key) => translations[locale][key],
  }), [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside I18nProvider.");
  return context;
}
