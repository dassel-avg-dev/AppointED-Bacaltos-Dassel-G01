from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from .managers import UserManager


class Department(models.Model):
    department_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "departments"
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractBaseUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        FACULTY = "FACULTY", "Faculty"
        ADMIN = "ADMIN", "Administrator"

    user_id = models.AutoField(primary_key=True)
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="department_id",
        related_name="users",
    )
    email = models.EmailField(max_length=100, unique=True)  # BR-01
    password = models.CharField(max_length=255, db_column="password_hash")
    full_name = models.CharField(max_length=100)
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.STUDENT, db_default=Role.STUDENT
    )
    is_active = models.BooleanField(default=True, db_default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    last_login = None  # not part of the SDD schema

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        constraints = [
            models.CheckConstraint(  # BR-02
                condition=Q(role__in=["STUDENT", "FACULTY", "ADMIN"]),
                name="users_role_check",
            )
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    # Role helpers
    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_faculty(self):
        return self.role == self.Role.FACULTY

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    # Django Admin access is derived from the role (no extra columns).
    @property
    def is_staff(self):
        return self.is_active and self.role == self.Role.ADMIN

    @property
    def is_superuser(self):
        return self.is_staff

    def has_perm(self, perm, obj=None):
        return self.is_staff

    def has_module_perms(self, app_label):
        return self.is_staff
