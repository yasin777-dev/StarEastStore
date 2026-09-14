"""Account views: register, login/logout, profile, addresses, passwords."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login as auth_login, views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.utils import rate_limit

from .forms import (
    AddressForm,
    ChangePasswordForm,
    EmailAuthenticationForm,
    ProfileForm,
    RegisterForm,
)
from .models import Address
from .emails import send_welcome_email


@rate_limit('register', limit=10, per_seconds=600)
def register(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
            send_welcome_email(user)
            auth_login(request, user, backend='accounts.backends.EmailBackend')
            messages.success(
                request,
                f'Welcome to the store, {user.get_full_name() or user.username}! '
                'Your account has been created.',
            )
            return redirect('core:home')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


@rate_limit('login', limit=8, per_seconds=300)
def custom_login(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    next_url = request.POST.get('next') or request.GET.get('next')
    if request.method == 'POST':
        form = EmailAuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user, backend='accounts.backends.EmailBackend')
            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()},
            ):
                return redirect(next_url)
            return redirect('core:home')
    else:
        form = EmailAuthenticationForm(request)
    return render(request, 'accounts/login.html', {'form': form, 'next': next_url})


def custom_logout(request):
    """Logout accepts POST only (CSRF-protected, per Django best practice)."""
    if request.method == 'POST':
        from django.contrib.auth import logout

        logout(request)
        messages.info(request, 'You have been logged out.')
        return redirect('core:home')
    return redirect('core:home')


@login_required
def profile(request):
    return render(request, 'accounts/profile.html')


@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, user=request.user,
                           instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated.')
            return redirect('accounts:profile')
    else:
        form = ProfileForm(user=request.user, instance=request.user.profile)
    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
def address_list(request):
    return render(request, 'accounts/addresses.html', {
        'addresses': request.user.addresses.all(),
    })


@login_required
def address_create(request):
    next_url = request.POST.get('next') or request.GET.get('next')
    if request.method == 'POST':
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            with transaction.atomic():
                address.save()
            messages.success(request, 'Address added.')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('accounts:address_list')
    else:
        form = AddressForm(initial={'full_name': request.user.get_full_name(),
                                    'phone': request.user.profile.phone})
    return render(request, 'accounts/address_form.html', {
        'form': form, 'next': next_url, 'is_create': True,
    })


@login_required
def address_edit(request, pk: int):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            messages.success(request, 'Address updated.')
            return redirect('accounts:address_list')
    else:
        form = AddressForm(instance=address)
    return render(request, 'accounts/address_form.html', {
        'form': form, 'address': address, 'is_create': False,
    })


@login_required
@require_POST
def address_delete(request, pk: int):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.delete()
    messages.success(request, 'Address removed.')
    return redirect('accounts:address_list')


# ---------------------------------------------------------------------------
# Password management (Django's battle-tested views + custom templates)
# ---------------------------------------------------------------------------
class ChangePasswordView(auth_views.PasswordChangeView):
    template_name = 'accounts/password_change.html'
    form_class = ChangePasswordForm
    success_url = reverse_lazy('accounts:password_change_done')

    def form_valid(self, form):
        messages.success(self.request, 'Your password has been changed.')
        return super().form_valid(form)


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = 'accounts/password_change_done.html'


class PasswordResetView(auth_views.PasswordResetView):
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.txt'
    subject_template_name = 'accounts/password_reset_subject.txt'
    success_url = reverse_lazy('accounts:password_reset_done')
    extra_context = {'title': 'Password reset'}


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = 'accounts/password_reset_done.html'


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = 'accounts/password_reset_confirm.html'
    success_url = reverse_lazy('accounts:password_reset_complete')

    def get_form(self):
        form = super().get_form()
        for field in form.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
        return form


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = 'accounts/password_reset_complete.html'
