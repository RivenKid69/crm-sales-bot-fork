import { HttpException, Injectable, InternalServerErrorException, NotFoundException } from '@nestjs/common';
import { FindUsersAccountsWithTransactionsUseCase } from '../../accounts/domain/use-cases/find-users-accounts-with-transactions.use-case';
import { GetUsersTransactionsDto } from '../dto/get-users-transactions.dto';
import { PostTransactionDto } from '../dto/post-transaction.dto';
import { FindUserByIdUseCase } from '../../users/domain/use-cases/find-user-by-id.use-case';
import { getManager } from 'typeorm';
import { BillingService } from '../../../common/services/billing/billing.service';
// import { FindLedgersAccountsUseCase } from '../../accounts/domain/use-cases/find-ledgers-accounts.use-case';
import { FindUsersAllSubscriptionsUseCase } from '../../subscriptions/domain/use-cases/find-users-all-subscriptions.use-case';
import { CountUsersActiveSubscriptionUseCase } from '../../subscriptions/domain/use-cases/count-users-active-subscription.use-case';
// import subscriptionConfig from '../../../config/subscription.config';
import { ActivateUsersSubscriptionUseCase } from '../../subscriptions/domain/use-cases/activate-users-subscription.use-case';
// import { SubscriptionDao } from '../../../common/dao/subscription.dao';
// import { addDays, getNowAlmatyTime } from '../../../common/helpers/datetime';
import createCustomErrorLogger from '../../../common/logger/error-logger';
import { SumLedgerAccountsBalanceUseCase } from '../../accounts/domain/use-cases/sum-ledger-accounts-balance.use-case';
import { PushService } from '../../../common/services/push/push.service';
import { FindUsersActiveSubscriptionUseCase } from '../../subscriptions/domain/use-cases/find-users-active-subscription.use-case';
import { I18nRequestScopeService } from 'nestjs-i18n';
import { UserDao } from '../../../common/dao/user.dao';
// import { SubscriptionChargeProducerService } from '../../../common/services/subscription/subscriptionCharge.producer.service';
import { LedgerDao } from '../../../common/dao/ledger.dao';
import { AccountDao } from '../../../common/dao/account.dao';
import { PostTransferDto } from '../dto/post-transfer.dto';
import { DateTime } from 'luxon';

@Injectable()
export class TransactionsService {
  constructor(
    private readonly findUsersAccountsWithTransactions: FindUsersAccountsWithTransactionsUseCase,
    private readonly findUserById: FindUserByIdUseCase,
    private readonly billingService: BillingService,
    // private readonly findLedgersAccounts: FindLedgersAccountsUseCase,
    private readonly findUsersAllSubs: FindUsersAllSubscriptionsUseCase,
    private readonly countUsersActiveSubs: CountUsersActiveSubscriptionUseCase,
    private readonly activateUsersSubscription: ActivateUsersSubscriptionUseCase,
    private readonly sumLedgerAccountsBalance: SumLedgerAccountsBalanceUseCase,
    private readonly pushService: PushService,
    private readonly findUsersActiveSub: FindUsersActiveSubscriptionUseCase,
    private readonly i18n: I18nRequestScopeService, // private readonly subscriptionChargeProducerService: SubscriptionChargeProducerService,
  ) {}

  async getUsersTransactions(user: UserDao, page, type, fullUrl: string) {
    const ledger = await LedgerDao.findOne({ where: { user_id: user.id } });
    if (!ledger) throw new NotFoundException({ message: 'User does not have ledger' });
    return await this.findUsersAccountsWithTransactions.handle(ledger.id, page, type, fullUrl);
  }

