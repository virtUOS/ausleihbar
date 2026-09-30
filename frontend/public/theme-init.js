// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

// Set the theme before first paint to avoid a flash of the wrong mode.
// Mirrors the logic in src/theme.tsx (Auto/Light/Dark; Auto = system) and
// basicbar's prePaintScript. Loaded as a classic synchronous script from
// index.html so it runs before first paint and satisfies a `script-src 'self'`
// CSP (#44).
(function () {
  try {
    var choice = localStorage.getItem("appearance");
    var dark =
      choice === "dark" ||
      ((!choice || choice === "auto") &&
        window.matchMedia("(prefers-color-scheme: dark)").matches);
    var root = document.documentElement;
    if (dark) root.classList.add("dark");
    root.style.colorScheme = dark ? "dark" : "light";
  } catch (e) {}
})();
