from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    Permission,
    PermissionsMixin,
)
from django.db import models, transaction


class Role(models.Model):
    class Name(models.TextChoices):
        SUPERADMIN = 'superadmin', 'Superadmin'
        ADMIN = 'admin', 'Admin'
        MANAGER = 'manager', 'Manager'
        CUSTOMER = 'customer', 'Customer'

    name = models.CharField(max_length=50, unique=True, choices=Name.choices)
    description = models.CharField(max_length=255, blank=True)
    permissions = models.ManyToManyField(Permission, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self) -> str:
        return self.name


class CustomUserManager(BaseUserManager):
    def create_user(self, username: str, email: str, password: str | None = None, **extra_fields):
        if not username:
            raise ValueError('Username is required.')
        if not email:
            raise ValueError('Email is required.')

        email = self.normalize_email(email)
        role = extra_fields.pop('role', None)
        if role is None:
            role, _ = Role.objects.get_or_create(
                name=Role.Name.CUSTOMER,
                defaults={'description': 'Standard banking customer'},
            )

        user = self.model(username=username, email=email, role=role, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        UserProfile.objects.get_or_create(user=user)
        return user

    def create_superuser(self, username: str, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        superadmin_role, _ = Role.objects.get_or_create(
            name=Role.Name.SUPERADMIN,
            defaults={'description': 'Full system administrator'},
        )
        extra_fields['role'] = superadmin_role
        return self.create_user(username=username, email=email, password=password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='users')
    created_by = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='managed_users',
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.username} ({self.role.name})'

    @property
    def full_name(self) -> str:
        name = f'{self.first_name} {self.last_name}'.strip()
        return name or self.username


class UserProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='profile')
    date_of_birth = models.DateField(null=True, blank=True)
    national_id = models.CharField(max_length=50, blank=True)
    bio = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f'Profile<{self.user.username}>'


class Address(models.Model):
    class Label(models.TextChoices):
        HOME = 'home', 'Home'
        WORK = 'work', 'Work'
        OTHER = 'other', 'Other'

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=50, choices=Label.choices, default=Label.HOME)
    street = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_primary', '-created_at']

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_primary:
                Address.objects.filter(user=self.user, is_primary=True).exclude(pk=self.pk).update(
                    is_primary=False
                )
            elif not Address.objects.filter(user=self.user, is_primary=True).exclude(pk=self.pk).exists():
                self.is_primary = True
            super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f'{self.user.username} - {self.label}: {self.city}'


class ActivityLog(models.Model):
    class Category(models.TextChoices):
        AUTH = 'auth', 'Authentication'
        BANKING = 'banking', 'Banking'
        CHEQUE = 'cheque', 'Cheque Book'
        ENDORSEMENT = 'endorsement', 'USD Endorsement'
        PROFILE = 'profile', 'Profile & Address'
        ADMIN = 'admin', 'Administration'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='acted_activities',
    )
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subject_activities',
    )
    category = models.CharField(max_length=30, choices=Category.choices)
    action = models.CharField(max_length=64)
    description = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['subject_user', '-created_at']),
            models.Index(fields=['category', '-created_at']),
        ]

    def __str__(self) -> str:
        return f'{self.action} ({self.subject_user.username})'