  async postTransfer(postTransferDto: PostTransferDto) {
    if (postTransferDto.from_user_id === postTransferDto.to_user_id)
      throw new HttpException({ to_user_id: ['The from user id and to user id are equal.'] }, 422);

    const fromUser = await this.findUserById.handle(postTransferDto.from_user_id);
    const toUser = await this.findUserById.handle(postTransferDto.to_user_id);
    if (!fromUser || !fromUser.ledger)
      throw new HttpException({ from_user_id: ['The selected from user id is invalid'] }, 422);

    if (!toUser || !toUser.ledger) throw new HttpException({ to_user_id: ['The selected to user id is invalid'] }, 422);

    const fromLedger = fromUser.ledger;
    const toLedger = toUser.ledger;
    const provider = 'wipon_transfer';
    const accountProvider = 'Wipon';

    postTransferDto.sum = Number(postTransferDto.sum);

    if (postTransferDto.sum <= 0) {
      throw new HttpException({ sum: ['Transfer sum can not be 0 or less than 0'] }, 422);
    }

    const isUserHasEnoughMoney = await this.billingService.capitalAdequacy(fromLedger, postTransferDto.sum);
    if (!isUserHasEnoughMoney)
      throw new HttpException({ sum: ['Selected user does not have enough money to transfer'] }, 422);

    try {
      await getManager().transaction('SERIALIZABLE', async (transactionalEntityManager) => {
        await this.billingService.createAccounts(fromUser, transactionalEntityManager);
        await this.billingService.createAccounts(toUser, transactionalEntityManager);

        const fromAccount = await transactionalEntityManager.findOne(AccountDao, {
          where: { ledger_id: fromLedger.id, provider: accountProvider },
        });

        const toAccount = await transactionalEntityManager.findOne(AccountDao, {
          where: { ledger_id: toLedger.id, provider: accountProvider },
        });

        if (!fromAccount || !toAccount) throw new HttpException({ account: ['Account not found'] }, 404);
        const currentAlmatyTimeInString = DateTime.now().setZone('Asia/Almaty').toString();

        const rawInfoFrom = postTransferDto.raw_info_from ? JSON.parse(postTransferDto.raw_info_from) : null;
        const rawInfoTo = postTransferDto.raw_info_to ? JSON.parse(postTransferDto.raw_info_to) : null;

        const formattedInfoFrom = rawInfoFrom
          ? { ...rawInfoFrom, created_at: currentAlmatyTimeInString }
          : { created_at: currentAlmatyTimeInString };
        const formattedInfoTo = rawInfoTo
          ? { ...rawInfoTo, created_at: currentAlmatyTimeInString }
          : { created_at: currentAlmatyTimeInString };

        const accountTransactionFrom = this.billingService.addTransaction(
          provider,
          fromAccount,
          -postTransferDto.sum,
          formattedInfoFrom,
          toLedger.id,
        );
        const accountTransactionTo = this.billingService.addTransaction(
          provider,
          toAccount,
          postTransferDto.sum,
          formattedInfoTo,
          fromLedger.id,
        );

        await transactionalEntityManager.save([accountTransactionFrom, accountTransactionTo]);

        const fromAllAccounts = await transactionalEntityManager.find(AccountDao, {
          where: { ledger_id: fromLedger.id },
        });

        let _sum = postTransferDto.sum;
        for (const acc of fromAllAccounts) {
          if (_sum == 0) break;
          if (acc.balance <= 0) continue;

          if (acc.balance < _sum) {
            _sum -= acc.balance;
            await transactionalEntityManager.update(AccountDao, acc.id, { balance: 0, updated_at: new Date() });
          } else {
            await transactionalEntityManager.update(AccountDao, acc.id, {
              balance: acc.balance - _sum,
              updated_at: new Date(),
            });
            _sum = 0;
          }
        }

        if (_sum != 0) {
          throw new Error('Error in charging user');
        }

        toAccount.balance = Number(toAccount.balance) + postTransferDto.sum;

        await transactionalEntityManager.save(toAccount);
      });
    } catch (e) {
      const errorLogger = createCustomErrorLogger();
      errorLogger.log('error', e);
      if (e instanceof HttpException) throw e;
      throw new InternalServerErrorException({ error: 'transfer error...' });
    }

    return {
      status: 'success',
    };
  }

