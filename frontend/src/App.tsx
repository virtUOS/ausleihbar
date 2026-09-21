// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Universität Osnabrück (virtUOS)

import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { TranslationFormProvider } from "@basicbar/ui";
import { api } from "./api";
import { useAuth, rememberRedirect } from "./auth";
import { Loading } from "./components/Status";
import { LandingPage } from "./pages/LandingPage";
import { PageView } from "./pages/PageView";
import { StartPage } from "./pages/StartPage";
import { SectionPage } from "./pages/SectionPage";
import { PoolPage } from "./pages/PoolPage";
import { ProductPage } from "./pages/ProductPage";
import { SetPage } from "./pages/SetPage";
import { SearchPage } from "./pages/SearchPage";
import { BookingsPage } from "./pages/BookingsPage";
import { BookingDetailPage } from "./pages/BookingDetailPage";
import { CartPage } from "./pages/CartPage";
import { FavoritesPage } from "./pages/FavoritesPage";
import { ManageLanding } from "./pages/ManageLanding";
import { ManagePage } from "./pages/ManagePage";
import { ManageListPage } from "./pages/ManageListPage";
import { PendingConfirmationsPage } from "./pages/PendingConfirmationsPage";
import { BorrowerProfilePage } from "./pages/BorrowerProfilePage";
import { WalkInLendingPage } from "./pages/WalkInLendingPage";
import { QrHandoutPage } from "./pages/QrHandoutPage";
import { ResourceRedirectPage } from "./pages/ResourceRedirectPage";
import { StatsPage } from "./pages/StatsPage";
import { BorrowersPage } from "./pages/BorrowersPage";
import { AdminPage } from "./pages/AdminPage";
import { AdminPoolsPage } from "./pages/AdminPoolsPage";
import { AdminProductTypesPage } from "./pages/AdminProductTypesPage";
import { AdminProductsPage } from "./pages/AdminProductsPage";
import { AdminCategoriesPage } from "./pages/AdminCategoriesPage";
import { AdminSectionsPage } from "./pages/AdminSectionsPage";
import { AdminSetsPage } from "./pages/AdminSetsPage";
import { AdminInventoryPage } from "./pages/AdminInventoryPage";
import { AdminQrLabelsPage } from "./pages/AdminQrLabelsPage";
import { AdminInventoryDetailPage } from "./pages/AdminInventoryDetailPage";
import { AdminUsersPage } from "./pages/AdminUsersPage";
import { AdminAccessGroupsPage } from "./pages/AdminAccessGroupsPage";
import { AdminStrikeRulesPage } from "./pages/AdminStrikeRulesPage";
import { AdminRetentionPage } from "./pages/AdminRetentionPage";
import { AdminDefectsPage } from "./pages/AdminDefectsPage";
import { ManageDefectTicketsPage } from "./pages/ManageDefectTicketsPage";
import { AdminCartSettingsPage } from "./pages/AdminCartSettingsPage";
import { AdminNotificationsPage } from "./pages/AdminNotificationsPage";
import { AdminFunctionsPage } from "./pages/AdminFunctionsPage";
import { AdminWelcomePage } from "./pages/AdminWelcomePage";
import { AdminShopHomePage } from "./pages/AdminShopHomePage";
import { AdminPagesPage } from "./pages/AdminPagesPage";
import { AdminDataPage } from "./pages/AdminDataPage";
import { AdminTrashPage } from "./pages/AdminTrashPage";

/** "/" shows the public welcome page to guests and the shop to signed-in users. */
function HomeRoute() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return user?.authenticated ? <StartPage /> : <LandingPage />;
}

/** Gate for every internal route. The whole catalog/desk/admin area is for
 *  authenticated users only (borrower = any signed-in user); "/" is the sole
 *  public page. Without this, re-entering an internal URL after the one-shot
 *  silent-SSO bounce rendered the page to a guest (issue #10) — route-level
 *  authorization (lender / staff) stays on the individual pages. */
function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user?.authenticated) {
    // Remember where they were headed so sign-in returns them here (issue #18).
    rememberRedirect(location.pathname + location.search);
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

function App() {
  const { t } = useTranslation();
  return (
    <TranslationFormProvider
      translate={(text, source, target, format) =>
        api.translate(text, source, target, format).then((r) => r.translated)
      }
    >
    <div className="flex min-h-screen flex-col bg-white text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <a href="#main" className="skip-link">
        {t("Skip to content")}
      </a>
      <Header />
      <main id="main" className="mx-auto w-full max-w-3xl flex-1 px-4 py-5">
        <Routes>
          <Route path="/" element={<HomeRoute />} />
          <Route path="/pages/:slug" element={<PageView />} />
          <Route element={<RequireAuth />}>
            <Route path="/sections/:id" element={<SectionPage />} />
            <Route path="/pools/:id" element={<PoolPage />} />
            <Route path="/products/:id" element={<ProductPage />} />
            <Route path="/sets/:id" element={<SetPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/bookings" element={<BookingsPage />} />
            <Route path="/bookings/:code" element={<BookingDetailPage />} />
            <Route path="/cart" element={<CartPage />} />
            <Route path="/favorites" element={<FavoritesPage />} />
            <Route path="/functions" element={<AdminFunctionsPage />} />
            <Route path="/manage" element={<ManageLanding />} />
            <Route path="/manage/day" element={<ManagePage />} />
            <Route path="/manage/confirm" element={<PendingConfirmationsPage />} />
            <Route path="/manage/list" element={<ManageListPage />} />
            <Route path="/manage/users/:id" element={<BorrowerProfilePage />} />
            <Route path="/manage/walk-in" element={<WalkInLendingPage />} />
            <Route path="/qr" element={<QrHandoutPage />} />
            <Route path="/r/:qrId" element={<ResourceRedirectPage />} />
            <Route path="/manage/stats" element={<StatsPage />} />
            <Route path="/manage/borrowers" element={<BorrowersPage />} />
            {/* Operational features moved from Admin into the lending desk. */}
            <Route path="/manage/products" element={<AdminProductsPage />} />
            <Route path="/manage/sets" element={<AdminSetsPage />} />
            <Route path="/manage/inventory" element={<AdminInventoryPage />} />
            <Route path="/manage/inventory/:id" element={<AdminInventoryDetailPage />} />
            <Route path="/manage/qr-labels" element={<AdminQrLabelsPage />} />
            <Route path="/manage/defects" element={<AdminDefectsPage />} />
            <Route path="/manage/defect-tickets" element={<ManageDefectTicketsPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/admin/pools" element={<AdminPoolsPage />} />
            <Route path="/admin/product-types" element={<AdminProductTypesPage />} />
            <Route path="/admin/categories" element={<AdminCategoriesPage />} />
            <Route path="/admin/sections" element={<AdminSectionsPage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/admin/access-groups" element={<AdminAccessGroupsPage />} />
            <Route path="/admin/strike-rules" element={<AdminStrikeRulesPage />} />
            <Route path="/admin/retention" element={<AdminRetentionPage />} />
            <Route path="/admin/cart" element={<AdminCartSettingsPage />} />
            <Route path="/admin/notifications" element={<AdminNotificationsPage />} />
            <Route path="/admin/pages" element={<AdminPagesPage />} />
            <Route path="/admin/data" element={<AdminDataPage />} />
            <Route path="/admin/trash" element={<AdminTrashPage />} />
            <Route path="/admin/pages/welcome" element={<AdminWelcomePage />} />
            <Route path="/admin/pages/shop" element={<AdminShopHomePage />} />
          </Route>
        </Routes>
      </main>
      <Footer />
    </div>
    </TranslationFormProvider>
  );
}

export default App;
