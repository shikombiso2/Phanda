import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import "./index.css";
import App from "./App.tsx";

// autoUpdate (configured in vite.config.ts) means a new service worker
// activates itself on the next load rather than waiting for every open tab
// to close -- right for a job-matching app where stale app-shell code is a
// bigger problem than a mid-session reload.
registerSW({ immediate: true });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
