import { useState } from 'react';
import {
  Visibility as InspectIcon,
} from '@mui/icons-material';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
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

export function CustomersPage() {
  const navigate = useNavigate();
  const { user, accessToken } = useAuthStore();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [accountType, setAccountType] = useState('');
  const [accountActive, setAccountActive] = useState('');
  const [usdEndorsed, setUsdEndorsed] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['staff-customers', page, search, accountType, accountActive, usdEndorsed, user?.id],
    queryFn: () =>
      bankingApi.getCustomers({
        page,
        search: search || undefined,
        account_type: accountType || undefined,
        account_active: accountActive || undefined,
        is_usd_endorsed: usdEndorsed || undefined,
      }),
    enabled: Boolean(user?.id && accessToken),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.count / 20)) : 1;

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4">Customer Directory</Typography>
        <Typography variant="body2" color="text.secondary">
          Inspect customer profiles, bank accounts, transaction histories, and audit activities.
        </Typography>
      </Box>

      <Card>
        <CardContent>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2.5 }}>
            <TextField
              label="Search name, username, email, account #"
              size="small"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 280 }}
            />
            <TextField
              select
              label="Account Type"
              size="small"
              value={accountType}
              onChange={(e) => {
                setAccountType(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="">All Types</MenuItem>
              <MenuItem value="savings">Savings</MenuItem>
              <MenuItem value="current">Current</MenuItem>
              <MenuItem value="salary">Salary</MenuItem>
            </TextField>
            <TextField
              select
              label="Account Status"
              size="small"
              value={accountActive}
              onChange={(e) => {
                setAccountActive(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="">All Statuses</MenuItem>
              <MenuItem value="true">Active</MenuItem>
              <MenuItem value="false">Frozen</MenuItem>
            </TextField>
            <TextField
              select
              label="USD Endorsement"
              size="small"
              value={usdEndorsed}
              onChange={(e) => {
                setUsdEndorsed(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 170 }}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="true">USD Endorsed</MenuItem>
              <MenuItem value="false">Not Endorsed</MenuItem>
            </TextField>
          </Stack>

          {isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 5 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Customer</TableCell>
                      <TableCell>Contact</TableCell>
                      <TableCell>Account</TableCell>
                      <TableCell align="right">Balance</TableCell>
                      <TableCell>USD Endorsement</TableCell>
                      <TableCell align="center">Txns</TableCell>
                      <TableCell>Pending Queue</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">Action</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(data?.results ?? []).map((cust) => (
                      <TableRow key={cust.id} hover>
                        <TableCell>
                          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              {cust.full_name}
                            </Typography>
                            {cust.role !== 'customer' && <StatusChip value={cust.role} />}
                          </Stack>
                          <Typography variant="caption" color="text.secondary">
                            @{cust.username}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">{cust.email}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {cust.phone || 'No phone'}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          {cust.bank_account ? (
                            <>
                              <Typography variant="body2" sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
                                {cust.bank_account.account_number}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {cust.bank_account.account_type.toUpperCase()}
                              </Typography>
                            </>
                          ) : (
                            '-'
                          )}
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 700 }}>
                          {cust.bank_account
                            ? `$${Number(cust.bank_account.balance).toLocaleString(undefined, {
                                minimumFractionDigits: 2,
                              })}`
                            : '-'}
                        </TableCell>
                        <TableCell>
                          {cust.bank_account?.is_usd_endorsed ? (
                            <Chip
                              size="small"
                              color="success"
                              variant="outlined"
                              label={`USD $${Number(
                                cust.bank_account.usd_endorsement_limit
                              ).toLocaleString()}`}
                            />
                          ) : (
                            <Typography variant="caption" color="text.secondary">
                              Not Endorsed
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell align="center">{cust.transaction_count}</TableCell>
                        <TableCell>
                          {cust.pending_cheques === 0 && cust.pending_endorsements === 0 ? (
                            <Typography variant="caption" color="text.secondary">
                              None
                            </Typography>
                          ) : (
                            <Stack direction="row" spacing={0.5}>
                              {cust.pending_cheques > 0 && (
                                <Chip
                                  size="small"
                                  color="warning"
                                  label={`${cust.pending_cheques} Cheque`}
                                />
                              )}
                              {cust.pending_endorsements > 0 && (
                                <Chip
                                  size="small"
                                  color="info"
                                  label={`${cust.pending_endorsements} USD`}
                                />
                              )}
                            </Stack>
                          )}
                        </TableCell>
                        <TableCell>
                          {cust.bank_account ? (
                            <StatusChip
                              value={cust.bank_account.is_active ? 'active' : 'frozen'}
                            />
                          ) : (
                            <StatusChip value={cust.is_active ? 'active' : 'inactive'} />
                          )}
                        </TableCell>
                        <TableCell align="right">
                          <Button
                            size="small"
                            variant="outlined"
                            startIcon={<InspectIcon fontSize="small" />}
                            onClick={() => navigate(`/staff/customers/${cust.id}`)}
                          >
                            View 360°
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                    {(data?.results ?? []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={9} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                          No customers match your filters.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </Box>
              {totalPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
                  <Pagination count={totalPages} page={page} onChange={(_e, val) => setPage(val)} />
                </Box>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </Stack>
  );
}

