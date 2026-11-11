import { useState } from 'react';
import { AccountBalance as BankIcon } from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../../api/auth';
import { getApiErrorMessage } from '../../api/client';
import { queryClient } from '../../api/queryClient';
import { useAuthStore } from '../../store/authStore';

const DEMO_USERS = [
  { username: 'superadmin', role: 'superadmin' },
  { username: 'admin1', role: 'admin' },
  { username: 'manager1', role: 'manager' },
  { username: 'customer1', role: 'customer ($10,000)' },
  { username: 'customer2', role: 'customer ($5,000)' },
  { username: 'customer3', role: 'customer ($2,500)' },
];

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await queryClient.cancelQueries();
      logout();
      const data = await authApi.login(username, password);
      setAuth(data.access, data.refresh, data.user);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(getApiErrorMessage(err, 'Invalid credentials.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        p: 2,
      }}
    >
      <Card sx={{ maxWidth: 440, width: '100%' }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={1} sx={{ alignItems: 'center', mb: 3 }}>
            <BankIcon color="primary" sx={{ fontSize: 40 }} />
            <Typography variant="h5" color="primary" sx={{ fontWeight: 700 }}>
              FinChat Service
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Sign in to access your financial dashboard
            </Typography>
          </Stack>

          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit}>
            <Stack spacing={2}>
              <TextField
                label="Username or Email"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                fullWidth
                autoFocus
              />
              <TextField
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                fullWidth
              />
              <Button
                type="submit"
                variant="contained"
                size="large"
                disabled={loading}
                fullWidth
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </Button>
            </Stack>
          </Box>

          <Divider sx={{ my: 3 }}>
            <Typography variant="caption" color="text.secondary">
              Quick Fill (Local Dev: Test@1234)
            </Typography>
          </Divider>

          <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1, justifyContent: 'center' }}>
            {DEMO_USERS.map((u) => (
              <Chip
                key={u.username}
                label={`${u.username}`}
                title={u.role}
                size="small"
                variant="outlined"
                clickable
                onClick={() => {
                  setUsername(u.username);
                  setPassword('Test@1234');
                }}
              />
            ))}
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}

