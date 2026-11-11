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
import { usersApi } from '../../api/users';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';

export function ActivityLogsPage() {
  const navigate = useNavigate();
  const { user, accessToken } = useAuthStore();
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['staff-activities', page, category, search, user?.id],
    queryFn: () =>
      usersApi.getActivities({
        page,
        category: category || undefined,
        search: search || undefined,
      }),
    enabled: Boolean(user?.id && accessToken),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.count / 20)) : 1;

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4">System Activity & Audit Logs</Typography>
        <Typography variant="body2" color="text.secondary">
          Track authentication, deposits, withdrawals, teller actions, approvals, and profile updates.
        </Typography>
      </Box>

      <Card>
        <CardContent>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2.5 }}>
            <TextField
              label="Search action, description, username"
              size="small"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 270 }}
            />
            <TextField
              select
              label="Category"
              size="small"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 190 }}
            >
              <MenuItem value="">All Categories</MenuItem>
              <MenuItem value="auth">Authentication</MenuItem>
              <MenuItem value="banking">Banking</MenuItem>
              <MenuItem value="cheque">Cheque Book</MenuItem>
              <MenuItem value="endorsement">USD Endorsement</MenuItem>
              <MenuItem value="profile">Profile & Address</MenuItem>
              <MenuItem value="admin">Administration</MenuItem>
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
                      <TableCell>Timestamp</TableCell>
                      <TableCell>Subject User</TableCell>
                      <TableCell>Actor</TableCell>
                      <TableCell>Category</TableCell>
                      <TableCell>Action</TableCell>
                      <TableCell>Description</TableCell>
                      <TableCell>IP Address</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(data?.results ?? []).map((act) => (
                      <TableRow key={act.id} hover>
                        <TableCell>{new Date(act.created_at).toLocaleString()}</TableCell>
                        <TableCell>
                          <Link
                            component="button"
                            variant="body2"
                            underline="hover"
                            sx={{ fontWeight: 600 }}
                            onClick={() => navigate(`/staff/customers/${act.subject_user}`)}
                          >
                            {act.subject_username}
                          </Link>
                        </TableCell>
                        <TableCell>
                          {act.actor_username ? (
                            <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
                              <Typography variant="body2">{act.actor_username}</Typography>
                              {act.actor_role && <StatusChip value={act.actor_role} />}
                            </Stack>
                          ) : (
                            'System'
                          )}
                        </TableCell>
                        <TableCell>
                          <StatusChip value={act.category} />
                        </TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem', fontWeight: 600 }}>
                          {act.action}
                        </TableCell>
                        <TableCell>{act.description}</TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                          {act.ip_address || '-'}
                        </TableCell>
                      </TableRow>
                    ))}
                    {(data?.results ?? []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                          No activity events match your filters.
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

