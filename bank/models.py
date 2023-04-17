from django.db import models
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.base_user import AbstractBaseUser
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(_('електронна адреса'), unique=True)
    phone_number = models.CharField(_('номер телефону'), max_length=13, unique=True)
    first_name = models.CharField(_("ім'я"), max_length=30, blank=True)
    last_name = models.CharField(_('прізвище'), max_length=30, blank=True)
    patronymic = models.CharField(_('по-батькові'), max_length=30, blank=True)
    date_joined = models.DateTimeField(_('дата і час приєднання'), auto_now_add=True, editable=True)
    is_staff = models.BooleanField(_('суперкористувач'), default=False)
    is_active = models.BooleanField(_('активний'), default=True)
    verification_code = models.CharField(_('код підтвердження електронної адреси'), null=True, default=None, max_length=128, blank=True)
    password_reset_code = models.CharField(_('код скидання паролю'), null=True, default=None, max_length=128, blank=True)
    password_reset_request_time = models.DateTimeField(_('дата і час запиту на скидання паролю'), null=True, editable=True, blank=True)
    two_step_login = models.BooleanField(_('двоетапний вхід'), default=False)
    second_step_code = models.CharField(_('код підтвердження входу'), null=True, default=None, max_length=128, blank=True)
    confirm_operations = models.CharField(_('запитувати підтвердження важливих операцій'), max_length=4, default=120, null=False, blank=True)
    last_operation_confirmation_time = models.DateTimeField(_('дата і час останнього підтвердження операції'), null=True, editable=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['phone_number', 'first_name', 'last_name', 'patronymic']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')


class Card(models.Model):
    title = models.CharField(_('назва картки'), max_length=30, default='Картка')
    bank_account = models.BigIntegerField(_('банківський рахунок'), null=True)
    card_number = models.CharField(_('номер картки'), max_length=16, unique=True)
    expiry_date = models.CharField(_('термін дії'), max_length=5)
    payment_system = models.CharField(_('платіжна система'), choices=[('visa', 'Visa'), ('mastercard', 'Mastercard')],
                                      max_length=10)
    cvv = models.CharField(max_length=3)
    cardholder_name = models.CharField(_("ім'я власника картки"), max_length=30)
    cardholder_surname = models.CharField(_('прізвище власника картки'), max_length=30)
    cardholder_email = models.EmailField(_('електронна адреса власника картки'), null=True)
    color = models.CharField(_('колір картки'), choices=[('cyan', 'Бірюзовий'), ('yellow', 'Жовтий'),
                                                         ('green', 'Зелений'), ('orange', 'Помаранчевий'),
                                                         ('magenta', 'Пурпурний'), ('blue', 'Cиній'),
                                                         ('grey', 'Сірий'), ('purple', 'Фіолетовий'),
                                                         ('red', 'Червоний')],
                             max_length=9, default='blue')

    def __str__(self):
        return self.card_number

    def beautiful_number(self):
        num = self.card_number
        return num[0:4] + ' ' + num[4:8] + ' ' + num[8:12] + ' ' + num[12:16]

    class Meta:
        verbose_name = _('картка')
        verbose_name_plural = _('картки')


class BankAccount(models.Model):
    title = models.CharField(_("назва банківського рахунку"), max_length=30, default='Банківський рахунок')
    name = models.CharField(_("ім'я власника рахунку"), max_length=30)
    surname = models.CharField(_('прізвище власника рахунку'), max_length=30)
    patronymic = models.CharField(_('по-батькові власника рахунку'), max_length=30)
    iban = models.CharField(_('iban'), max_length=29, unique=True)
    currency = models.CharField(_('валюта'), max_length=3)
    balance = models.DecimalField(_('баланс'), max_digits=100, decimal_places=2)
    email = models.EmailField(_('електронна адреса'), null=True)

    def __str__(self):
        return self.iban

    def beautiful_iban(self):
        iban = self.iban
        return iban[0:4] + ' ' + iban[4:8] + ' ' + iban[8:12] + ' ' + iban[12:16] + ' ' + iban[16:20] + ' ' \
                         + iban[20:24] + ' ' + iban[24:28] + ' ' + iban[28]

    class Meta:
        verbose_name = _('банківський рахунок')
        verbose_name_plural = _('банківські рахунки')


class ExchangeRate(models.Model):
    date = models.DateField(_('дата'), unique=True, primary_key=True)
    rate = models.JSONField(_('курс обміну'))

    def __str__(self):
        return self.date.strftime("%d.%m.%Y")

    class Meta:
        verbose_name = _('курс обміну')
        verbose_name_plural = _('курси обміну')


class Transaction(models.Model):
    sender_bank_account = models.CharField(_('iban відправника'), max_length=29)
    receiver_bank_account = models.CharField(_('iban отримувача'), max_length=29)

    receiver_money = models.DecimalField(_('сума в валюті отримувача'), max_digits=100, decimal_places=2)
    sender_money = models.DecimalField(_('сума в валюті відправника'), max_digits=100, decimal_places=2)

    comment = models.CharField(_('коментар'), max_length=100)
    time = models.DateTimeField(_('час'), auto_now_add=True)

    showing_to_sender = models.BooleanField(_('Показується для відправника'), default=True)
    showing_to_receiver = models.BooleanField(_('Показується для отримувача'), default=True)

    def __str__(self):
        return self.time.strftime("%d.%m.%Y %H:%M")

    def short_comment(self):
        comment = self.comment
        if not comment:
            iban = self.sender_bank_account
            beautiful_iban = iban[0:4] + ' ' + iban[4:8] + ' ' + iban[8:12] + ' ' + iban[12:16] + ' ' + iban[16:20] \
                                       + ' ' + iban[20:24] + ' ' + iban[24:28] + ' ' + iban[28]
            return 'Переказ з рахунку ' + beautiful_iban
        elif len(comment) <= 50:
            return comment
        else:
            return comment[0:49]+'...'

    class Meta:
        verbose_name = _('транзакція')
        verbose_name_plural = _('транзакції')
