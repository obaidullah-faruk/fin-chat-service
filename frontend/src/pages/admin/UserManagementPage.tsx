import { useState } from 'react';
import {
  AccountBalance as OpenAccountIcon,
  Add as AddIcon,
  DeleteOutlined as DeleteIcon,
  Edit as EditIcon,
} from '@mui/icons-material';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
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
  Tooltip,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getApiErrorMessage } from '../../api/client';
import { usersApi } from '../../api/users';
import { StatusChip } from '../../components/StatusChip';
import { useAuthStore } from '../../store/authStore';
import type { RoleName, User } from '../../types';

export function UserManagementPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { user: currentUser, accessToken, setUser } = useAuthStore();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    role: 'customer' as RoleName,
    initial_balance: '0.00',
    account_type: 'savings',
    create_bank_account: false,
  });

  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editForm, setEditForm] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    role: 'customer' as RoleName,
    is_active: true,
  });

  const [openAccUser, setOpenAccUser] = useState<User | null>(null);
  const [openAccForm, setOpenAccForm] = useState<{
    account_type: 'savings' | 'current' | 'salary';
    initial_balance: string;
  }>({ account_type: 'savings', initial_balance: '1000.00' });

  const { data: roles = [] } = useQuery({
    queryKey: ['roles', currentUser?.id],
    queryFn: usersApi.getRoles,
    enabled: Boolean(currentUser?.id && accessToken),
  });

  const { data: usersData, isLoading } = useQuery({
    queryKey: ['users', page, search, roleFilter, currentUser?.id],
    queryFn: () =>
      usersApi.getUsers({
        page,
        search: search || undefined,
        role__name: roleFilter || undefined,
      }),
    enabled: Boolean(currentUser?.id && accessToken),
  });

  const createMutation = useMutation({
    mutationFn: () => usersApi.createUser(createForm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['staff-customers'] });
      queryClient.invalidateQueries({ queryKey: ['staff-dashboard'] });
      setCreateOpen(false);
      setCreateForm({
        username: '',
        email: '',
        password: '',
        first_name: '',
        last_name: '',
        role: 'customer',
        initial_balance: '0.00',
        account_type: 'savings',
        create_bank_account: false,
      });
      setFeedback({ type: 'success', text: 'User created successfully.' });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  const updateMutation = useMutation({
    mutationFn: () => usersApi.updateUser(editingUser!.id, editForm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setEditingUser(null);
      setFeedback({ type: 'success', text: 'User updated successfully.' });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  const openBankAccountMutation = useMutation({
    mutationFn: () => usersApi.openBankAccount(openAccUser!.id, openAccForm),
    onSuccess: (updatedUser) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['staff-customers'] });
      queryClient.invalidateQueries({ queryKey: ['staff-dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['me'] });
      if (currentUser && updatedUser.id === currentUser.id) {
        setUser(updatedUser);
      }
      setOpenAccUser(null);
      setFeedback({
        type: 'success',
        text: `Personal bank account ${updatedUser.bank_account?.account_number} opened for ${updatedUser.username}.`,
      });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => usersApi.deleteUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setFeedback({ type: 'success', text: 'User deleted.' });
    },
    onError: (err) => setFeedback({ type: 'error', text: getApiErrorMessage(err) }),
  });

  const openEdit = (u: User) => {
    setEditingUser(u);
    setEditForm({
      first_name: u.first_name,
      last_name: u.last_name,
      phone: u.phone,
      role: u.role,
      is_active: u.is_active,
    });
  };

  const totalPages = usersData ? Math.max(1, Math.ceil(usersData.count / 20)) : 1;
  const showBankFields = createForm.role === 'customer' || createForm.create_bank_account;

  return (
    <Stack spacing={3}>
      <Stack
        direction="row"
        sx={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}
      >
        <Typography variant="h4">User Management</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          Create User
        </Button>
      </Stack>

      {feedback && (
        <Alert severity={feedback.type} onClose={() => setFeedback(null)}>
          {feedback.text}
        </Alert>
      )}

      <Card>
        <CardContent>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2.5 }}>
            <TextField
              label="Search username, email, name"
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
              label="Role"
              size="small"
              value={roleFilter}
              onChange={(e) => {
                setRoleFilter(e.target.value);
                setPage(1);
              }}
              sx={{ minWidth: 160 }}
            >
              <MenuItem value="">All Roles</MenuItem>
              <MenuItem value="superadmin">Superadmin</MenuItem>
              <MenuItem value="admin">Admin</MenuItem>
              <MenuItem value="manager">Manager</MenuItem>
              <MenuItem value="customer">Customer</MenuItem>
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
                      <TableCell>Username</TableCell>
                      <TableCell>Email</TableCell>
                      <TableCell>Name</TableCell>
                      <TableCell>Role</TableCell>
                      <TableCell>Personal Bank Account</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(usersData?.results ?? []).map((u) => (
                      <TableRow key={u.id} hover>
                        <TableCell sx={{ fontWeight: 600 }}>{u.username}</TableCell>
                        <TableCell>{u.email}</TableCell>
                        <TableCell>{`${u.first_name} ${u.last_name}`.trim() || '-'}</TableCell>
                        <TableCell>
                          <StatusChip value={u.role} />
                        </TableCell>
                        <TableCell>
                          {u.bank_account ? (
                            <Link
                              component="button"
                              variant="body2"
                              underline="hover"
                              onClick={() => navigate(`/staff/customers/${u.id}`)}
                            >
                              {u.bank_account.account_number} ($
                              {Number(u.bank_account.balance).toLocaleString()})
                            </Link>
                          ) : (
                            <Button
                              size="small"
                              startIcon={<OpenAccountIcon fontSize="small" />}
                              onClick={() => {
                                setOpenAccUser(u);
                                setOpenAccForm({ account_type: 'savings', initial_balance: '1000.00' });
                              }}
                            >
                              Open Personal Account
                            </Button>
                          )}
                        </TableCell>
                        <TableCell>
                          <StatusChip value={u.is_active ? 'active' : 'inactive'} />
                        </TableCell>
                        <TableCell align="right">
                          <Tooltip title="Edit User">
                            <IconButton size="small" onClick={() => openEdit(u)}>
                              <EditIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          {u.id !== currentUser?.id && (
                            <Tooltip title="Delete User">
                              <IconButton
                                size="small"
                                color="error"
                                onClick={() => deleteMutation.mutate(u.id)}
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
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

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Create New User</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={2}>
              <TextField
                label="Username"
                value={createForm.username}
                onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
                required
                fullWidth
              />
              <TextField
                label="Email"
                type="email"
                value={createForm.email}
                onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
                required
                fullWidth
              />
            </Stack>
            <TextField
              label="Password"
              type="password"
              value={createForm.password}
              onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
              required
              fullWidth
            />
            <Stack direction="row" spacing={2}>
              <TextField
                label="First Name"
                value={createForm.first_name}
                onChange={(e) => setCreateForm({ ...createForm, first_name: e.target.value })}
                fullWidth
              />
              <TextField
                label="Last Name"
                value={createForm.last_name}
                onChange={(e) => setCreateForm({ ...createForm, last_name: e.target.value })}
                fullWidth
              />
            </Stack>
            <TextField
              select
              label="Role"
              value={createForm.role}
              onChange={(e) =>
                setCreateForm({ ...createForm, role: e.target.value as RoleName })
              }
              fullWidth
            >
              {roles.map((r) => (
                <MenuItem key={r.id} value={r.name}>
                  {r.name.toUpperCase()}
                </MenuItem>
              ))}
            </TextField>
            {createForm.role !== 'customer' && (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={createForm.create_bank_account}
                    onChange={(e) =>
                      setCreateForm({ ...createForm, create_bank_account: e.target.checked })
                    }
                  />
                }
                label="Also open a separate personal customer bank account for this staff user"
              />
            )}
            {showBankFields && (
              <Stack direction="row" spacing={2}>
                <TextField
                  label="Initial Balance (USD)"
                  type="number"
                  slotProps={{ htmlInput: { step: '0.01', min: '0' } }}
                  value={createForm.initial_balance}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, initial_balance: e.target.value })
                  }
                  fullWidth
                />
                <TextField
                  select
                  label="Account Type"
                  value={createForm.account_type}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, account_type: e.target.value })
                  }
                  fullWidth
                >
                  <MenuItem value="savings">Savings</MenuItem>
                  <MenuItem value="current">Current</MenuItem>
                  <MenuItem value="salary">Salary</MenuItem>
                </TextField>
              </Stack>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            {createMutation.isPending ? 'Creating...' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(editingUser)} onClose={() => setEditingUser(null)} fullWidth maxWidth="xs">
        <DialogTitle>Edit User: {editingUser?.username}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="First Name"
              value={editForm.first_name}
              onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })}
              fullWidth
            />
            <TextField
              label="Last Name"
              value={editForm.last_name}
              onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })}
              fullWidth
            />
            <TextField
              label="Phone"
              value={editForm.phone}
              onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
              fullWidth
            />
            <TextField
              select
              label="Role"
              value={editForm.role}
              onChange={(e) => setEditForm({ ...editForm, role: e.target.value as RoleName })}
              fullWidth
            >
              {roles.map((r) => (
                <MenuItem key={r.id} value={r.name}>
                  {r.name.toUpperCase()}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={editForm.is_active}
                  onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                />
              }
              label="Active"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditingUser(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={updateMutation.isPending}
            onClick={() => updateMutation.mutate()}
          >
            {updateMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(openAccUser)} onClose={() => setOpenAccUser(null)} fullWidth maxWidth="xs">
        <DialogTitle>Open Personal Bank Account</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              User: <strong>{openAccUser?.username}</strong> ({openAccUser?.role.toUpperCase()})
            </Typography>
            <TextField
              select
              label="Account Type"
              value={openAccForm.account_type}
              onChange={(e) =>
                setOpenAccForm({
                  ...openAccForm,
                  account_type: e.target.value as 'savings' | 'current' | 'salary',
                })
              }
              fullWidth
            >
              <MenuItem value="savings">Savings</MenuItem>
              <MenuItem value="current">Current</MenuItem>
              <MenuItem value="salary">Salary</MenuItem>
            </TextField>
            <TextField
              label="Initial Balance (USD)"
              type="number"
              slotProps={{ htmlInput: { step: '0.01', min: '0' } }}
              value={openAccForm.initial_balance}
              onChange={(e) => setOpenAccForm({ ...openAccForm, initial_balance: e.target.value })}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAccUser(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={openBankAccountMutation.isPending}
            onClick={() => openBankAccountMutation.mutate()}
          >
            {openBankAccountMutation.isPending ? 'Opening...' : 'Open Account'}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
