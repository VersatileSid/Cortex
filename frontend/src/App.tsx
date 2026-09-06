import { ChangeEvent, useEffect, useState } from "react";
import { UI_LANGUAGES, useI18n } from "./i18n";

type Inspection = { id: string; inspection_number: string };
type UploadedImage = { id: string; original_filename: string };
type OcrResult = { raw_text: string; languages: string[]; results: Array<{ text: string; confidence: number | null; bbox: number[][] | null }> };
type ExtractionField = { value: string | null; confidence: number; needs_review: boolean };
type ExtractionResult = { fields: Record<string, ExtractionField> };
type ComplianceFinding = { rule_id: string; rule_name: string; status: "PASS" | "FAIL" | "REVIEW"; severity: "INFO" | "WARNING" | "CRITICAL"; message: string; field: string | null; value: string | null; confidence: number | null; evidence: string | null };
type ComplianceResult = { overall_status: "PASS" | "FAIL" | "REVIEW"; summary: { passed: number; failed: number; review: number }; findings: ComplianceFinding[] };
type MessageKey = "imageUploaded" | "uploadFailed" | "ocrComplete" | "ocrFailed" | "extractionFailed";
type ApiError = Error & { detail?: string };

const extractionFieldLabels = {
  product_name: "extractionProductName", manufacturer: "extractionManufacturer", manufacturer_address: "extractionManufacturerAddress",
  packer: "extractionPacker", packer_address: "extractionPackerAddress", importer: "extractionImporter", importer_address: "extractionImporterAddress",
  mrp: "extractionMrp", net_quantity: "extractionNetQuantity", manufacturing_date: "extractionManufacturingDate",
  packing_date: "extractionPackingDate", best_before: "extractionBestBefore", use_by: "extractionUseBy", expiry_date: "extractionExpiryDate",
  consumer_care_phone: "extractionConsumerCarePhone", consumer_care_email: "extractionConsumerCareEmail", consumer_care_website: "extractionConsumerCareWebsite",
} as const;

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

async function apiError(response: Response, operation: string): Promise<ApiError> {
  let detail = "";
  try {
    const body = await response.json();
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    // A non-JSON error response still has a useful HTTP status below.
  }
  const error = new Error(operation) as ApiError;
  if (import.meta.env.DEV) error.detail = `${response.status}${detail ? `: ${detail}` : ""}`;
  return error;
}

function LanguageSelector() {
  const { locale, setLocale, t } = useI18n();
  return <label className="language-selector"><span>{t("language")}</span><select aria-label={t("language")} value={locale} onChange={(event) => setLocale(event.target.value as typeof locale)}>{UI_LANGUAGES.map(({ code, nativeName, englishName }) => <option key={code} value={code}>{nativeName} — {englishName}</option>)}</select></label>;
}

