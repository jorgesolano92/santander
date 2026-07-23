import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { DashboardSucursal } from './components/DashboardSucursal';
import { SucursalForm } from './components/SucursalForm';
import { SucursalList } from './components/SucursalList';
import { AdminLayout } from './layout/AdminLayout';
import { AlertsDesignPage } from './pages/AlertsDesignPage';
import { AuditPage } from './pages/AuditPage';
import { LoginPage } from './pages/LoginPage';
import { MessagingDesignPage } from './pages/MessagingDesignPage';
import { TechniciansPage } from './pages/TechniciansPage';
import { OverviewPage } from './pages/OverviewPage';
import { ReportingDesignPage } from './pages/ReportingDesignPage';
import { RolesDesignPage } from './pages/RolesDesignPage';
import { UpdatesDesignPage } from './pages/UpdatesDesignPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<AdminLayout />}>
          <Route index element={<Navigate to="/overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="sucursales" element={<SucursalList />} />
          <Route path="sucursales/nueva" element={<SucursalForm />} />
          <Route path="sucursales/editar/:id" element={<SucursalForm />} />
          <Route path="control/:id" element={<DashboardSucursal />} />
          <Route path="updates" element={<UpdatesDesignPage />} />
          <Route path="mensajeria" element={<MessagingDesignPage />} />
          <Route path="tecnicos" element={<TechniciansPage />} />
          <Route path="reporting" element={<ReportingDesignPage />} />
          <Route path="roles" element={<RolesDesignPage />} />
          <Route path="alertas" element={<AlertsDesignPage />} />
          <Route path="auditoria" element={<AuditPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
