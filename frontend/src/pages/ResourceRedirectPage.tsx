// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useFetch } from "../useFetch";
import { ErrorBox, Loading } from "../components/Status";

/**
 * Landing page for a device QR sticker (`/r/<qr_id>`). A normal QR reader opens
 * this; we resolve the unit to its product and forward to the product page so
 * the borrower finds details / manuals (concept §6.2).
 */
export function ResourceRedirectPage() {
  const { t } = useTranslation();
  const { qrId } = useParams();
  const navigate = useNavigate();
  const { data, loading, error } = useFetch(
    () => api.resolveResourceByQr(qrId!),
    [qrId],
  );

  useEffect(() => {
    if (data) navigate(`/products/${data.product}`, { replace: true });
  }, [data, navigate]);

  if (loading || data) return <Loading />;
  if (error)
    return (
      <div className="py-10 text-center">
        <ErrorBox message={t("This device QR code isn't recognised.")} />
        <Link to="/" className="text-sm text-slate-600 dark:text-slate-300 underline">
          {t("Go to lending")}
        </Link>
      </div>
    );
  return null;
}
