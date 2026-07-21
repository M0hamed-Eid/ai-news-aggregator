from django import forms
from django.contrib.auth.forms import (
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from .models import User

BOOTSTRAP_INPUT = {"class": "form-control"}


class RegisterForm(UserCreationForm):
    """Sign-up form keyed on email."""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={**BOOTSTRAP_INPUT, "autofocus": True}),
    )
    first_name = forms.CharField(
        required=False, widget=forms.TextInput(attrs=BOOTSTRAP_INPUT)
    )

    class Meta:
        model = User
        fields = ("email", "first_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update(BOOTSTRAP_INPUT)
        self.fields["password2"].widget.attrs.update(BOOTSTRAP_INPUT)


class BootstrapPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({**BOOTSTRAP_INPUT, "autofocus": True})


class BootstrapSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update({**BOOTSTRAP_INPUT, "autofocus": True})
        self.fields["new_password2"].widget.attrs.update(BOOTSTRAP_INPUT)
