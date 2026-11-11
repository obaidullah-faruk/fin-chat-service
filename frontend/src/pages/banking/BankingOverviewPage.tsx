import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { bankingApi } from '../../api/banking';
import { getApiErrorMessage } from '../../api/client';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';

export function BankingOverviewPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user, accessToken } = useAuthStore();
  const [accountType, setAccountType] = useState<'savings' | 'current' | 'salary'>('savings');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: account, isLoading, error } = useQuery({
    queryKey: ['my-account', user?.id],
    queryFn: bankingApi.getMyAccount,
    enabled: Boolean(user?.id && accessToken),
    retry: false,
  });

  useEffect(() => {
    if (account) {
      setAccountType(account.account_type);
    }
  }, [account]);

  const updateTypeMutation = useMutation({
    mutationFn: (type: 'savings' | 'current' | 'salary') => bankingApi.updateAccountType(type),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['my-account'] });
      setMessage({ type: 'success', text: 'Account type updated successfully.' });
    },
    onError: (err) => {
      setMessage({ type: 'error', text: getApiErrorMessage(err) });
    },
  });

  if (isLoading) return <CircularProgress />;
  if (error || !account) {
    return (
      <Alert severity="info">
        No bank account is linked to your user profile.
      </Alert>
    );
  }

  return (
    <Stack spacing={3}>
      <Typography variant="h4">Bank Account Overview</Typography>

      {!account.is_active && (
        <Alert severity="error">
          This bank account is currently frozen. Contact a branch manager to restore account activity.
        </Alert>
      )}

      {message && (
        <Alert severity={message.type} onClose={() => setMessage(null)}>
          {message.text}
        </Alert>
      )}

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '2fr 1fr' },
          gap: 3,
        }}
      >
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="h6">Account Details</Typography>
                <StatusChip value={account.is_active ? 'active' : 'frozen'} />
              </Stack>

              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' },
                  gap: 2,
                }}
              >
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Account Number
                  </Typography>
                  <Typography variant="h6" sx={{ fontFamily: 'monospace' }}>
                    {account.account_number}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Current Balance
                  </Typography>
                  <Typography variant="h5" color="primary" sx={{ fontWeight: 700 }}>
                    {account.currency}{' '}
                    {Number(account.balance).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                    })}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    Account Holder
                  </Typography>
                  <Typography variant="body1" sx={{ fontWeight: 500 }}>
                    {account.owner_name} ({account.username})
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    USD Endorsement
                  </Typography>
                  <Typography variant="body1" sx={{ fontWeight: 500 }}>
                    {account.is_usd_endorsed
                      ? `Enabled (Limit: USD ${Number(account.usd_endorsement_limit).toLocaleString()})`
                      : 'Not Enabled'}
                  </Typography>
                </Box>
              </Box>

              <Stack direction="row" spacing={1.5} sx={{ pt: 1 }}>
                <Button
                  variant="contained"
                  disabled={!account.is_active}
                  onClick={() => navigate('/banking/deposit')}
                >
                  Deposit
                </Button>
                <Button
                  variant="outlined"
                  disabled={!account.is_active}
                  onClick={() => navigate('/banking/withdraw')}
                >
                  Withdraw
                </Button>
                <Button
                  variant="outlined"
                  disabled={!account.is_active}
                  onClick={() => navigate('/banking/transfer')}
                >
                  Transfer
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Change Account Type
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Switch your single account type between Savings, Current, or Salary.
            </Typography>
            <Stack spacing={2}>
              <TextField
                select
                label="Account Type"
                value={accountType}
                onChange={(e) =>
                  setAccountType(e.target.value as 'savings' | 'current' | 'salary')
                }
                fullWidth
              >
                <MenuItem value="savings">Savings</MenuItem>
                <MenuItem value="current">Current</MenuItem>
                <MenuItem value="salary">Salary</MenuItem>
              </TextField>
              <Button
                variant="contained"
                disabled={
                  !account.is_active ||
                  updateTypeMutation.isPending ||
                  accountType === account.account_type
                }
                onClick={() => updateTypeMutation.mutate(accountType)}
              >
                {updateTypeMutation.isPending ? 'Saving...' : 'Update Account Type'}
              </Button>
            </Stack>
          </CardContent>
        </Card>
      </Box>
    </Stack>
  );
}

