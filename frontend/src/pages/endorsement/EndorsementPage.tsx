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
import { getApiErrorMessage } from '../../api/client';
import { endorsementApi } from '../../api/endorsement';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';
import type { EndorsementType } from '../../types';

export function EndorsementPage() {
  const queryClient = useQueryClient();
  const { user, accessToken } = useAuthStore();
  const [endorsementType, setEndorsementType] = useState<EndorsementType>('usd_enable');
  const [amount, setAmount] = useState('5000');
  const [passportNumber, setPassportNumber] = useState('');
  const [notes, setNotes] = useState('');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: account, isError: noAccount } = useQuery({
    queryKey: ['my-account', user?.id],
    queryFn: bankingApi.getMyAccount,
    enabled: Boolean(user?.id && accessToken),
    retry: false,
  });

  const { data: endorsementsData, isLoading } = useQuery({
    queryKey: ['my-endorsements', user?.id],
    queryFn: () => endorsementApi.getEndorsements({ mine: 'true' }),
    enabled: Boolean(user?.id && accessToken),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      endorsementApi.createEndorsement({
        endorsement_type: endorsementType,
        amount: amount || undefined,
        passport_number: passportNumber,
        notes,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-endorsements'] });
      setFeedback({ type: 'success', text: 'USD endorsement request submitted for review.' });
      setPassportNumber('');
      setNotes('');
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
      <Typography variant="h4">USD Currency Endorsement</Typography>

      {noAccount && (
        <Alert severity="info">No personal bank account is linked to your user profile.</Alert>
      )}
      {account && !account.is_active && (
        <Alert severity="error">
          This bank account is currently frozen. USD endorsement requests are disabled.
        </Alert>
      )}

      {account && (
        <Alert severity={account.is_usd_endorsed ? 'success' : 'info'}>
          {account.is_usd_endorsed
            ? `USD usage is ENABLED on account ${account.account_number} with an approved limit of USD ${Number(
                account.usd_endorsement_limit
              ).toLocaleString()}.`
            : `USD usage is not yet endorsed on account ${account.account_number}. Submit an endorsement request below to enable international USD spending.`}
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
              Request USD Endorsement
            </Typography>
            <Box component="form" onSubmit={handleSubmit}>
              <Stack spacing={2}>
                <TextField
                  select
                  label="Endorsement Type"
                  value={endorsementType}
                  onChange={(e) => setEndorsementType(e.target.value as EndorsementType)}
                  fullWidth
                >
                  <MenuItem value="usd_enable">USD Usage Enablement</MenuItem>
                  <MenuItem value="usd_limit">USD Limit Increase</MenuItem>
                  <MenuItem value="travel_quota">USD Travel Quota</MenuItem>
                </TextField>

                <TextField
                  label="Requested Limit (USD)"
                  type="number"
                  slotProps={{ htmlInput: { step: '0.01', min: '1' } }}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  fullWidth
                />

                <TextField
                  label="Passport Number (optional)"
                  value={passportNumber}
                  onChange={(e) => setPassportNumber(e.target.value)}
                  fullWidth
                />

                <TextField
                  label="Purpose / Notes"
                  multiline
                  rows={2}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  fullWidth
                />

                <Button
                  type="submit"
                  variant="contained"
                  disabled={createMutation.isPending || !account || !account.is_active}
                >
                  {createMutation.isPending ? 'Submitting...' : 'Submit Endorsement Request'}
                </Button>
              </Stack>
            </Box>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Endorsement History
            </Typography>
            {isLoading ? (
              <CircularProgress size={24} />
            ) : (
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>ID</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell align="right">USD Limit</TableCell>
                      <TableCell>Passport</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Review Remarks</TableCell>
                      <TableCell>Date</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(endorsementsData?.results ?? []).map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>#{item.id}</TableCell>
                        <TableCell>{item.endorsement_type.replace(/_/g, ' ').toUpperCase()}</TableCell>
                        <TableCell align="right">
                          {item.amount ? `$${Number(item.amount).toLocaleString()}` : '-'}
                        </TableCell>
                        <TableCell>{item.passport_number || '-'}</TableCell>
                        <TableCell>
                          <StatusChip value={item.status} />
                        </TableCell>
                        <TableCell>{item.review_remarks || '-'}</TableCell>
                        <TableCell>{new Date(item.created_at).toLocaleDateString()}</TableCell>
                      </TableRow>
                    ))}
                    {(endorsementsData?.results ?? []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                          No endorsement requests yet.
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

