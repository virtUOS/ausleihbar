# Third-party licenses

Ausleihbar is licensed under the Apache License 2.0 (see `LICENSE`).
It uses the following third-party components, each under its own license.
The notable non-permissive ones:

- **psycopg** — LGPL-3.0 (used as a library / dynamic import; replaceable).
- **mozilla-django-oidc** — MPL-2.0 (file-level copyleft on its own files).
- **html5-qrcode**, **typescript** — Apache-2.0.

All others are permissive (MIT, BSD, Apache-2.0, HPND/MIT-CMU, ISC, …).
This inventory is generated from the installed dependency trees (backend
pip environment and frontend `node_modules`), so it includes transitive
dependencies.

## Python (backend)

Installed distributions and their licenses:

| Package | Version | License |
|---|---|---|
| asgiref | 3.11.1 | BSD License |
| certifi | 2026.5.20 | Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.0.0 | see package |
| charset-normalizer | 3.4.7 | MIT |
| cryptography | 48.0.0 | see package |
| Django | 5.1.4 | BSD License |
| django-cors-headers | 4.6.0 | MIT License |
| djangorestframework | 3.15.2 | BSD License |
| holidays | 0.60 | MIT License |
| idna | 3.18 | see package |
| josepy | 2.2.0 | see package |
| mozilla-django-oidc | 4.0.1 | Mozilla Public License 2.0 (MPL 2.0) |
| pillow | 11.0.0 | CMU License (MIT-CMU) |
| pip | 25.0.1 | MIT License |
| psycopg | 3.2.3 | GNU Lesser General Public License v3 (LGPLv3) |
| psycopg-binary | 3.2.3 | GNU Lesser General Public License v3 (LGPLv3) |
| pycparser | 3.0 | see package |
| python-dateutil | 2.9.0.post0 | BSD License, Apache Software License |
| qrcode | 8.0 | BSD License, Other/Proprietary License |
| requests | 2.34.2 | Apache Software License |
| six | 1.17.0 | MIT License |
| sqlparse | 0.5.5 | BSD License |
| typing_extensions | 4.15.0 | see package |
| urllib3 | 2.7.0 | see package |

## JavaScript (frontend)

Installed packages and their licenses:

