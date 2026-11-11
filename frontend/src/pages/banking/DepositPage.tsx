import { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { bankingApi } from '../../api/banking';
import { getApiErrorMessage } from '../../api/client';
import { useAuthStore } from '../../store/authStore';
import type { FundingSource } from '../../types';

export function DepositPage() {
  const queryClient = useQueryClient();
  const { user, accessToken } = useAuthStore();
  const [amount, setAmount] = useState('');
  const [fundingSource, setFundingSource] = useState<FundingSource>('bank_transfer');
  const [description, setDescription] = useState('');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: account, isError: noAccount } = useQuery({
    queryKey: ['my-account', user?.id],
    queryFn: bankingApi.getMyAccount,
    enabled: Boolean(user?.id && accessToken),
    retry: false,
  });

  const depositMutation = useMutation({
    mutationFn: () =>
      bankingApi.deposit({ amount, funding_source: fundingSource, description }),
    onSuccess: (txn) => {
      queryClient.invalidateQueries({ queryKey: ['my-account'] });
      queryClient.invalidateQueries({ queryKey: ['transactions'] });
      queryClient.invalidateQueries({ queryKey: ['recent-transactions'] });
      queryClient.invalidateQueries({ queryKey: ['staff-dashboard'] });
      setFeedback({
        type: 'success',
        text: `Deposited $${Number(txn.amount).toFixed(2)} via ${txn.channel
          .replace(/_/g, ' ')
          .toUpperCase()}. New balance: $${Number(txn.balance_after).toFixed(2)} (Ref: ${
          txn.reference
        })`,
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
    depositMutation.mutate();
  };

  return (
    <Stack spacing={3} sx={{ maxWidth: 560 }}>
      <Typography variant="h4">Deposit Funds</Typography>
      {noAccount && (
        <Alert severity="info">No personal bank account is linked to your user profile.</Alert>
      )}
      {account && !account.is_active && (
        <Alert severity="error">
          This bank account is currently frozen. Self-service deposits are disabled.
        </Alert>
      )}
      {account && (
        <Typography variant="body2" color="text.secondary">
          Account: {account.account_number} &middot; Current Balance: $
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
                select
                label="Funding Source"
                value={fundingSource}
                onChange={(e) => setFundingSource(e.target.value as FundingSource)}
                fullWidth
              >
                <MenuItem value="bank_transfer">External Bank Transfer (ACH)</MenuItem>
                <MenuItem value="debit_card">Linked Debit Card Top-Up</MenuItem>
                <MenuItem value="atm_cash">ATM Cash Deposit</MenuItem>
                <MenuItem value="mobile_wallet">Mobile Check / Digital Wallet</MenuItem>
              </TextField>
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
                placeholder="e.g. Monthly savings transfer"
                fullWidth
              />
              <Button
                type="submit"
                variant="contained"
                size="large"
                disabled={depositMutation.isPending || !account || !account.is_active}
              >
                {depositMutation.isPending ? 'Processing...' : 'Deposit Money'}
              </Button>
            </Stack>
          </Box>
        </CardContent>
      </Card>
    </Stack>
  );
}
