import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { DataDetailPage } from "./pages/DataDetailPage";
import { DataPage } from "./pages/DataPage";
import { FactorDetailPage } from "./pages/FactorDetailPage";
import { FactorsPage } from "./pages/FactorsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { RunsPage } from "./pages/RunsPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="data" element={<DataPage />} />
          <Route path="data/:name" element={<DataDetailPage />} />
          <Route path="runs" element={<RunsPage />} />
          <Route path="runs/:id" element={<RunDetailPage />} />
          <Route path="factors" element={<FactorsPage />} />
          <Route path="factors/:id" element={<FactorDetailPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
