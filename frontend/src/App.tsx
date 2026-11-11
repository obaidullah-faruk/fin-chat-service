import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ChequeApprovalPage } from './pages/admin/ChequeApprovalPage';
import { EndorsementApprovalPage } from './pages/admin/EndorsementApprovalPage';
import { UserManagementPage } from './pages/admin/UserManagementPage';
import { LoginPage } from './pages/auth/LoginPage';
import { BankingOverviewPage } from './pages/banking/BankingOverviewPage';
import { DepositPage } from './pages/banking/DepositPage';
import { TransactionsPage } from './pages/banking/TransactionsPage';
import { TransferPage } from './pages/banking/TransferPage';
import { WithdrawPage } from './pages/banking/WithdrawPage';
import { ChequeBookPage } from './pages/cheque/ChequeBookPage';
import { DashboardPage } from './pages/dashboard/DashboardPage';
import { EndorsementPage } from './pages/endorsement/EndorsementPage';
import { AddressPage } from './pages/profile/AddressPage';
import { ProfilePage } from './pages/profile/ProfilePage';
import { ActivityLogsPage } from './pages/staff/ActivityLogsPage';
import { CustomerDetailPage } from './pages/staff/CustomerDetailPage';
import { CustomersPage } from './pages/staff/CustomersPage';

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />

          <Route path="/banking" element={<BankingOverviewPage />} />
          <Route path="/banking/deposit" element={<DepositPage />} />
          <Route path="/banking/withdraw" element={<WithdrawPage />} />
          <Route path="/banking/transfer" element={<TransferPage />} />
          <Route path="/banking/transactions" element={<TransactionsPage />} />

          <Route path="/cheque" element={<ChequeBookPage />} />
          <Route path="/endorsement" element={<EndorsementPage />} />

          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/profile/address" element={<AddressPage />} />

          <Route element={<ProtectedRoute allowedRoles={['manager', 'admin', 'superadmin']} />}>
            <Route path="/staff/customers" element={<CustomersPage />} />
            <Route path="/staff/customers/:userId" element={<CustomerDetailPage />} />
            <Route path="/staff/transactions" element={<TransactionsPage scopeAll />} />
            <Route path="/staff/activities" element={<ActivityLogsPage />} />
            <Route path="/admin/cheque-requests" element={<ChequeApprovalPage />} />
            <Route path="/admin/endorsements" element={<EndorsementApprovalPage />} />
            <Route path="/admin/transactions" element={<TransactionsPage scopeAll />} />
          </Route>

          <Route element={<ProtectedRoute allowedRoles={['admin', 'superadmin']} />}>
            <Route path="/admin/users" element={<UserManagementPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default App;
