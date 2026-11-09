import React from "react";
import ReactDOM from "react-dom/client";
// Fontes empacotadas localmente (licença SIL OFL 1.1) — funcionam offline.
import "@fontsource/press-start-2p/400.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/vt323/400.css";
import "./styles/index.css";
import App from "./app/App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
