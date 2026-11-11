import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bankingApi } from '../../api/banking';
import { chequeApi } from '../../api/cheque';
import { getApiErrorMessage } from '../../api/client';
import { usersApi } from '../../api/users';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';

export function ChequeBookPage() {
  const queryClient = useQueryClient();
  const { user, accessToken } = useAuthStore();
  const [leaves, setLeaves] = useState(25);
  const [addressId, setAddressId] = useState<string>('');
  const [remarks, setRemarks] = useState('');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: account, isError: noAccount } = useQuery({
    queryKey: ['my-account', user?.id],
    queryFn: bankingApi.getMyAccount,
    enabled: Boolean(user?.id && accessToken),
    retry: false,
  });

  const { data: addresses = [] } = useQuery({
    queryKey: ['addresses', user?.id],
    queryFn: usersApi.getAddresses,
    enabled: Boolean(user?.id && accessToken),
  });

  const { data: requestsData, isLoading } = useQuery({
    queryKey: ['my-cheque-requests', user?.id],
    queryFn: () => chequeApi.getRequests({ mine: 'true' }),
    enabled: Boolean(user?.id && accessToken),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      chequeApi.createRequest({
        leaves_requested: leaves,
        delivery_address: addressId ? Number(addressId) : null,
        remarks,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-cheque-requests'] });
      setFeedback({ type: 'success', text: 'Cheque book request submitted successfully.' });
      setRemarks('');
    },
    onError: (err) => {
      setFeedback({ type: 'error', text: getApiErrorMessage(err) });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    createMutation.mutate();
  };

  return (
    <Stack spacing={3}>
      <Typography variant="h4">Cheque Book Requests</Typography>

      {noAccount && (
        <Alert severity="info">No personal bank account is linked to your user profile.</Alert>
      )}
      {account && !account.is_active && (
        <Alert severity="error">
          This bank account is currently frozen. Cheque book requests are disabled.
        </Alert>
      )}

      {feedback && (
        <Alert severity={feedback.type} onClose={() => setFeedback(null)}>
          {feedback.text}
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: '1fr 2fr' },
          gap: 3,
          alignItems: 'start',
        }}
      >
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              New Request
            </Typography>
            <Box component="form" onSubmit={handleSubmit}>
              <Stack spacing={2}>
                <TextField
                  select
                  label="Number of Leaves"
                  value={leaves}
                  onChange={(e) => setLeaves(Number(e.target.value))}
                  fullWidth
                >
                  <MenuItem value={10}>10 Leaves</MenuItem>
                  <MenuItem value={25}>25 Leaves</MenuItem>
                  <MenuItem value={50}>50 Leaves</MenuItem>
                  <MenuItem value={100}>100 Leaves</MenuItem>
                </TextField>

                <TextField
                  select
                  label="Delivery Address"
                  value={addressId}
                  onChange={(e) => setAddressId(e.target.value)}
                  fullWidth
                  helperText="Defaults to your primary address if left unselected"
                >
                  <MenuItem value="">Primary Address (Default)</MenuItem>
                  {addresses.map((addr) => (
                    <MenuItem key={addr.id} value={String(addr.id)}>
                      {addr.label.toUpperCase()} — {addr.street}, {addr.city}
                    </MenuItem>
                  ))}
                </TextField>

                <TextField
                  label="Remarks (optional)"
                  multiline
                  rows={2}
                  value={remarks}
                  onChange={(e) => setRemarks(e.target.value)}
                  fullWidth
                />

                <Button
                  type="submit"
                  variant="contained"
                  disabled={createMutation.isPending || !account || !account.is_active}
                >
                  {createMutation.isPending ? 'Submitting...' : 'Request Cheque Book'}
                </Button>
              </Stack>
            </Box>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              My Requests
            </Typography>
            {isLoading ? (
              <CircularProgress size={24} />
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>ID</TableCell>
                      <TableCell>Leaves</TableCell>
                      <TableCell>Delivery Address</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Remarks</TableCell>
                      <TableCell>Requested</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(requestsData?.results ?? []).map((req) => (
                      <TableRow key={req.id}>
                        <TableCell>#{req.id}</TableCell>
                        <TableCell>{req.leaves_requested}</TableCell>
                        <TableCell>{req.delivery_address_snapshot || '-'}</TableCell>
                        <TableCell>
                          <StatusChip value={req.status} />
                        </TableCell>
                        <TableCell>{req.remarks || '-'}</TableCell>
                        <TableCell>{new Date(req.requested_at).toLocaleDateString()}</TableCell>
                      </TableRow>
                    ))}
                    {(requestsData?.results ?? []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={6} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                          No cheque book requests yet.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Box>
            )}
          </CardContent>
        </Card>
      </Box>
    </Stack>
  );
}

