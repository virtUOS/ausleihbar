// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

/** An on/off switch (`role="switch"`) for settings that apply immediately,
 *  e.g. a course link's "active" state. Pass `label` (visible) or
 *  `ariaLabel` (icon-only rows). */
export function Switch({
  checked,
  onChange,
  disabled,
  label,
  ariaLabel,
  id,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  label?: React.ReactNode;
  ariaLabel?: string;
  id?: string;
}) {
  const button = (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-150 disabled:opacity-40 ${
        checked ? "bg-brand-600" : "bg-slate-300 dark:bg-slate-600"
      }`}
    >
      <span
        aria-hidden
        className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform duration-150 motion-reduce:transition-none ${
          checked ? "translate-x-5" : "translate-x-0.5"
        }`}
      />
    </button>
  );
  if (!label) return button;
  return (
    <label className="inline-flex cursor-pointer items-center gap-3 text-sm text-slate-700 dark:text-slate-200">
      {button}
      <span>{label}</span>
    </label>
  );
}
