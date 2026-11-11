import { Alert, Box, Container } from '@mui/material';
import { Navigate, Outlet } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import type { RoleName } from '../types';

interface ProtectedRouteProps {
  allowedRoles?: RoleName[];
  children?: React.ReactNode;
}

export function ProtectedRoute({ allowedRoles, children }: ProtectedRouteProps) {
  const { accessToken, user } = useAuthStore();

  if (!accessToken || !user) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <Container maxWidth="sm" sx={{ mt: 6 }}>
        <Box>
          <Alert severity="error">
            403 Forbidden — Your role ({user.role}) does not have access to this page.
          </Alert>
        </Box>
      </Container>
    );
  }

  return children ? <>{children}</> : <Outlet />;
}

