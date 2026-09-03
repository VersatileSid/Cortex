import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main>
      <p className="eyebrow">LabelGuard</p>
      <h1>Package-label inspection assistance</h1>
      <p>
        Project foundation is ready. Inspection workflows will be added in upcoming milestones.
      </p>
      <p className="notice">
        This system supports inspectors and does not make legally binding enforcement decisions.
      </p>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
