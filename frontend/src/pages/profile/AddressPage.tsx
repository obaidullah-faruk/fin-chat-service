import { useState } from 'react';
import {
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
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getApiErrorMessage } from '../../api/client';
import { usersApi } from '../../api/users';
import { useAuthStore } from '../../store/authStore';
import type { Address } from '../../types';

const EMPTY_FORM = {
  label: 'home' as Address['label'],
  street: '',
  city: '',
  state: '',
  postal_code: '',
  country: '',
  is_primary: false,
};

export function AddressPage() {
  const queryClient = useQueryClient();
  const { user, accessToken } = useAuthStore();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Address | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const { data: addresses = [], isLoading } = useQuery({
    queryKey: ['addresses', user?.id],
    queryFn: usersApi.getAddresses,
    enabled: Boolean(user?.id && accessToken),
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      editing
        ? usersApi.updateAddress(editing.id, form)
        : usersApi.createAddress(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['addresses'] });
      setDialogOpen(false);
      setEditing(null);
      setForm(EMPTY_FORM);
      setFeedback({ type: 'success', text: 'Address saved successfully.' });
    },
    onError: (err) => {
      setFeedback({ type: 'error', text: getApiErrorMessage(err) });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => usersApi.deleteAddress(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['addresses'] });
      setFeedback({ type: 'success', text: 'Address deleted.' });
    },
    onError: (err) => {
      setFeedback({ type: 'error', text: getApiErrorMessage(err) });
    },
  });

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (addr: Address) => {
    setEditing(addr);
    setForm({
      label: addr.label,
      street: addr.street,
      city: addr.city,
      state: addr.state,
      postal_code: addr.postal_code,
      country: addr.country,
      is_primary: addr.is_primary,
    });
    setDialogOpen(true);
  };

  return (
    <Stack spacing={3}>
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4">My Addresses</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={openCreate}>
          Add Address
        </Button>
      </Stack>

      {feedback && (
        <Alert severity={feedback.type} onClose={() => setFeedback(null)}>
          {feedback.text}
        </Alert>
      )}

      {isLoading ? (
        <CircularProgress />
      ) : addresses.length === 0 ? (
        <Alert severity="info">No addresses saved yet. Add your first address above.</Alert>
      ) : (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' },
            gap: 2.5,
          }}
        >
          {addresses.map((addr) => (
            <Card key={addr.id}>
              <CardContent>
                <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                    <Typography variant="h6" sx={{ textTransform: 'capitalize' }}>
                      {addr.label}
                    </Typography>
                    {addr.is_primary && (
                      <Chip label="PRIMARY" color="primary" size="small" />
                    )}
                  </Stack>
                  <Stack direction="row">
                    <IconButton size="small" onClick={() => openEdit(addr)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => deleteMutation.mutate(addr.id)}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                </Stack>
                <Typography variant="body1" sx={{ mt: 1 }}>
                  {addr.street}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {addr.city}, {addr.state} {addr.postal_code}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {addr.country}
                </Typography>
              </CardContent>
            </Card>
          ))}
        </Box>
      )}

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editing ? 'Edit Address' : 'Add Address'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Label"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value as Address['label'] })}
              fullWidth
            >
              <MenuItem value="home">Home</MenuItem>
              <MenuItem value="work">Work</MenuItem>
              <MenuItem value="other">Other</MenuItem>
            </TextField>
            <TextField
              label="Street Address"
              value={form.street}
              onChange={(e) => setForm({ ...form, street: e.target.value })}
              required
              fullWidth
            />
            <Stack direction="row" spacing={2}>
              <TextField
                label="City"
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                required
                fullWidth
              />
              <TextField
                label="State / Division"
                value={form.state}
                onChange={(e) => setForm({ ...form, state: e.target.value })}
                required
                fullWidth
              />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField
                label="Postal Code"
                value={form.postal_code}
                onChange={(e) => setForm({ ...form, postal_code: e.target.value })}
                required
                fullWidth
              />
              <TextField
                label="Country"
                value={form.country}
                onChange={(e) => setForm({ ...form, country: e.target.value })}
                required
                fullWidth
              />
            </Stack>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.is_primary}
                  onChange={(e) => setForm({ ...form, is_primary: e.target.checked })}
                />
              }
              label="Set as primary address"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

