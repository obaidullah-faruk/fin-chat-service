import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bankingApi } from '../../api/banking';
import { getApiErrorMessage } from '../../api/client';
import { useAuthStore } from '../../store/authStore';

export function TransferPage() {
  const queryClient = useQueryClient();
  const { user, accessToken } = useAuthStore();
  const [toAccountNumber, setToAccountNumber] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: account, isError: noAccount } = useQuery({
    queryKey: ['my-account', user?.id],
    queryFn: bankingApi.getMyAccount,
    enabled: Boolean(user?.id && accessToken),
    retry: false,
  });

  const { data: lookupAccounts = [] } = useQuery({
    queryKey: ['account-lookup', user?.id],
    queryFn: () => bankingApi.lookupAccounts(''),
    enabled: Boolean(user?.id && accessToken && account),
  });

  const transferMutation = useMutation({
    mutationFn: () =>
      bankingApi.transfer({
        to_account_number: toAccountNumber,
        amount,
        description,
      }),
    onSuccess: (txn) => {
      queryClient.invalidateQueries({ queryKey: ['my-account'] });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['recent-transactions'] });
      setFeedback({
        type: 'success',
        text: `Transferred $${Number(txn.amount).toFixed(2)} to ${
          txn.related_account_number
        }. New balance: $${Number(txn.balance_after).toFixed(2)} (Ref: ${txn.reference})`,
      });
      setAmount('');
      setDescription('');
    },
    onError: (err) => {
      setFeedback({ type: 'error', text: getApiErrorMessage(err) });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    transferMutation.mutate();
  };

  return (
    <Stack spacing={3} sx={{ maxWidth: 600 }}>
      <Typography variant="h4">Transfer Funds</Typography>
      {noAccount && (
        <Alert severity="info">No personal bank account is linked to your user profile.</Alert>
      )}
      {account && !account.is_active && (
        <Alert severity="error">
          This bank account is currently frozen. Transfers are disabled.
        </Alert>
      )}
      {account && (
        <Typography variant="body2" color="text.secondary">
          From: {account.account_number} &middot; Available Balance: $
          {Number(account.balance).toLocaleString(undefined, { minimumFractionDigits: 2 })}
        </Typography>
      )}
      {feedback && (
        <Alert severity={feedback.type} onClose={() => setFeedback(null)}>
          {feedback.text}
        </Alert>
      )}
      <Card>
        <CardContent>
          <Box component="form" onSubmit={handleSubmit}>
            <Stack spacing={2.5}>
              <TextField
                label="Recipient Account Number"
                placeholder="e.g. FC1000000002"
                value={toAccountNumber}
                onChange={(e) => setToAccountNumber(e.target.value)}
                required
                fullWidth
              />
              {lookupAccounts.length > 0 && (
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
                    Quick Select Recipient:
                  </Typography>
                  <Stack direction="row" sx={{ flexWrap: 'wrap', gap: 1 }}>
                    {lookupAccounts.map((acc) => (
                      <Chip
                        key={acc.account_number}
                        label={`${acc.username} (${acc.account_number})`}
                        size="small"
                        variant={toAccountNumber === acc.account_number ? 'filled' : 'outlined'}
                        color={toAccountNumber === acc.account_number ? 'primary' : 'default'}
                        onClick={() => setToAccountNumber(acc.account_number)}
                        clickable
                      />
                    ))}
                  </Stack>
                </Box>
              )}
              <TextField
                label="Amount (USD)"
                type="number"
                slotProps={{ htmlInput: { step: '0.01', min: '0.01' } }}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                required
                fullWidth
              />
              <TextField
                label="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                fullWidth
              />
              <Button
                type="submit"
                variant="contained"
                size="large"
                disabled={transferMutation.isPending || !account || !account.is_active}
              >
                {transferMutation.isPending ? 'Sending...' : 'Send Transfer'}
              </Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>
    </Stack>
  );
}

