// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ThemeProvider } from "@basicbar/ui";
import { AuthProvider } from "./auth";
import { CartProvider } from "./cart";
import { StartDateProvider } from "./startDate";
import { ToastProvider } from "./components/Toast";
import { ConfirmProvider } from "./components/ConfirmDialog";
import { PromptProvider } from "./components/PromptDialog";
import "./i18n";
// Self-hosted font (no third-party CDN — GDPR).
import "@fontsource-variable/plus-jakarta-sans";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <ToastProvider>
            <ConfirmProvider>
              <PromptProvider>
                <CartProvider>
                  <StartDateProvider>
                    <App />
                  </StartDateProvider>
                </CartProvider>
              </PromptProvider>
            </ConfirmProvider>
          </ToastProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>
);
