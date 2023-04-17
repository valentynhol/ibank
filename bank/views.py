import decimal
import random
import datetime

import hashlib
import pytz
import requests

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.utils import IntegrityError
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponseRedirect, JsonResponse, Http404, HttpResponse
from django.core.mail import send_mail
from django.template.loader import get_template
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth import update_session_auth_hash

from .forms import LogInForm, SignUpForm, CardForm, BankAccountForm, ExchangeRateForm
from .models import Card, BankAccount, User, ExchangeRate, Transaction


def __confirm_operation(request):
    user = request.user
    if user.confirm_operations:
        context = {}
        if not user.last_operation_confirmation_time or \
                (datetime.datetime.now().astimezone(user.last_operation_confirmation_time.tzinfo) - user.last_operation_confirmation_time).total_seconds() > int(user.confirm_operations):

            if request.method == 'POST':
                if 'confirmation' in request.POST.keys():
                    if check_password(request.POST['password'], user.password):
                        user.last_operation_confirmation_time = datetime.datetime.now(pytz.UTC)
                        user.save()
                        return 'confirmed'
                    else:
                        context = {'error': 'Неправильний пароль!'}
                else:
                    return 'confirmed'

            return render(request, 'confirm_operation.html', context)
        else:
            return 'confirmed'
    else:
        return 'confirmed'


def __send_email(email, file, context, title):
    send_mail(
        title,
        get_template(f'mail/{file}.txt').render(context), 'ibank.gh.noreply@gmail.com', [email],
        html_message=get_template(f'mail/{file}.html').render(context)
    )


def __generate_card_num(payment_system):
    if payment_system == 'visa':
        card_num = '4'
    else:
        card_num = '5'

    for i in range(14):
        card_num += str(random.randint(1, 9))

    last_digit_sum = 0
    for digit in card_num:
        if int(digit) % 2 == 1:
            digit = str(int(digit)*2)
            digit = sum(map(int, [i for i in digit]))

        last_digit_sum += int(digit)

    last_digit = 10 - (last_digit_sum % 10)
    card_num += '0' if last_digit == 10 else str(last_digit)
    return card_num