  async postTransaction(postTransactionDto: PostTransactionDto) {
    postTransactionDto.amount = Number(postTransactionDto.amount);

    const user = await this.findUserById.handle(postTransactionDto.user_id);
    if (!user) throw new HttpException({ user_id: ['The selected user id is invalid'] }, 404);

    let isActivated;
    let activeSubs;

    try {
      await getManager().transaction('SERIALIZABLE', async (transactionalEntityManager) => {
        await this.billingService.createAccounts(user, transactionalEntityManager);
        const accountProvider = postTransactionDto.account ? postTransactionDto.account : 'Wipon';
        // const account = await this.findLedgersAccounts.handle(user.ledger.id, accountProvider);
        const account = await transactionalEntityManager.findOne(AccountDao, {
          where: { ledger_id: user.ledger.id, provider: accountProvider },
        });

        if (!account) throw new HttpException({ account: ['Account not found'] }, 404);

        const rawInfo = postTransactionDto.raw_info ? JSON.parse(postTransactionDto.raw_info) : null;
        const createdAt = postTransactionDto.timestamp
          ? new Date(postTransactionDto.timestamp)
          : DateTime.now().setZone('Asia/Almaty').toString();

        const formattedInfo = rawInfo ? { ...rawInfo, created_at: createdAt } : { created_at: createdAt };

        const accountTransaction = this.billingService.addTransaction(
          postTransactionDto.provider,
          account,
          postTransactionDto.amount,
          formattedInfo,
          postTransactionDto.contracter_id,
        );

        await transactionalEntityManager.save(accountTransaction);

        account.balance = Number(account.balance) + Number(postTransactionDto.amount);
        await transactionalEntityManager.save(account);
        if (
          postTransactionDto.provider == 'wipon_transfer' &&
          postTransactionDto.amount > 0 &&
          rawInfo.type &&
          rawInfo.type == 'refund'
        ) {
          // если был возврат средств, деактивируем подписку и назначим попытку активации через пять минут
          const subscriptions = await this.findUsersAllSubs.handle(user.id);
          subscriptions.forEach((sub) => (sub.is_active = false));
          await transactionalEntityManager.save(subscriptions);
          // await this.subscriptionChargeProducerService.sendBilling(user.id);
        } else if (postTransactionDto.amount > 0) {
          // let isYear = false;
          // activeSubs = await this.countUsersActiveSubs.handle(user.id);
          // isActivated = !!activeSubs;
          // if (!activeSubs) {
          //   const isUserCharged = await this.billingService.chargeUser(
          //     transactionalEntityManager,
          //     user,
          //     subscriptionConfig.cost,
          //     {
          //       subscription_for: new Date(),
          //     },
          //   );
          //   if (isUserCharged) {
          //     isActivated = await this.activateUsersSubscription.handle(
          //       user,
          //       subscriptionConfig.lifetime,
          //       transactionalEntityManager,
          //     );
          //     isYear = true;
          //   }
          // }
          // if (postTransactionDto.timestamp && !activeSubs && isActivated) {
          //   const createdTime = new Date(postTransactionDto.timestamp);
          //   const expiresTime = addDays(
          //     getNowAlmatyTime(postTransactionDto.timestamp),
          //     isYear ? subscriptionConfig.lifetime + 1 : subscriptionConfig.quarter_lifetime + 1,
          //   );
          //
          //   await transactionalEntityManager.update(
          //     SubscriptionDao,
          //     { deleted_at: null, user_id: user.id, is_active: true },
          //     { created_at: createdTime, expires_at: expiresTime },
          //   );
          // }
        }
      });
    } catch (e) {
      const errorLogger = createCustomErrorLogger();
      errorLogger.log('error', e);
      throw new InternalServerErrorException({ error: 'internal server error' });
    }

    if (
      postTransactionDto.amount > 0 &&
      postTransactionDto.provider !== 'Wipon' &&
      postTransactionDto.provider !== 'wipon_transfer'
    ) {
      const totalBalance = await this.sumLedgerAccountsBalance.handle(user.ledger.id);
      const msg = await this.i18n.translate('messages.billing_paid', {
        args: {
          sum: postTransactionDto.amount,
          total_balance: totalBalance,
        },
      });
      await this.pushService.send(user, msg);
      //
      //   if (isActivated) {
      //     const subscription = await this.findUsersActiveSub.handle(user.id);
      //     if (subscription) {
      //       const newStartAt = subscription.expires_at;
      //       const newExpiresAt = addDays(subscription.expires_at, subscriptionConfig.lifetime);
      //       const isCapitalAdequacy = await this.billingService.capitalAdequacy(user.ledger, subscriptionConfig.cost);
      //       if (isCapitalAdequacy) {
      //         const pushMsg = await this.i18n.translate('messages.billing_paid_continue', {
      //           args: {
      //             current_start_at: subscription.created_at.toLocaleDateString('kk-KK'),
      //             current_expires_at: subscription.expires_at.toLocaleDateString('kk-KK'),
      //             new_start_at: newStartAt.toLocaleDateString('kk-KK'),
      //             new_expires_at: newExpiresAt.toLocaleDateString('kk-KK'),
      //           },
      //         });
      //         await this.pushService.send(user, pushMsg);
      //       } else if (activeSubs) {
      //         const notPaidMsg = await this.i18n.translate('messages.billing_paid_not_continue', {
      //           args: {
      //             current_start_at: subscription.created_at.toLocaleDateString('kk-KK'),
      //             current_expires_at: subscription.expires_at.toLocaleDateString('kk-KK'),
      //             new_start_at: newStartAt.toLocaleDateString('kk-KK'),
      //             new_expires_at: newExpiresAt.toLocaleDateString('kk-KK'),
      //             required_sum: subscriptionConfig.cost,
      //           },
      //         });
      //         await this.pushService.send(user, notPaidMsg);
      //       }
    }
    //   } else {
    //     const msg = await this.i18n.translate('messages.subscription_not_activated', {
    //       args: {
    //         required_sum: subscriptionConfig.cost - totalBalance,
    //         cost: subscriptionConfig.cost,
    //       },
    //     });
    //     await this.pushService.send(user, msg);
    //   }
    // }

    return {
      status: 'success',
    };
  }
}
