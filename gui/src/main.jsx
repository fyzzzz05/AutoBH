import { installInputModality } from './input-modality.js';
import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.jsx";
import "./styles.css";
import "./dashboard.css";
import "./appearance.css";
import "./sunshine-layout.css";
import "./boya-personalization.css";

installInputModality();

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
