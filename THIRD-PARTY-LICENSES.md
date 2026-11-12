# Third-party licenses

Ausleihbar is licensed under the Apache License 2.0 (see `LICENSE`).
It uses the following third-party components, each under its own license.
The notable non-permissive ones:

- **psycopg** — LGPL-3.0 (used as a library / dynamic import; replaceable).
- **mozilla-django-oidc**, **certifi** — MPL-2.0 (file-level copyleft on their own files).
- **lightningcss** — MPL-2.0 (build tool only; not shipped in the image's SPA).
- **@fontsource-variable/plus-jakarta-sans** — SIL OFL 1.1 (font).
- **caniuse-lite** — CC-BY-4.0 (build-time browser data).

All others are permissive (MIT, BSD, Apache-2.0, PSF, MIT-CMU, ISC, 0BSD, …).
This inventory is generated from the installed dependency trees (backend
pip environment and frontend `node_modules`, including dev and build
tools), so it includes transitive dependencies. Platform-specific build
binaries are listed for linux-x64, the platform of the release image.

## Python (backend)

Installed distributions and their licenses:

| Package | Version | License |
|---|---|---|
| asgiref | 3.13.0 | BSD-3-Clause |
| basicbar-auth | 0.2.2 | Apache-2.0 |
| basicbar-integrations | 0.4.0 | Apache-2.0 |
| certifi | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| Django | 6.1.3 | BSD-3-Clause |
| django-cors-headers | 4.9.0 | MIT |
| django-modeltranslation | 0.20.6 | BSD-3-Clause |
| djangorestframework | 3.18.3 | BSD-3-Clause |
| gunicorn | 27.0.0 | MIT |
| holidays | 0.108 | MIT |
| idna | 3.20 | BSD-3-Clause |
| Markdown | 3.11.3 | BSD-3-Clause |
| mozilla-django-oidc | 5.0.2 | MPL-2.0 |
| nh3 | 0.3.7 | MIT |
| pillow | 13.0.0 | MIT-CMU |
| psycopg | 3.3.9 | LGPL-3.0-only |
| psycopg-binary | 3.3.9 | LGPL-3.0-only |
| pycparser | 3.12 | BSD-3-Clause |
| PyJWT | 2.15.1 | MIT |
| pypdf | 7.0.1 | BSD-3-Clause |
| python-dateutil | 2.9.0.post0 | Apache Software License; BSD License |
| qrcode | 8.2 | BSD License; Other/Proprietary License |
| requests | 2.34.2 | Apache Software License |
| six | 1.17.0 | MIT License |
| sqlparse | 0.6.1 | BSD License |
| typing_extensions | 4.16.0 | PSF-2.0 |
| urllib3 | 2.8.0 | MIT |

## JavaScript (frontend)

Installed packages and their licenses:

| Package | Version | License |
|---|---|---|
| @alloc/quick-lru | 5.2.0 | MIT |
| @babel/runtime | 7.29.7 | MIT |
| @basicbar/ui | 0.9.1 | Apache-2.0 |
| @floating-ui/core | 1.8.0 | MIT |
| @floating-ui/dom | 1.8.0 | MIT |
| @floating-ui/utils | 0.2.12 | MIT |
| @fontsource-variable/plus-jakarta-sans | 5.3.0 | OFL-1.1 |
| @jridgewell/gen-mapping | 0.3.13 | MIT |
| @jridgewell/resolve-uri | 3.1.2 | MIT |
| @jridgewell/sourcemap-codec | 1.5.5 | MIT |
| @jridgewell/trace-mapping | 0.3.31 | MIT |
| @nodelib/fs.scandir | 2.1.5 | MIT |
| @nodelib/fs.stat | 2.0.5 | MIT |
| @nodelib/fs.walk | 1.2.8 | MIT |
| @oxc-project/types | 0.156.0 | MIT |
| @playwright/test | 1.65.0 | Apache-2.0 |
| @rolldown/binding-linux-x64-gnu | 1.2.18 | MIT |
| @rolldown/pluginutils | 1.1.0 | MIT |
| @tiptap/core | 3.31.3 | MIT |
| @tiptap/core | 3.33.1 | MIT |
| @tiptap/extension-blockquote | 3.31.3 | MIT |
| @tiptap/extension-bold | 3.31.3 | MIT |
| @tiptap/extension-bubble-menu | 3.33.1 | MIT |
| @tiptap/extension-bullet-list | 3.31.3 | MIT |
| @tiptap/extension-code | 3.31.3 | MIT |
| @tiptap/extension-code-block | 3.31.3 | MIT |
| @tiptap/extension-document | 3.31.3 | MIT |
| @tiptap/extension-dropcursor | 3.31.3 | MIT |
| @tiptap/extension-floating-menu | 3.33.1 | MIT |
| @tiptap/extension-gapcursor | 3.31.3 | MIT |
| @tiptap/extension-hard-break | 3.31.3 | MIT |
| @tiptap/extension-heading | 3.31.3 | MIT |
| @tiptap/extension-horizontal-rule | 3.31.3 | MIT |
| @tiptap/extension-image | 3.31.3 | MIT |
| @tiptap/extension-italic | 3.31.3 | MIT |
| @tiptap/extension-link | 3.31.3 | MIT |
| @tiptap/extension-list | 3.31.3 | MIT |
| @tiptap/extension-list-item | 3.31.3 | MIT |
| @tiptap/extension-list-keymap | 3.31.3 | MIT |
| @tiptap/extension-ordered-list | 3.31.3 | MIT |
| @tiptap/extension-paragraph | 3.31.3 | MIT |
| @tiptap/extension-strike | 3.31.3 | MIT |
| @tiptap/extension-text | 3.31.3 | MIT |
| @tiptap/extension-underline | 3.31.3 | MIT |
| @tiptap/extensions | 3.31.3 | MIT |
| @tiptap/pm | 3.31.3 | MIT |
| @tiptap/pm | 3.33.1 | MIT |
| @tiptap/react | 3.33.1 | MIT |
| @tiptap/starter-kit | 3.31.3 | MIT |
| @types/react | 19.3.0 | MIT |
| @types/react-dom | 19.3.0 | MIT |
| @types/use-sync-external-store | 0.0.6 | MIT |
| @typescript/typescript-linux-arm64 | 7.0.2 | Apache-2.0 |
| @vitejs/plugin-react | 6.3.0 | MIT |
| any-promise | 1.3.0 | MIT |
| anymatch | 3.1.3 | ISC |
| arg | 5.0.2 | MIT |
| autoprefixer | 10.6.2 | MIT |
| baseline-browser-mapping | 2.11.30 | Apache-2.0 |
| binary-extensions | 2.3.0 | MIT |
| braces | 3.0.3 | MIT |
| browserslist | 4.29.4 | MIT |
| camelcase-css | 2.0.1 | MIT |
| caniuse-lite | 1.0.30001817 | CC-BY-4.0 |
| chokidar | 3.6.0 | MIT |
| commander | 4.1.1 | MIT |
| cookie | 1.1.1 | MIT |
| cssesc | 3.0.0 | MIT |
| csstype | 3.2.3 | MIT |
| detect-libc | 2.1.2 | Apache-2.0 |
| didyoumean | 1.2.2 | Apache-2.0 |
| dlv | 1.1.3 | MIT |
| electron-to-chromium | 1.5.462 | ISC |
| es-errors | 1.3.0 | MIT |
| escalade | 3.2.0 | MIT |
| fast-equals | 5.4.5 | MIT |
| fast-glob | 3.3.3 | MIT |
| fastq | 1.20.1 | ISC |
| fdir | 6.5.0 | MIT |
| fill-range | 7.1.1 | MIT |
| fraction.js | 5.3.4 | MIT |
| function-bind | 1.1.2 | MIT |
| glob-parent | 5.1.2 | ISC |
| glob-parent | 6.0.2 | ISC |
| hasown | 2.0.4 | MIT |
| html-parse-stringify | 4.0.1 | MIT |
| html5-qrcode | 2.3.8 | Apache-2.0 |
| i18next | 27.1.1 | MIT |
| i18next-browser-languagedetector | 8.3.0 | MIT |
| is-binary-path | 2.1.0 | MIT |
| is-core-module | 2.16.2 | MIT |
| is-extglob | 2.1.1 | MIT |
| is-glob | 4.0.3 | MIT |
| is-number | 7.0.0 | MIT |
| jiti | 1.21.7 | MIT |
| lightningcss | 1.33.0 | MPL-2.0 |
| lightningcss-linux-x64-gnu | 1.33.0 | MPL-2.0 |
| lilconfig | 3.1.3 | MIT |
| lines-and-columns | 1.2.4 | MIT |
| linkifyjs | 4.3.3 | MIT |
| lucide-react | 1.72.0 | ISC |
| merge2 | 1.4.1 | MIT |
| micromatch | 4.0.8 | MIT |
| mz | 2.7.0 | MIT |
| nanoid | 3.3.20 | MIT |
| node-releases | 2.0.59 | MIT |
| normalize-path | 3.0.0 | MIT |
| normalize-wheel | 1.0.1 | BSD-3-Clause |
| object-assign | 4.1.1 | MIT |
| object-hash | 3.0.0 | MIT |
| orderedmap | 2.1.1 | MIT |
| path-parse | 1.0.7 | MIT |
| picocolors | 1.1.1 | ISC |
| picomatch | 2.3.2 | MIT |
| picomatch | 4.0.4 | MIT |
| picomatch | 4.0.7 | MIT |
| pify | 2.3.0 | MIT |
| pirates | 4.0.7 | MIT |
| playwright | 1.65.0 | Apache-2.0 |
| playwright-core | 1.65.0 | Apache-2.0 |
| postcss | 8.5.32 | MIT |
| postcss-import | 15.1.0 | MIT |
| postcss-js | 4.1.0 | MIT |
| postcss-load-config | 6.0.1 | MIT |
| postcss-nested | 6.2.0 | MIT |
| postcss-selector-parser | 6.1.5 | MIT |
| postcss-value-parser | 4.2.0 | MIT |
| prosemirror-changeset | 2.4.4 | MIT |
| prosemirror-commands | 1.7.2 | MIT |
| prosemirror-dropcursor | 1.8.4 | MIT |
| prosemirror-gapcursor | 1.4.1 | MIT |
| prosemirror-history | 1.5.1 | MIT |
| prosemirror-inputrules | 1.5.1 | MIT |
| prosemirror-keymap | 1.2.3 | MIT |
| prosemirror-model | 1.25.12 | MIT |
| prosemirror-schema-list | 1.5.1 | MIT |
| prosemirror-state | 1.4.4 | MIT |
| prosemirror-tables | 1.8.5 | MIT |
| prosemirror-transform | 1.12.2 | MIT |
| prosemirror-view | 1.42.6 | MIT |
| queue-microtask | 1.2.3 | MIT |
| react | 19.3.1 | MIT |
| react-dom | 19.3.1 | MIT |
| react-easy-crop | 6.2.5 | MIT |
| react-i18next | 18.0.1 | MIT |
| react-router | 7.18.5 | MIT |
| react-router-dom | 7.18.5 | MIT |
| read-cache | 1.0.0 | MIT |
| readdirp | 3.6.0 | MIT |
| resolve | 1.22.12 | MIT |
| reusify | 1.1.0 | MIT |
| rolldown | 1.2.18 | MIT |
| rope-sequence | 1.3.4 | MIT |
| run-parallel | 1.2.0 | MIT |
| scheduler | 0.28.0 | MIT |
| set-cookie-parser | 2.7.3 | MIT |
| source-map-js | 1.2.2 | BSD-3-Clause |
| sucrase | 3.35.1 | MIT |
| supports-preserve-symlinks-flag | 1.0.0 | MIT |
| tailwindcss | 3.4.19 | MIT |
| thenify | 3.3.1 | MIT |
| thenify-all | 1.6.0 | MIT |
| tinyglobby | 0.2.17 | MIT |
| to-regex-range | 5.0.1 | MIT |
| ts-interface-checker | 0.1.13 | Apache-2.0 |
| typescript | 7.0.2 | Apache-2.0 |
| update-browserslist-db | 1.3.4 | MIT |
| use-sync-external-store | 1.6.0 | MIT |
| util-deprecate | 1.0.2 | MIT |
| vite | 8.3.8 | MIT |
| w3c-keyname | 2.2.8 | MIT |