def __generate_iban(ba_type):
    bi_num = '380982'
    ba = '00000'

    if ba_type == 'checking':
        ba += '2600'
    elif ba_type == 'deposit':
        ba += '2620'
    else:
        ba += '2640'

    for i in range(10):
        ba += str(random.randint(1, 9))

    iban_raw = int(bi_num + ba + '301000')

    control_sum = str(98 - (iban_raw - 97*(iban_raw//97)))

    iban = 'UA' + ('0'+control_sum if int(control_sum) <= 9 else control_sum) + bi_num + ba
    return iban


def __generate_code(length, uppercase=False):
    symbol_list = '1 2 3 4 5 6 7 8 9 0 A B C D E F G H I G K L M N O P Q R S T U V W X Y Z'.split(' ')

    if not uppercase:
        symbol_list.append('a b c d e f g h i j k l m n o p q r s t u v w x y z')

    return ''.join([random.choice(symbol_list) for _ in range(length)])


def user_signup(request):
    if not str(request.user) == 'AnonymousUser':
        return HttpResponseRedirect('/')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if request.POST['password1'] == request.POST['password2']:
            try:
                user = User.objects.get(email=request.POST['email'])
                if not user.is_active and (datetime.datetime.now().astimezone(user.date_joined.tzinfo) - user.date_joined).total_seconds() > 86400:
                    user.delete()

            except User.DoesNotExist:
                pass

            try:
                user = User.objects.create_user(email=request.POST['email'],
                                                password=request.POST['password1'],
                                                first_name=request.POST['first_name'],
                                                last_name=request.POST['last_name'],
                                                patronymic=request.POST['patronymic'],
                                                phone_number=request.POST['phone_number'],
                                                is_active=False)
                if user:
                    verification_code = __generate_code(6, True)
                    user.verification_code = make_password(verification_code)
                    user.save()
                    __send_email(user.email, 'email_verification',
                                 {'code': verification_code,
                                  'name': f'{user.first_name} {user.last_name}',
                                  'link': f'https://ibank-gh.herokuapp.com/email_verification/'
                                          f'{user.id}/{verification_code}'}, 'Активація акаунту')

                return render(request, 'email_verification.html', {'user_id': user.id})
            except IntegrityError as signup_error:
                request.session['error'] = \
                    'Ця електронна адреса вже використовується' \
                    if 'email' in str(signup_error) \
                    else 'Цей номер телефону вже використовується'
        else:
            request.session['error'] = 'Паролі не збігаються!'
    else:
        form = SignUpForm()

    try:
        error = request.session['error']
        del request.session['error']
    except KeyError:
        error = None

    context = {'form': form, 'error': error}
    return render(request, 'signup.html', context)


def user_login(request):
    if not str(request.user) == 'AnonymousUser':
        return HttpResponseRedirect('/')

    if request.method == 'POST':
        if 'second_step' in request.POST.keys():
            user = User.objects.get(id=request.POST['user_id'])

            if check_password(request.POST['code'], user.second_step_code):
                login(request, user)

                user.second_step_code = None
                user.save()

                return HttpResponse('logged_in')

            return HttpResponse('incorrect_code')
        else:
            form = LogInForm(request.POST)
            try:
                user = User.objects.get(email=request.POST['email'])
                if not user.is_active:
                    if (datetime.datetime.now().astimezone(user.date_joined.tzinfo) - user.date_joined).total_seconds() > 86400:
                        user.delete()
                        request.session['error'] = 'Неправильна електронна адреса або пароль!'
                    else:
                        request.session['error'] = 'Спочатку активуйте акаунт'
                else:
                    form = LogInForm(request.POST)
                    user_authenticated = authenticate(request, email=request.POST['email'],
                                                      password=request.POST['password'])

                    if user_authenticated:
                        if user.two_step_login:
                            code = __generate_code(6, True)

                            user.second_step_code = make_password(code)
                            user.save()

                            __send_email(user.email, 'second_step_login', {'code': code}, 'Підтвердження входу')

                            return render(request, 'second_step_login.html', {'user_id': user.id})
                        else:
                            login(request, user_authenticated)
                            return HttpResponseRedirect('/')
                    else:
                        request.session['error'] = 'Неправильна електронна адреса або пароль!'
            except User.DoesNotExist:
                request.session['error'] = 'Неправильна електронна адреса або пароль!'
    else:
        form = LogInForm()

    try:
        error = request.session['error']
        del request.session['error']
    except KeyError:
        error = None

    context = {'form': form, 'error': error}
    return render(request, 'login.html', context)


@login_required(redirect_field_name=None)
def user_logout(request):
    logout(request)
    return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def cards_and_bank_accounts(request):
    user = request.user

    raw_cards = Card.objects.all().filter(cardholder_email=user.email)
    raw_bas = BankAccount.objects.all().filter(email=user.email)

    cards = []
    for card in raw_cards:
        cards.append({'title': card.title, 'number': card.beautiful_number(), 'color': card.color,
                      'payment_system': card.payment_system, 'id': card.id})
    bas = []
    for ba in raw_bas:
        bas.append({'title': ba.title, 'currency': ba.currency, 'iban': ba.beautiful_iban(), 'id': ba.id,
                    'balance': ba.balance})

    try:
        error = request.session['error']
        del request.session['error']
    except KeyError:
        error = None
    try:
        success = request.session['success']
        del request.session['success']
    except KeyError:
        success = None

    return render(request, 'cards.html', {'cards': cards, 'bank_accounts': bas, 'error': error, 'success': success})


@login_required(redirect_field_name=None)
def create_card(request):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    if request.method == 'POST' and 'confirmation' not in request.POST.keys():
        for i in range(60):
            try:
                if len(request.POST['title']) <= 30:
                    title = request.POST['title']
                else:
                    title = request.POST['title'][0:29]

                card_number = __generate_card_num(request.POST['payment_system'])
                expiry_date = datetime.date(year=datetime.date.today().year+3,
                                            month=datetime.date.today().month,
                                            day=datetime.date.today().day).strftime('%m/%y')
                card = Card(title=title, color=request.POST['color'],
                            payment_system=request.POST['payment_system'],
                            card_number=card_number, cvv=''.join([str(random.randint(1, 9)) for _ in range(3)]),
                            bank_account=request.POST['bank_account'], expiry_date=expiry_date,
                            cardholder_name=user.first_name, cardholder_surname=user.last_name,
                            cardholder_email=user.email)
                card.save()
                return HttpResponseRedirect('/')
            except IntegrityError:
                pass
        request.session['error'] = 'Помилка створення карти'
        return HttpResponseRedirect('/')
    else:
        form = CardForm()
        bas = BankAccount.objects.all().filter(email=user.email)

        if bas:
            form.fields['bank_account'].choices += [(bank_account.id, bank_account.title) for bank_account in bas]

            try:
                error = request.session['error']
                del request.session['error']
            except KeyError:
                error = None
            try:
                success = request.session['success']
                del request.session['success']
            except KeyError:
                success = None

            context = {'form': form, 'error': error, 'success': success}
            return render(request, 'add_card.html', context)

        request.session['error'] = 'Спочатку потрібно створити рахунок'
        return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def create_ba(request):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    if request.method == 'POST' and 'confirmation' not in request.POST.keys():
        for i in range(60):
            try:
                if len(request.POST['title']) <= 30:
                    title = request.POST['title']
                else:
                    title = request.POST['title'][0:29]

                iban = __generate_iban('checking')
                ba = BankAccount(title=title, iban=iban, currency=request.POST['currency'], balance='0',
                                 name=user.first_name, surname=user.last_name, patronymic=user.patronymic,
                                 email=user.email)
                ba.save()
                return HttpResponseRedirect('/')
            except IntegrityError:
                pass
        request.session['error'] = 'Помилка створення рахункy'
        return HttpResponseRedirect('/')
    else:
        try:
            error = request.session['error']
            del request.session['error']
        except KeyError:
            error = None
        try:
            success = request.session['success']
            del request.session['success']
        except KeyError:
            success = None

        form = BankAccountForm()
        context = {'form': form, 'error': error, 'success': success}
        return render(request, 'add_bank_account.html', context)


@login_required(redirect_field_name=None)
def card_page(request, card_id):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    try:
        card = Card.objects.get(id=card_id)
    except Card.DoesNotExist:
        request.session['error'] = 'Такої карти не існує!'
        return HttpResponseRedirect('/')

    if user.email == card.cardholder_email:
        card_ba = BankAccount.objects.get(id=card.bank_account)

        try:
            error = request.session['error']
            del request.session['error']
        except KeyError:
            error = None
        try:
            success = request.session['success']
            del request.session['success']
        except KeyError:
            success = None

        context = {'error': error, 'success': success, 'balance': card_ba.balance,
                   'card': {'number': card.beautiful_number(), 'title': card.title,
                            'bank_account': card_ba.beautiful_iban(), 'ba_title': card_ba.title, 'color': card.color,
                            'payment_system': card.payment_system, 'expiry_date': card.expiry_date, 'id': card.id,
                            'cardholder': f'{card.cardholder_surname} {card.cardholder_name}', 'cvv': card.cvv,
                            'currency': card_ba.currency}}
        return render(request, 'card_page.html', context)
    else:
        request.session['error'] = 'Ви не є власником цієї картки!'
        return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def ba_page(request, ba_id):
    def sort_transactions(element):
        return element[0]

    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    try:
        ba = BankAccount.objects.get(id=ba_id)
    except BankAccount.DoesNotExist:
        request.session['error'] = 'Такого рахунку не існує!'
        return HttpResponseRedirect('/')

    if user.email == ba.email:
        try:
            error = request.session['error']
            del request.session['error']
        except KeyError:
            error = None
        try:
            success = request.session['success']
            del request.session['success']
        except KeyError:
            success = None

        income_transactions = Transaction.objects.all().filter(receiver_bank_account=ba.iban, showing_to_receiver=True)
        outcome_transactions = Transaction.objects.all().filter(sender_bank_account=ba.iban, showing_to_sender=True)
        transactions = []
        for income_transaction in income_transactions:
            transactions.append([income_transaction.time, income_transaction.short_comment(),
                                 income_transaction.receiver_money, 'income', income_transaction.id])
        for outcome_transaction in outcome_transactions:
            transactions.append([outcome_transaction.time, outcome_transaction.short_comment(),
                                 outcome_transaction.sender_money, 'outcome', outcome_transaction.id])

        transactions.sort(key=sort_transactions, reverse=True)

        context = {'error': error, 'success': success, 'transactions': transactions,
                   'ba': {'iban': ba.beautiful_iban(), 'title': ba.title, 'balance': ba.balance, 'id': ba_id,
                          'full_name': f'{ba.surname} {ba.name} {ba.patronymic}', 'currency': ba.currency}}
        return render(request, 'ba_page.html', context)
    else:
        request.session['error'] = 'Ви не є власником цього рахунку!'
        return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def edit_card(request, card_id):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    try:
        card = Card.objects.get(id=card_id)
    except Card.DoesNotExist:
        request.session['error'] = 'Такої карти не існує!'
        return HttpResponseRedirect('/')

    if user.email == card.cardholder_email:
        if request.method == 'POST' and 'confirmation' not in request.POST.keys():
            if len(request.POST['title']) <= 30:
                title = request.POST['title']
            else:
                title = request.POST['title'][0:29]

            if title.replace(' ', ''):
                card.title = title
                card.color = request.POST['color']
                card.save()

                request.session['success'] = 'Картку успішно змінено'
            else:
                request.session['error'] = 'Назва має містити символи крім пробілів'
            return HttpResponseRedirect('/cards/'+str(card_id))
        else:
            form = CardForm(initial={'color': card.color, 'title': card.title})

            try:
                error = request.session['error']
                del request.session['error']
            except KeyError:
                error = None
            try:
                success = request.session['success']
                del request.session['success']
            except KeyError:
                success = None

            context = {'form': form, 'error': error, 'success': success, 'card_title': card.title,
                       'card_id': card_id}
            return render(request, 'edit_card.html', context)
    else:
        request.session['error'] = 'Ви не є власником цієї картки!'
        return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def add_money(request, ba_id):
    user = request.user
    try:
        ba = BankAccount.objects.get(id=ba_id)
    except BankAccount.DoesNotExist:
        request.session['error'] = 'Такого рахунку не існує!'
        return HttpResponseRedirect('/')

    if user.email == ba.email:
        if request.method == 'POST':
            try:
                if int(request.POST['money']) < 0:
                    request.session['error'] = "Введена сума має бути додатньою!"
                    return HttpResponseRedirect('/bank_accounts/' + str(ba_id))
                elif int(request.POST['money']) > 10000:
                    request.session['error'] = "Введена сума має бути не більше 10000!"
                    return HttpResponseRedirect('/bank_accounts/' + str(ba_id))
                else:
                    ba.balance += decimal.Decimal(float(request.POST['money']))
                    ba.save()
                    request.session['success'] = 'Кошти успішно нараховано на рахунок'
                    return HttpResponseRedirect('/bank_accounts/' + str(ba_id))
            except ValueError:
                request.session['error'] = "Введено некоректні дані"
                return HttpResponseRedirect('/bank_accounts/' + str(ba_id))
        else:
            try:
                error = request.session['error']
                del request.session['error']
            except KeyError:
                error = None
            try:
                success = request.session['success']
                del request.session['success']
            except KeyError:
                success = None

            context = {'error': error, 'success': success, 'ba_title': ba.title, 'ba_id': ba_id}
            return render(request, 'add_money.html', context)
    else:
        request.session['error'] = 'Ви не є власником цього рахунку!'
        return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def withdraw_money(request, ba_id):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    try:
        ba = BankAccount.objects.get(id=ba_id)
    except BankAccount.DoesNotExist:
        request.session['error'] = 'Такого рахунку не існує!'
        return HttpResponseRedirect('/')

    if ba.balance < 50:
        request.session['error'] = "Недостатньо коштів на рахунку!"
        return HttpResponseRedirect('/bank_accounts/' + str(ba_id))

    if user.email == ba.email:
        if request.method == 'POST' and 'confirmation' not in request.POST.keys():
            try:
                if int(request.POST['money']) < 0:
                    request.session['error'] = "Введена сума має бути додатньою!"
                    return HttpResponseRedirect('/bank_accounts/' + str(ba_id))
                elif int(request.POST['money']) > float(ba.balance):
                    request.session['error'] = "Недостатньо коштів на рахунку!"
                    return HttpResponseRedirect('/bank_accounts/' + str(ba_id))
                else:
                    ba.balance -= decimal.Decimal(float(request.POST['money']))
                    ba.save()
                    request.session['success'] = 'Кошти успішно знято'
                    return HttpResponseRedirect('/bank_accounts/' + str(ba_id))
            except ValueError:
                request.session['error'] = "Введено некоректні дані"
                return HttpResponseRedirect('/bank_accounts/' + str(ba_id))
        else:
            try:
                error = request.session['error']
                del request.session['error']
            except KeyError:
                error = None
            try:
                success = request.session['success']
                del request.session['success']
            except KeyError:
                success = None

            context = {'error': error, 'success': success, 'ba_title': ba.title, 'ba_id': ba_id,
                       'max_money': int(ba.balance - (ba.balance % 100))}
            return render(request, 'withdraw_money.html', context)
    else:
        request.session['error'] = 'Ви не є власником цього рахунку!'
        return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def edit_ba(request, ba_id):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    try:
        ba = BankAccount.objects.get(id=ba_id)
    except BankAccount.DoesNotExist:
        request.session['error'] = 'Такого рахунку не існує!'
        return HttpResponseRedirect('/')

    if user.email == ba.email:
        if request.method == 'POST' and 'confirmation' not in request.POST.keys():
            if len(request.POST['title']) <= 30:
                title = request.POST['title']
            else:
                title = request.POST['title'][0:29]

            if title.replace(' ', ''):
                ba.title = title
                ba.save()

                request.session['success'] = 'Банківський рахунок успішно змінено'
            else:
                request.session['error'] = 'Назва має містити символи крім пробілів'
            return HttpResponseRedirect('/bank_accounts/'+str(ba_id))
        else:
            form = CardForm(initial={'title': ba.title})

            try:
                error = request.session['error']
                del request.session['error']
            except KeyError:
                error = None
            try:
                success = request.session['success']
                del request.session['success']
            except KeyError:
                success = None

            context = {'form': form, 'error': error, 'success': success, 'card_title': ba.title,
                       'ba_id': ba_id}
            return render(request, 'edit_ba.html', context)
    else:
        request.session['error'] = 'Ви не є власником цього рахунку!'
        return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def transfer_money(request, card_id):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    try:
        card = Card.objects.get(id=card_id)
    except Card.DoesNotExist:
        request.session['error'] = 'Такої картки не існує!'
        return HttpResponseRedirect('/')

    ba = BankAccount.objects.get(id=card.bank_account)

    if ba.balance < 10:
        request.session['error'] = "Недостатньо коштів на рахунку!"
        return HttpResponseRedirect('/cards/' + str(card_id))

    if user.email == card.cardholder_email:
        if request.method == 'POST' and 'confirmation' not in request.POST.keys():
            if 'confirm' in request.POST.keys():
                try:
                    recipient_ba = BankAccount.objects.get(id=request.session['recipient_ba'])

                except BankAccount.DoesNotExist:
                    request.session['error'] = 'Помилка переказу'
                    return HttpResponseRedirect('/')

                ba.balance -= decimal.Decimal(float(request.session['sender_money']))
                ba.save()

                recipient_ba.balance += decimal.Decimal(float(request.session['receiver_money']))
                recipient_ba.save()

                transaction = Transaction.objects.create(sender_bank_account=ba.iban,
                                                         comment=request.session['comment'],
                                                         receiver_bank_account=recipient_ba.iban,
                                                         receiver_money=float(request.session['receiver_money']),
                                                         sender_money=float(request.session['sender_money']))

                del request.session['receiver_money']
                del request.session['sender_money']
                del request.session['comment']
                request.session['success'] = 'Кошти успішно знято'
                return HttpResponseRedirect('/cards/' + str(card.id))
            elif 'number' in request.POST.keys():
                try:
                    card = Card.objects.get(card_number=request.POST['number'])
                    return HttpResponse(card.payment_system)
                except Card.DoesNotExist:
                    return HttpResponse()
            else:
                try:
                    recipient_card = Card.objects.get(card_number=request.POST['recipient_card'].replace(' ', ''))
                except Card.DoesNotExist:
                    request.session['error'] = 'Такої картки не існує!'
                    return HttpResponseRedirect(f'../transfer_money/{card_id}')

                recipient_ba = BankAccount.objects.get(id=recipient_card.bank_account)

                if ba.iban == recipient_ba.iban:
                    request.session['error'] = "Не можна переказати кошти на картку прив'язану до цього ж рахунку"
                    return HttpResponseRedirect('/cards/' + str(card.id))

                try:
                    if int(request.POST['money']) < 0:
                        request.session['error'] = "Введена сума має бути додатньою!"
                        return HttpResponseRedirect('/transfer_money/' + str(card.id))
                    elif int(request.POST['money']) > float(ba.balance):
                        request.session['error'] = "Недостатньо коштів на рахунку!"
                        return HttpResponseRedirect('/transfer_money/' + str(card.id))
                    else:
                        request.session['sender_money'] = request.POST['money']
                        if ba.currency == recipient_ba.currency:
                            request.session['receiver_money'] = request.POST['money']
                        else:
                            request.session['receiver_money'] = round(requests.get(f"https://api.exchangerate.host"
                                                                                   f"/convert?from={ba.currency}"
                                                                                   f"&to={recipient_ba.currency}"
                                                                                   f"&amount={request.POST['money']}")
                                                                      .json()['result'], 2)

                        request.session['comment'] = request.POST['comment']
                        request.session['recipient_ba'] = recipient_card.bank_account

                        return render(request, 'transfer_money_confirm.html',
                                      {'recipient': {'full_name': f"{recipient_card.cardholder_name} "
                                                                  f"{recipient_card.cardholder_surname}",
                                                     'iban': recipient_ba.beautiful_iban(),
                                                     'card': recipient_card.beautiful_number(),
                                                     'currency': recipient_ba.currency},
                                       'sender': {'full_name': f"{card.cardholder_name} "
                                                               f"{card.cardholder_surname}",
                                                  'iban': ba.beautiful_iban(),
                                                  'card': card.beautiful_number(),
                                                  'currency': ba.currency},
                                       'card_id': card_id,
                                       'receiver_money': request.session['receiver_money'],
                                       'sender_money': request.session['sender_money'],
                                       'msg': request.session['comment']})
                except ValueError:
                    request.session['error'] = "Введено некоректні дані"
                    return HttpResponseRedirect('/transfer_money/' + str(card.id))
        else:
            try:
                error = request.session['error']
                del request.session['error']
            except KeyError:
                error = None
            try:
                success = request.session['success']
                del request.session['success']
            except KeyError:
                success = None
            context = {'error': error, 'success': success, 'card_title': card.title, 'card_id': card_id,
                       'max_money': int(ba.balance - (ba.balance % 10)), 'card_currency': ba.currency}
            return render(request, 'transfer_money.html', context)
    else:
        request.session['error'] = 'Ви не є власником цього рахунку!'
        return HttpResponseRedirect('/')


@login_required(redirect_field_name=None)
def exchange_rate(request):
    current_date = datetime.date.today()
    if request.method == 'POST':
        inputted_date = request.POST['date'].split('-')
        date = datetime.date(year=int(inputted_date[0]), month=int(inputted_date[1]), day=int(inputted_date[2]))
        currency = request.POST['currency']
        form = ExchangeRateForm(request.POST)
    else:
        date = current_date
        currency = 'UAH'
        form = ExchangeRateForm()

    if current_date >= date >= datetime.date(year=current_date.year-4, month=current_date.month, day=current_date.day):
        try:
            er = ExchangeRate.objects.get(date=date).rate
        except ExchangeRate.DoesNotExist:
            er = requests.get(f'https://api.exchangerate.host/{date.strftime("%Y-%m-%d")}?base=UAH').json()['rates']
            er_created = ExchangeRate(date=date, rate=er)
            er_created.save()
    else:
        request.session['error'] = 'Зберігаються дані курсів валют тільки за 4 останні роки'
        er = None

    try:
        error = request.session['error']
        del request.session['error']
    except KeyError:
        error = None
    try:
        success = request.session['success']
        del request.session['success']
    except KeyError:
        success = None

    return render(request, 'exchange_rate.html', {'rate': round(er[currency], 3), 'date': date, 'error': error,
                                                  'form': form, 'success': success,
                                                  'date_input': {'value': date.strftime('%Y-%m-%d'),
                                                                 'min': datetime.date(
                                                                     year=current_date.year-4,
                                                                     month=current_date.month,
                                                                     day=current_date.day).strftime('%Y-%m-%d'),
                                                                 'max': current_date.strftime('%Y-%m-%d')}})


def period_exchange_rate(request):
    if request.method == 'POST':
        period = request.POST['period']
        days = 1 if period == 'day' else 7 if period == 'week' else 30

        form = ExchangeRateForm()

        current_date = datetime.date.today()

        date = current_date - datetime.timedelta(days=days-1)
        ers = []
        while date <= current_date:
            try:
                er = ExchangeRate.objects.get(date=date).rate
            except ExchangeRate.DoesNotExist:
                er = requests.get(f'https://api.exchangerate.host/{date.strftime("%Y-%m-%d")}?base=UAH').json()[
                    'rates']
                er_created = ExchangeRate(date=date, rate=er)
                er_created.save()
            ers.append((er, date.strftime('%d.%m.%Y')))

            date += datetime.timedelta(days=1)

        return JsonResponse({'date': current_date.strftime('%Y-%m-%d'), 'ers': ers,
                             'currencyDropdown': form.render(form.template_name_p)
                            .replace('<label for="id_currency">Currency:</label>', '')
                            .replace('this.parentNode.submit()', f"changeRate('period', this.value)")})
    else:
        raise Http404


@login_required(redirect_field_name=None)
def transaction_page(request, transaction_id):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    try:
        transaction = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        return HttpResponseRedirect('/')

    try:
        sender_ba = BankAccount.objects.get(iban=transaction.sender_bank_account)
    except BankAccount.DoesNotExist:
        transaction.delete()
        return HttpResponseRedirect('/')

    try:
        receiver_ba = BankAccount.objects.get(iban=transaction.receiver_bank_account)
    except BankAccount.DoesNotExist:
        transaction.delete()
        return HttpResponseRedirect('/')
    if sender_ba.email == receiver_ba.email:
        context = {'sender_money': transaction.sender_money, 'sender_currency': sender_ba.currency,
                   'receiver_money': transaction.receiver_money, 'receiver_currency': receiver_ba.currency,
                   'sender_iban': sender_ba.beautiful_iban(), 'receiver_iban': receiver_ba.beautiful_iban(),
                   'msg': transaction.comment, 'in_account': True}

    elif user.email == sender_ba.email:
        context = {'receiver': receiver_ba.surname + ' ' + receiver_ba.name + ' ' + receiver_ba.patronymic,
                   'sender_money': transaction.sender_money, 'sender_currency': sender_ba.currency,
                   'sender_iban': sender_ba.beautiful_iban(), 'receiver_iban': receiver_ba.beautiful_iban(),
                   'msg': transaction.comment, 'outcome': True}

    elif user.email == receiver_ba.email:
        context = {'sender': sender_ba.surname + ' ' + sender_ba.name + ' ' + sender_ba.patronymic,
                   'receiver_money': transaction.receiver_money, 'receiver_currency': receiver_ba.currency,
                   'sender_iban': sender_ba.beautiful_iban(), 'receiver_iban': receiver_ba.beautiful_iban(),
                   'msg': transaction.comment, 'income': True}

    else:
        raise Http404

    return render(request, 'transaction.html', context)


@login_required(redirect_field_name=None)
def all_transactions(request):
    def sort_transactions(element):
        return element['time']

    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user

    bas = BankAccount.objects.all().filter(email=user.email)

    transactions = []

    for ba in bas:
        income_transactions = Transaction.objects.all().filter(receiver_bank_account=ba.iban, showing_to_receiver=True)
        outcome_transactions = Transaction.objects.all().filter(sender_bank_account=ba.iban, showing_to_sender=True)
        for income_transaction in income_transactions:
            receiver = BankAccount.objects.get(iban=income_transaction.receiver_bank_account)
            sender = BankAccount.objects.get(iban=income_transaction.sender_bank_account)

            if receiver.email == sender.email:
                transactions.append(
                    {'time': income_transaction.time, 'comment': income_transaction.short_comment(),
                     'money': income_transaction.receiver_money, 'type': 'in-acccount',
                     'id': income_transaction.id, 'currency': ba.currency})
            else:
                transactions.append(
                    {'time': income_transaction.time, 'comment': income_transaction.short_comment(),
                     'money': income_transaction.receiver_money, 'type': 'income',
                     'id': income_transaction.id, 'currency': ba.currency})
        for outcome_transaction in outcome_transactions:
            receiver = BankAccount.objects.get(iban=outcome_transaction.receiver_bank_account)
            sender = BankAccount.objects.get(iban=outcome_transaction.sender_bank_account)

            if not receiver.email == sender.email:
                transactions.append(
                    {'time': outcome_transaction.time, 'comment': outcome_transaction.short_comment(),
                     'money': outcome_transaction.receiver_money, 'type': 'outcome',
                     'id': outcome_transaction.id, 'currency': ba.currency})
    transactions.sort(key=sort_transactions, reverse=True)

    return render(request, 'all_transactions.html', {'transactions': transactions})


@login_required(redirect_field_name=None)
def settings(request):
    confirm_operation = __confirm_operation(request)
    if not confirm_operation == 'confirmed':
        return confirm_operation

    user = request.user
    if request.method == 'POST':
        context = {}
        if request.POST['type'] == 'personal_info':
            user.first_name = request.POST['name']
            user.last_name = request.POST['lastname']
            user.patronymic = request.POST['patronymic']
            user.save()
            context = {'success': 'ПІБ успішно змінено'}

        elif request.POST['type'] == 'change_password':
            if check_password(request.POST['current_password'], user.password):
                if request.POST['new_password1'] == request.POST['new_password2']:
                    if request.POST['new_password1'] and request.POST['new_password2'] and request.POST['current_password']:
                        user.set_password(request.POST['new_password1'])
                        update_session_auth_hash(request, request.user)
                        user.save()
                        context = {'success': 'Пароль успішно змінено'}
                    else:
                        return render(request, 'reset_password.html', {'error': 'Пароль має мати хоч один символ!'})
                else:
                    context = {'error': 'Нові паролі не збігаються!'}
            else:
                context = {'error': 'Неправильний пароль!'}

        elif request.POST['type'] == '2_step_login':
            if request.POST['value'] == 'true':
                value = True
            else:
                value = False

            user.two_step_login = value
            user.save()

            return HttpResponse()

        elif request.POST['type'] == 'confirm_operations':
            if request.POST['value'] in ['0', '30', '60', '120', '300', '600', '']:
                user.confirm_operations = request.POST['value']
                user.save()

            return HttpResponse()

        elif request.POST['type'] == 'set_custom_time':
            if str(request.POST['minutes']).isdigit() and str(request.POST['seconds']).isdigit():
                if int(request.POST['minutes']) >= 0 and int(request.POST['minutes']) >= 0:
                    value = int(request.POST['minutes'])*60 + int(request.POST['seconds'])

                    if 0 <= value <= 1800:
                        user.confirm_operations = str(value)
                        user.save()

            context = {}

    else:
        context = {}

    if user.confirm_operations not in ["0", "30", "60", "120", "300", "600", ""]:
        confirm_operations_custom = str(int(user.confirm_operations) // 60) + 'хв ' + \
                                    str(int(user.confirm_operations) % 60) + 'с'
    else:
        confirm_operations_custom = ''

    context.update({'name': user.first_name, 'last_name': user.last_name, 'patronymic': user.patronymic,
                    '2_step_login': user.two_step_login, 'confirm_operations': user.confirm_operations,
                    'confirm_operations_custom': confirm_operations_custom})

    return render(request, 'settings.html', context)


def email_verification(request, user_id, verification_code):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise Http404

    if not user.is_active and (datetime.datetime.now().astimezone(user.date_joined.tzinfo) - user.date_joined).total_seconds() > 86400:
        user.delete()

    elif not user.is_active and check_password(verification_code, user.verification_code):
        user.is_active = True
        user.verification_code = None
        user.save()
        return render(request, 'email_verification_successful.html', {'email': user.email})

    raise Http404


def email_verification_with_code(request):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=request.POST['user_id'])
        except User.DoesNotExist:
            return HttpResponse('user_does_not_exist')

        if not user.is_active and (datetime.datetime.now().astimezone(user.date_joined.tzinfo) - user.date_joined).total_seconds() > 86400:
            user.delete()
            return HttpResponse('code_has_expired')

        elif not user.is_active and check_password(request.POST['verification_code'], user.verification_code):
            user.is_active = True
            user.verification_code = None
            user.save()
            return HttpResponse('verified')

        elif user.is_active:
            return HttpResponse('already_verified')

        return HttpResponse('incorrect_code')
    else:
        raise Http404


def send_password_reset_email(request):
    email_sent = False
    error = None
    if request.method == 'POST':
        try:
            user = User.objects.get(email=request.POST['email'])

            password_reset_code = hashlib.sha256(bytes(user.email +
                                                str(datetime.datetime.timestamp(datetime.datetime.now())) +
                                                'adjwod', 'UTF-8')).hexdigest()

            user.password_reset_code = password_reset_code
            user.password_reset_request_time = datetime.datetime.now(pytz.UTC)
            user.save()

            __send_email(user.email, 'reset_password',
                         {'link': f'https://ibank-gh.herokuapp.com/reset_password/{password_reset_code}'},
                         'Скидання пароля')

            email_sent = True

        except User.DoesNotExist:
            error = 'За цією електронною адресою не зареєстровано користувача.'

    return render(request, 'send_password_reset_email.html', {'email_sent': email_sent, 'error': error})


def reset_password(request, code):
    try:
        user = User.objects.get(password_reset_code=code)
    except User.DoesNotExist:
        raise Http404
    if user.password_reset_request_time:
        if (datetime.datetime.now().astimezone(user.password_reset_request_time.tzinfo) - user.password_reset_request_time).total_seconds() > 300:
            user.password_reset_request_time = None
            user.password_reset_code = None
            user.save()

        elif code == user.password_reset_code:
            if request.method == 'POST':
                if request.POST['password1'] == request.POST['password2']:
                    if request.POST['password1'] and request.POST['password2']:
                        user.set_password(request.POST['password1'])
                        update_session_auth_hash(request, request.user)
                        user.password_reset_request_time = None
                        user.password_reset_code = None
                        user.save()
                        return HttpResponseRedirect('/')
                    else:
                        return render(request, 'reset_password.html', {'error': 'Пароль має мати хоч один символ!'})
                else:
                    return render(request, 'reset_password.html', {'error': 'Паролі не співпадають!'})
            else:
                return render(request, 'reset_password.html', {})
    raise Http404
