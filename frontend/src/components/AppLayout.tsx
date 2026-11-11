import { useEffect, useState } from 'react';
import {
  AccountBalance as BankIcon,
  AccountCircle as ProfileIcon,
  AdminPanelSettings as AdminIcon,
  ArrowDownward as DepositIcon,
  ArrowUpward as WithdrawIcon,
  Badge as BackOfficeIcon,
  CheckCircleOutlined as ApprovalIcon,
  CurrencyExchange as EndorsementIcon,
  Dashboard as DashboardIcon,
  Groups as CustomersIcon,
  History as ActivityIcon,
  LocationOn as AddressIcon,
  Logout as LogoutIcon,
  Menu as MenuIcon,
  MenuBook as ChequeIcon,
  People as UsersIcon,
  Person as PersonalIcon,
  ReceiptLong as TransactionsIcon,
  SwapHoriz as TransferIcon,
} from '@mui/icons-material';
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Toolbar,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { authApi } from '../api/auth';
import { API_BASE_URL } from '../api/client';
import { useAuthStore } from '../store/authStore';
import type { RoleName, WorkspaceMode } from '../types';
import { ChatWidget } from './ChatWidget/ChatWidget';
import { StatusChip } from './StatusChip';

const DRAWER_WIDTH = 260;

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
  roles?: RoleName[];
  matchPrefix?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const STAFF_NAV_SECTIONS: NavSection[] = [
  {
    title: 'Back-Office',
    items: [
      { label: 'Operations Dashboard', path: '/dashboard', icon: <DashboardIcon fontSize="small" /> },
      {
        label: 'Customers',
        path: '/staff/customers',
        icon: <CustomersIcon fontSize="small" />,
        roles: ['manager', 'admin', 'superadmin'],
        matchPrefix: true,
      },
      {
        label: 'All Transactions',
        path: '/staff/transactions',
        icon: <TransactionsIcon fontSize="small" />,
        roles: ['manager', 'admin', 'superadmin'],
      },
      {
        label: 'Activity Logs',
        path: '/staff/activities',
        icon: <ActivityIcon fontSize="small" />,
        roles: ['manager', 'admin', 'superadmin'],
      },
    ],
  },
  {
    title: 'Approvals',
    items: [
      {
        label: 'Cheque Approvals',
        path: '/admin/cheque-requests',
        icon: <ApprovalIcon fontSize="small" />,
        roles: ['manager', 'admin', 'superadmin'],
      },
      {
        label: 'USD Endorsements',
        path: '/admin/endorsements',
        icon: <EndorsementIcon fontSize="small" />,
        roles: ['manager', 'admin', 'superadmin'],
      },
    ],
  },
  {
    title: 'Administration',
    items: [
      {
        label: 'User Management',
        path: '/admin/users',
        icon: <UsersIcon fontSize="small" />,
        roles: ['admin', 'superadmin'],
      },
    ],
  },
  {
    title: 'My Profile',
    items: [
      { label: 'Profile', path: '/profile', icon: <ProfileIcon fontSize="small" /> },
      { label: 'Addresses', path: '/profile/address', icon: <AddressIcon fontSize="small" /> },
    ],
  },
];