| Package | Version | License |
|---|---|---|
| @alloc/quick-lru | 5.2.0 | MIT |
| @babel/code-frame | 7.29.7 | MIT |
| @babel/compat-data | 7.29.7 | MIT |
| @babel/core | 7.29.7 | MIT |
| @babel/generator | 7.29.7 | MIT |
| @babel/helper-compilation-targets | 7.29.7 | MIT |
| @babel/helper-globals | 7.29.7 | MIT |
| @babel/helper-module-imports | 7.29.7 | MIT |
| @babel/helper-module-transforms | 7.29.7 | MIT |
| @babel/helper-plugin-utils | 7.29.7 | MIT |
| @babel/helper-string-parser | 7.29.7 | MIT |
| @babel/helper-validator-identifier | 7.29.7 | MIT |
| @babel/helper-validator-option | 7.29.7 | MIT |
| @babel/helpers | 7.29.7 | MIT |
| @babel/parser | 7.29.7 | MIT |
| @babel/plugin-transform-react-jsx-self | 7.29.7 | MIT |
| @babel/plugin-transform-react-jsx-source | 7.29.7 | MIT |
| @babel/template | 7.29.7 | MIT |
| @babel/traverse | 7.29.7 | MIT |
| @babel/types | 7.29.7 | MIT |
| @esbuild/linux-arm64 | 0.25.12 | MIT |
| @jridgewell/gen-mapping | 0.3.13 | MIT |
| @jridgewell/remapping | 2.3.5 | MIT |
| @jridgewell/resolve-uri | 3.1.2 | MIT |
| @jridgewell/sourcemap-codec | 1.5.5 | MIT |
| @jridgewell/trace-mapping | 0.3.31 | MIT |
| @nodelib/fs.scandir | 2.1.5 | MIT |
| @nodelib/fs.stat | 2.0.5 | MIT |
| @nodelib/fs.walk | 1.2.8 | MIT |
| @remix-run/router | 1.23.3 | MIT |
| @rolldown/pluginutils | 1.0.0-beta.27 | MIT |
| @rollup/rollup-linux-arm64-gnu | 4.61.0 | MIT |
| @types/babel__core | 7.20.5 | MIT |
| @types/babel__generator | 7.27.0 | MIT |
| @types/babel__template | 7.4.4 | MIT |
| @types/babel__traverse | 7.28.0 | MIT |
| @types/estree | 1.0.9 | MIT |
| @types/prop-types | 15.7.15 | MIT |
| @types/react | 18.3.29 | MIT |
| @types/react-dom | 18.3.7 | MIT |
| @vitejs/plugin-react | 4.7.0 | MIT |
| any-promise | 1.3.0 | MIT |
| anymatch | 3.1.3 | ISC |
| arg | 5.0.2 | MIT |
| autoprefixer | 10.5.0 | MIT |
| baseline-browser-mapping | 2.10.33 | Apache-2.0 |
| binary-extensions | 2.3.0 | MIT |
| braces | 3.0.3 | MIT |
| browserslist | 4.28.2 | MIT |
| camelcase-css | 2.0.1 | MIT |
| caniuse-lite | 1.0.30001793 | CC-BY-4.0 |
| chokidar | 3.6.0 | MIT |
| commander | 4.1.1 | MIT |
| convert-source-map | 2.0.0 | MIT |
| cssesc | 3.0.0 | MIT |
| csstype | 3.2.3 | MIT |
| debug | 4.4.3 | MIT |
| didyoumean | 1.2.2 | Apache-2.0 |
| dlv | 1.1.3 | MIT |
| electron-to-chromium | 1.5.364 | ISC |
| es-errors | 1.3.0 | MIT |
| esbuild | 0.25.12 | MIT |
| escalade | 3.2.0 | MIT |
| fast-glob | 3.3.3 | MIT |
| fastq | 1.20.1 | ISC |
| fill-range | 7.1.1 | MIT |
| fraction.js | 5.3.4 | MIT |
| function-bind | 1.1.2 | MIT |
| gensync | 1.0.0-beta.2 | MIT |
| glob-parent | 6.0.2 | ISC |
| hasown | 2.0.4 | MIT |
| html5-qrcode | 2.3.8 | Apache-2.0 |
| is-binary-path | 2.1.0 | MIT |
| is-core-module | 2.16.2 | MIT |
| is-extglob | 2.1.1 | MIT |
| is-glob | 4.0.3 | MIT |
| is-number | 7.0.0 | MIT |
| jiti | 1.21.7 | MIT |
| js-tokens | 4.0.0 | MIT |
| jsesc | 3.1.0 | MIT |
| json5 | 2.2.3 | MIT |
| lilconfig | 3.1.3 | MIT |
| lines-and-columns | 1.2.4 | MIT |
| loose-envify | 1.4.0 | MIT |
| lru-cache | 5.1.1 | ISC |
| merge2 | 1.4.1 | MIT |
| micromatch | 4.0.8 | MIT |
| ms | 2.1.3 | MIT |
| mz | 2.7.0 | MIT |
| nanoid | 3.3.12 | MIT |
| node-releases | 2.0.46 | MIT |
| normalize-path | 3.0.0 | MIT |
| normalize-wheel | 1.0.1 | BSD-3-Clause |
| object-assign | 4.1.1 | MIT |
| object-hash | 3.0.0 | MIT |
| path-parse | 1.0.7 | MIT |
| picocolors | 1.1.1 | ISC |
| picomatch | 2.3.2 | MIT |
| pify | 2.3.0 | MIT |
| pirates | 4.0.7 | MIT |
| postcss | 8.5.15 | MIT |
| postcss-import | 15.1.0 | MIT |
| postcss-js | 4.1.0 | MIT |
| postcss-load-config | 6.0.1 | MIT |
| postcss-nested | 6.2.0 | MIT |
| postcss-selector-parser | 6.1.2 | MIT |
| postcss-value-parser | 4.2.0 | MIT |
| queue-microtask | 1.2.3 | MIT |
| react | 18.3.1 | MIT |
| react-dom | 18.3.1 | MIT |
| react-easy-crop | 5.5.7 | MIT |
| react-refresh | 0.17.0 | MIT |
| react-router | 6.30.4 | MIT |
| react-router-dom | 6.30.4 | MIT |
| read-cache | 1.0.0 | MIT |
| readdirp | 3.6.0 | MIT |
| resolve | 1.22.12 | MIT |
| reusify | 1.1.0 | MIT |
| rollup | 4.61.0 | MIT |
| run-parallel | 1.2.0 | MIT |
| scheduler | 0.23.2 | MIT |
| semver | 6.3.1 | ISC |
| source-map-js | 1.2.1 | BSD-3-Clause |
| sucrase | 3.35.1 | MIT |
| supports-preserve-symlinks-flag | 1.0.0 | MIT |
| tailwindcss | 3.4.19 | MIT |
| thenify | 3.3.1 | MIT |
| thenify-all | 1.6.0 | MIT |
| tinyglobby | 0.2.17 | MIT |
| to-regex-range | 5.0.1 | MIT |
| ts-interface-checker | 0.1.13 | Apache-2.0 |
| tslib | 2.8.1 | 0BSD |
| typescript | 5.9.3 | Apache-2.0 |
| update-browserslist-db | 1.2.3 | MIT |
| util-deprecate | 1.0.2 | MIT |
| vite | 6.4.2 | MIT |
| yallist | 3.1.1 | ISC |