export default function App() {
  const { t } = useI18n();
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [image, setImage] = useState<UploadedImage | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [ocr, setOcr] = useState<OcrResult | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [compliance, setCompliance] = useState<ComplianceResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; key: MessageKey; detail?: string } | null>(null);

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  async function selectImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(file));
    setBusy(true); setMessage(null); setOcr(null); setExtraction(null); setCompliance(null);
    try {
      const inspectionResponse = await fetch(`${API_URL}/inspections`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      if (!inspectionResponse.ok) throw await apiError(inspectionResponse, "inspection");
      const created: Inspection = await inspectionResponse.json();
      const form = new FormData(); form.append("image", file);
      const uploadResponse = await fetch(`${API_URL}/inspections/${created.id}/image`, { method: "POST", body: form });
      if (!uploadResponse.ok) throw await apiError(uploadResponse, "upload");
      setInspection(created); setImage(await uploadResponse.json());
      setMessage({ kind: "success", key: "imageUploaded" });
    } catch (error) {
      setInspection(null); setImage(null); setMessage({ kind: "error", key: "uploadFailed", detail: (error as ApiError).detail });
    } finally { setBusy(false); }
  }

  async function runOcr() {
    if (!inspection || !image) return;
    setBusy(true); setMessage(null);
    try {
      const response = await fetch(`${API_URL}/inspections/${inspection.id}/images/${image.id}/ocr`, { method: "POST" });
      if (!response.ok) throw await apiError(response, "ocr");
      setOcr(await response.json()); setMessage({ kind: "success", key: "ocrComplete" });
    } catch (error) { setMessage({ kind: "error", key: "ocrFailed", detail: (error as ApiError).detail }); }
    finally { setBusy(false); }
  }

  async function extractInformation() {
    if (!inspection || !ocr) return;
    setBusy(true); setMessage(null);
    try {
      const response = await fetch(`${API_URL}/inspections/${inspection.id}/extract`, { method: "POST" });
      if (!response.ok) throw await apiError(response, "extract");
      setExtraction(await response.json());
    } catch (error) { setMessage({ kind: "error", key: "extractionFailed", detail: (error as ApiError).detail }); }
    finally { setBusy(false); }
  }

  async function runCompliance() {
    if (!inspection || !extraction) return;
    setBusy(true); setMessage(null);
    try {
      const response = await fetch(`${API_URL}/inspections/${inspection.id}/compliance`, { method: "POST" });
      if (!response.ok) throw await apiError(response, "compliance");
      setCompliance(await response.json());
    } catch (error) { setMessage({ kind: "error", key: "extractionFailed", detail: (error as ApiError).detail }); }
    finally { setBusy(false); }
  }

  const metadataCards = ["productInformation", "ingredients", "nutrition", "allergens", "manufacturer", "netQuantity", "mrp", "bestBefore", "countryOfOrigin", "compliance", "warnings"] as const;
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#dashboard"><span className="brand-mark" aria-hidden="true">LG</span><span>{t("appName")}</span></a><nav aria-label={t("primaryNavigation")}><a href="#dashboard">{t("dashboard")}</a><a href="#upload">{t("uploadLabel")}</a><a href="#results">{t("results")}</a></nav><LanguageSelector /></header>
    <main id="dashboard">
      <section className="hero"><div><p className="eyebrow">{t("supportedLanguages")}</p><h1>{t("tagline")}</h1><p>{t("legalNotice")}</p></div><div className="status-card"><span className="status-dot" />{image ? t("inspectionReady") : t("newInspection")}{inspection && <small>{t("inspectionId")}: {inspection.inspection_number}</small>}</div></section>
      {message && <div role="status" className={`message ${message.kind}`}>{message.kind === "error" ? t("error") : t("success")}: {t(message.key)}{message.detail && ` (${message.detail})`}</div>}
      <section id="upload" className="workspace-grid"><article className="card upload-card"><div className="card-heading"><div><p className="eyebrow">01</p><h2>{t("uploadImage")}</h2></div></div><p>{t("imageHelp")}</p><label className="upload-control"><input type="file" accept="image/png,image/jpeg" onChange={selectImage} disabled={busy} /><span>{busy ? t("loading") : t("selectImage")}</span></label>{image && <button className="primary-button" onClick={runOcr} disabled={busy}>{busy ? t("scanning") : t("scanLabel")}</button>}</article>
      <article className="card preview-card"><h2>{t("imagePreview")}</h2>{previewUrl ? <img src={previewUrl} alt={t("imagePreview")} /> : <p className="empty-state">{t("noImage")}</p>}</article></section>
      <section id="results" className="card results-card"><div className="card-heading"><div><p className="eyebrow">02</p><h2>{t("ocrResults")}</h2></div>{ocr && <span className="language-pill">{t("processingLanguages")}: {ocr.languages.join(", ")}</span>}</div>{ocr ? <><pre className="raw-text">{ocr.raw_text}</pre><div className="detection-list">{ocr.results.map((item, index) => <div className="detection" key={`${item.text}-${index}`}><strong>{item.text}</strong><span>{t("confidence")}: {item.confidence === null ? "—" : `${Math.round(item.confidence * 100)}%`}</span><span>{t("boundingBox")}: {item.bbox ? item.bbox.map((point) => point.join(",")).join(" · ") : "—"}</span></div>)}</div></> : <p className="empty-state">{t("noResults")}</p>}</section>
      {ocr && !extraction && <button className="primary-button" onClick={extractInformation} disabled={busy}>{busy ? t("extractingInformation") : t("extractInformation")}</button>}
      {extraction && <section className="card results-card" aria-label={t("extractionResults")}><h2>{t("extractionResults")}</h2><div className="detection-list">{Object.entries(extraction.fields).map(([name, field]) => <div className="detection" key={name}><strong>{t(extractionFieldLabels[name as keyof typeof extractionFieldLabels])}</strong><span>{field.value ?? t("notDetected")}</span><span>{t("extractionConfidence")}: {Math.round(field.confidence * 100)}% {field.needs_review ? `(${t("needsReview")})` : ""}</span></div>)}</div></section>}
      {extraction && !compliance && <button className="primary-button" onClick={runCompliance} disabled={busy}>{t("compliance")}</button>}
      {compliance && <section className="card results-card" aria-label={t("compliance")}><div className="card-heading"><h2>{t("compliance")}: {compliance.overall_status}</h2><span className="language-pill">{t("success")}: {compliance.summary.passed} · {t("error")}: {compliance.summary.failed} · {t("needsReview")}: {compliance.summary.review}</span></div><div className="detection-list">{compliance.findings.map((finding) => <div className="detection" key={finding.rule_id}><strong>{finding.rule_name} — {finding.status} ({finding.severity})</strong><span>{finding.message}</span><span>{finding.field}: {finding.value ?? t("notDetected")}</span>{finding.confidence !== null && <span>{t("confidence")}: {Math.round(finding.confidence * 100)}%</span>}{finding.evidence && <span>{finding.evidence}</span>}</div>)}</div></section>}
      <section className="metadata-grid" aria-label={t("productInformation")}>{metadataCards.map((key) => <article className="metadata-card" key={key}><h3>{t(key)}</h3><p>{t("notAvailable")}</p></article>)}</section>
    </main>
  </div>;
}