const PERSONAL_NAV_SECTIONS: NavSection[] = [
  {
    title: 'Overview',
    items: [
      { label: 'Dashboard', path: '/dashboard', icon: <DashboardIcon fontSize="small" /> },
      { label: 'Profile', path: '/profile', icon: <ProfileIcon fontSize="small" /> },
      { label: 'Addresses', path: '/profile/address', icon: <AddressIcon fontSize="small" /> },
    ],
  },
  {
    title: 'Personal Banking',
    items: [
      { label: 'Account', path: '/banking', icon: <BankIcon fontSize="small" /> },
      { label: 'Deposit', path: '/banking/deposit', icon: <DepositIcon fontSize="small" /> },
      { label: 'Withdraw', path: '/banking/withdraw', icon: <WithdrawIcon fontSize="small" /> },
      { label: 'Transfer', path: '/banking/transfer', icon: <TransferIcon fontSize="small" /> },
      {
        label: 'Transactions',
        path: '/banking/transactions',
        icon: <TransactionsIcon fontSize="small" />,
      },
      { label: 'Cheque Book', path: '/cheque', icon: <ChequeIcon fontSize="small" /> },
      {
        label: 'USD Endorsement',
        path: '/endorsement',
        icon: <EndorsementIcon fontSize="small" />,
      },
    ],
  },
];

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, accessToken, workspace, setWorkspace, setUser, refreshToken, logout } =
    useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const { data: freshUser } = useQuery({
    queryKey: ['me', user?.id],
    queryFn: authApi.getMe,
    enabled: Boolean(user?.id && accessToken),
    staleTime: 0,
    gcTime: 0,
  });

  useEffect(() => {
    if (freshUser && user?.id && freshUser.id === user.id) {
      setUser(freshUser);
    }
  }, [freshUser, user?.id, setUser]);

  const isStaffRole = Boolean(
    user && ['manager', 'admin', 'superadmin'].includes(user.role)
  );
  const hasPersonalAccount = Boolean(user?.bank_account);
  const inStaffWorkspace = Boolean(isStaffRole && workspace === 'staff');

  const activeSections = inStaffWorkspace ? STAFF_NAV_SECTIONS : PERSONAL_NAV_SECTIONS;

  const handleWorkspaceChange = (nextMode: WorkspaceMode) => {
    setWorkspace(nextMode);
    setMobileOpen(false);
    navigate('/dashboard');
  };

  const handleLogout = () => {
    const currentRefresh = refreshToken;
    const currentAccess = accessToken;
    logout();
    navigate('/login', { replace: true });
    if (currentRefresh) {
      void axios
        .post(
          `${API_BASE_URL}/auth/logout/`,
          { refresh: currentRefresh },
          currentAccess ? { headers: { Authorization: `Bearer ${currentAccess}` } } : undefined
        )
        .catch(() => undefined);
    }
  };

  const isItemSelected = (item: NavItem) => {
    if (item.matchPrefix) {
      return location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
    }
    return location.pathname === item.path;
  };

  const drawerContent = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Toolbar sx={{ px: 2, justifyContent: 'space-between' }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <BankIcon color="primary" />
          <Typography variant="h6" color="primary" sx={{ fontWeight: 700 }}>
            FinChat
          </Typography>
        </Stack>
        {isStaffRole && (
          <Chip
            size="small"
            label={inStaffWorkspace ? 'STAFF' : 'PERSONAL'}
            color={inStaffWorkspace ? 'secondary' : 'primary'}
            variant="filled"
            sx={{ fontSize: '0.65rem', fontWeight: 700, height: 22 }}
          />
        )}
      </Toolbar>
      <Divider />

      {isStaffRole && hasPersonalAccount && (
        <Box sx={{ px: 1.5, py: 1.25, borderBottom: '1px solid #e2e8f0', bgcolor: '#f8fafc' }}>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: 'block', mb: 0.75, fontWeight: 600 }}
          >
            Active Workspace
          </Typography>
          <ToggleButtonGroup
            value={workspace}
            exclusive
            fullWidth
            size="small"
            onChange={(_e, val) => {
              if (val) handleWorkspaceChange(val as WorkspaceMode);
            }}
          >
            <ToggleButton value="staff" sx={{ textTransform: 'none', fontSize: '0.75rem', py: 0.5 }}>
              <BackOfficeIcon sx={{ fontSize: 15, mr: 0.5 }} />
              Back-Office
            </ToggleButton>
            <ToggleButton value="personal" sx={{ textTransform: 'none', fontSize: '0.75rem', py: 0.5 }}>
              <PersonalIcon sx={{ fontSize: 15, mr: 0.5 }} />
              Personal
            </ToggleButton>
          </ToggleButtonGroup>
        </Box>
      )}

      <Box sx={{ flex: 1, overflowY: 'auto', py: 1 }}>
        {activeSections.map((section) => {
          const visibleItems = section.items.filter(
            (item) => !item.roles || (user && item.roles.includes(user.role))
          );
          if (visibleItems.length === 0) return null;
          return (
            <List
              key={section.title}
              dense
              subheader={
                <ListSubheader
                  component="div"
                  sx={{
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    letterSpacing: 0.6,
                    textTransform: 'uppercase',
                    lineHeight: '32px',
                    bgcolor: 'transparent',
                  }}
                >
                  {section.title}
                </ListSubheader>
              }
            >
              {visibleItems.map((item) => {
                const selected = isItemSelected(item);
                return (
                  <ListItemButton
                    key={item.path}
                    selected={selected}
                    onClick={() => {
                      navigate(item.path);
                      setMobileOpen(false);
                    }}
                    sx={{ mx: 1, borderRadius: 1.5, mb: 0.25 }}
                  >
                    <ListItemIcon sx={{ minWidth: 34, color: selected ? 'primary.main' : 'inherit' }}>
                      {item.icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.label}
                      slotProps={{
                        primary: {
                          variant: 'body2',
                          sx: { fontWeight: selected ? 600 : 500 },
                        },
                      }}
                    />
                  </ListItemButton>
                );
              })}
            </List>
          );
        })}
      </Box>
      <Divider />
      <List dense>
        <ListItemButton onClick={handleLogout} sx={{ mx: 1, my: 0.5, borderRadius: 1.5 }}>
          <ListItemIcon sx={{ minWidth: 34 }}>
            <LogoutIcon fontSize="small" color="error" />
          </ListItemIcon>
          <ListItemText
            primary="Sign Out"
            slotProps={{
              primary: { variant: 'body2', color: 'error.main', sx: { fontWeight: 600 } },
            }}
          />
        </ListItemButton>
      </List>
    </Box>
  );

  const portalTitle = inStaffWorkspace
    ? 'Staff Back-Office Portal'
    : isStaffRole
    ? 'Personal Customer Account View'
    : 'Customer Banking Portal';

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar
        position="fixed"
        color="inherit"
        elevation={0}
        sx={{
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { md: `${DRAWER_WIDTH}px` },
          borderBottom: '1px solid #e2e8f0',
          bgcolor: inStaffWorkspace ? '#ffffff' : 'background.paper',
        }}
      >
        <Toolbar sx={{ justifyContent: 'space-between', gap: 1 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <IconButton
              edge="start"
              onClick={() => setMobileOpen(!mobileOpen)}
              sx={{ display: { md: 'none' } }}
            >
              <MenuIcon />
            </IconButton>
            {inStaffWorkspace ? (
              <AdminIcon color="secondary" fontSize="small" />
            ) : (
              <BankIcon color="primary" fontSize="small" />
            )}
            <Typography variant="subtitle1" color="text.primary" sx={{ fontWeight: 600 }}>
              {portalTitle}
            </Typography>
          </Stack>
          {user && (
            <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
              {isStaffRole && hasPersonalAccount && (
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() =>
                    handleWorkspaceChange(inStaffWorkspace ? 'personal' : 'staff')
                  }
                  sx={{ display: { xs: 'none', lg: 'inline-flex' } }}
                >
                  {inStaffWorkspace ? 'Switch to Personal Account' : 'Back to Staff Portal'}
                </Button>
              )}
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ display: { xs: 'none', sm: 'block' } }}
              >
                {user.username} ({user.email})
              </Typography>
              <StatusChip value={user.role} />
            </Stack>
          )}
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
          }}
        >
          {drawerContent}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': {
              width: DRAWER_WIDTH,
              boxSizing: 'border-box',
              borderRight: '1px solid #e2e8f0',
            },
          }}
          open
        >
          {drawerContent}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: { xs: 2, sm: 3 },
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          mt: '64px',
          pb: 10,
        }}
      >
        {isStaffRole && !inStaffWorkspace && user?.bank_account && (
          <Alert
            severity="info"
            sx={{ mb: 2.5 }}
            action={
              <Button
                color="inherit"
                size="small"
                onClick={() => handleWorkspaceChange('staff')}
              >
                Return to Back-Office
              </Button>
            }
          >
            You are viewing your <strong>Personal Customer Account</strong> (
            {user.bank_account.account_number}). Only your personal transactions and banking
            actions are shown here.
          </Alert>
        )}
        <Outlet key={user?.id ?? 'guest'} />
      </Box>

      <ChatWidget key={user?.id ?? 'guest-chat'} />
    </Box>
  );
}
