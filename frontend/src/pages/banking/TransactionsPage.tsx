import { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CircularProgress,
  Link,
  MenuItem,
  Pagination,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { bankingApi } from '../../api/banking';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';

interface TransactionsPageProps {
  scopeAll?: boolean;
}

export function TransactionsPage({ scopeAll = false }: TransactionsPageProps) {
  const navigate = useNavigate();
  const { user, accessToken } = useAuthStore();
  const [page, setPage] = useState(1);
  const [transactionType, setTransactionType] = useState('');
  const [channel, setChannel] = useState('');
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: [
      'transactions',
      scopeAll ? 'all' : 'mine',
      page,
      transactionType,
      channel,
      search,
      user?.id,
    ],
    queryFn: () =>
      bankingApi.getTransactions({
        page,
        transaction_type: transactionType || undefined,
        channel: channel || undefined,
        search: search || undefined,
        scope: scopeAll ? 'all' : 'mine',
      }),
    enabled: Boolean(user?.id && accessToken),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.count / 20)) : 1;

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4">
          {scopeAll ? 'All Customer Transactions' : 'Personal Transaction History'}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {scopeAll
            ? 'Bank-wide ledger across all customer accounts, channels, and branch teller entries.'
            : 'Ledger for your personal bank account.'}
        </Typography>
      </Box>

      <Card>
        <CardContent>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2.5 }}>
            <TextField
              label="Search reference, description, account"
              size="small"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 250 }}
            />
            <TextField
              select
              label="Transaction Type"
              size="small"
              value={transactionType}
              onChange={(e) => {
                setTransactionType(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 170 }}
            >
              <MenuItem value="">All Types</MenuItem>
              <MenuItem value="deposit">Deposit</MenuItem>
              <MenuItem value="withdrawal">Withdrawal</MenuItem>
              <MenuItem value="transfer_in">Transfer In</MenuItem>
              <MenuItem value="transfer_out">Transfer Out</MenuItem>
            </TextField>
            <TextField
              select
              label="Channel"
              size="small"
              value={channel}
              onChange={(e) => {
                setChannel(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 170 }}
            >
              <MenuItem value="">All Channels</MenuItem>
              <MenuItem value="online">Online / Digital</MenuItem>
              <MenuItem value="atm">ATM</MenuItem>
              <MenuItem value="branch_teller">Branch Teller</MenuItem>
              <MenuItem value="system">System / Opening</MenuItem>
            </TextField>
          </Stack>

          {isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Reference</TableCell>
                      {scopeAll && <TableCell>Customer / Account</TableCell>}
                      <TableCell>Type</TableCell>
                      <TableCell>Channel</TableCell>
                      <TableCell>Counterparty</TableCell>
                      <TableCell>Processed By</TableCell>
                      <TableCell>Description</TableCell>
                      <TableCell align="right">Amount</TableCell>
                      <TableCell align="right">Balance After</TableCell>
                      <TableCell>Timestamp</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(data?.results ?? []).map((t) => (
                      <TableRow key={t.id} hover>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                          {t.reference}
                        </TableCell>
                        {scopeAll && (
                          <TableCell>
                            <Link
                              component="button"
                              variant="body2"
                              underline="hover"
                              sx={{ fontWeight: 600 }}
                              onClick={() => navigate(`/staff/customers/${t.user_id}`)}
                            >
                              {t.username}
                            </Link>
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                              {t.account_number}
                            </Typography>
                          </TableCell>
                        )}
                        <TableCell>
                          <StatusChip value={t.transaction_type} />
                        </TableCell>
                        <TableCell>
                          <StatusChip value={t.channel} />
                        </TableCell>
                        <TableCell>
                          {t.related_account_number
                            ? `${t.related_account_number} (${t.related_username})`
                            : '-'}
                        </TableCell>
                        <TableCell>{t.performed_by_username || '-'}</TableCell>
                        <TableCell>{t.description || '-'}</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          ${Number(t.amount).toFixed(2)}
                        </TableCell>
                        <TableCell align="right">${Number(t.balance_after).toFixed(2)}</TableCell>
                        <TableCell>{new Date(t.created_at).toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                    {(data?.results ?? []).length === 0 && (
                      <TableRow>
                        <TableCell
                          colSpan={scopeAll ? 10 : 9}
                          align="center"
                          sx={{ py: 4, color: 'text.secondary' }}
                        >
                          No transactions match your filters.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Box>
              {totalPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
                  <Pagination
                    count={totalPages}
                    page={page}
                    onChange={(_e, val) => setPage(val)}
                  />
                </Box>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}
