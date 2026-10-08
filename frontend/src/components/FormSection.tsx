import type { ReactNode } from "react";

/** Headed card used to group related fields in admin forms. */
export function FormSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={id}
      className="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800"
    >
      <h4 id={id} className="text-xs font-semibold text-slate-600 dark:text-slate-300">
        {title}
      </h4>
      {children}
    </section>
  );
}
