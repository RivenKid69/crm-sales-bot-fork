import { HttpException, Injectable } from '@nestjs/common';
import { LedgerDao } from '../../dao/ledger.dao';
import { LedgerChronicDao } from '../../dao/ledger-chronic.dao';
import { EntityManager, getConnection, IsNull } from 'typeorm';
import { greaterThan } from '../../helpers/datetime';
import { UpdateUserAccountsLedgerUseCase } from '../../../modules/accounts/domain/use-cases/update-user-accounts-ledger.use-case';
import { CountLedgerAccountsProvidersUseCase } from '../../../modules/accounts/domain/use-cases/count-ledger-accounts-providers.use-case';
import { AccountDao } from '../../dao/account.dao';
import { SaveAccountsUseCase } from '../../../modules/accounts/domain/use-cases/save-accounts.use-case';
import { AccountTransactionDao } from '../../dao/account-transaction.dao';
import { SumLedgerAccountsBalanceUseCase } from '../../../modules/accounts/domain/use-cases/sum-ledger-accounts-balance.use-case';
import { UserDao } from '../../dao/user.dao';
import { DateTime } from 'luxon';

@Injectable()
export class BillingService {
  constructor(
    private readonly updatedUserAccountsLedger: UpdateUserAccountsLedgerUseCase,
    private readonly countLedgerAccountsProviders: CountLedgerAccountsProvidersUseCase,
    private readonly saveAccounts: SaveAccountsUseCase,
    private readonly sumLedgerAccountsBalance: SumLedgerAccountsBalanceUseCase,
  ) {}

  async createAccounts(user: UserDao, transaction: null | EntityManager = null) {
    let ledger = user.ledger;
    if (!ledger) {
      const code = await this.generateLedgerCode();
      ledger = LedgerDao.create({ code, user_id: user.id, created_at: new Date() });
      if (!transaction) {
        ledger = await LedgerDao.save(ledger);
      } else {
        ledger = await transaction.save(ledger);
      }
    }

    const ledgerChronicsCount = await LedgerChronicDao.count({
      where: { ledger_id: ledger.id, user_id: user.id, finished_at: IsNull() },
    });

    if (!ledgerChronicsCount) {
      const beginningOfTimes = new Date(2017, 9, 1);
      const startedAt = greaterThan(user.created_at, beginningOfTimes) ? user.created_at : beginningOfTimes;
      const ledgerChronic = LedgerChronicDao.create({ ledger_id: ledger.id, user_id: user.id, started_at: startedAt });
      if (!transaction) {
        await LedgerChronicDao.save(ledgerChronic);
      } else {
        await transaction.save(ledgerChronic);
      }
    }

    await this.updatedUserAccountsLedger.handle(user.id, ledger.id, transaction);

    const qiwiOperatorsCount = await this.countLedgerAccountsProviders.handle(ledger.id, 'qiwi');
    const kassa24OperatorsCount = await this.countLedgerAccountsProviders.handle(ledger.id, 'kassa24');
    const cyberplatOperatorsCount = await this.countLedgerAccountsProviders.handle(ledger.id, 'cyberplat');
    const kaspiOperatorsCount = await this.countLedgerAccountsProviders.handle(ledger.id, 'kaspi');
    const bankOperatorsCount = await this.countLedgerAccountsProviders.handle(ledger.id, 'bank');
    const wiponOperatorsCount = await this.countLedgerAccountsProviders.handle(ledger.id, 'Wipon');
    const wooppayOperatorsCount = await this.countLedgerAccountsProviders.handle(ledger.id, 'wooppay');
    const alfabankOperatorsCount = await this.countLedgerAccountsProviders.handle(ledger.id, 'alfabank');

    const accounts: Array<AccountDao> = [];

    const operatorsCount = [
      { name: 'qiwi', count: qiwiOperatorsCount },
      { name: 'kaspi', count: kaspiOperatorsCount },
      { name: 'cyberplat', count: cyberplatOperatorsCount },
      { name: 'kassa24', count: kassa24OperatorsCount },
      { name: 'bank', count: bankOperatorsCount },
      { name: 'Wipon', count: wiponOperatorsCount },
      { name: 'wooppay', count: wooppayOperatorsCount },
      { name: 'alfabank', count: alfabankOperatorsCount },
    ];

    operatorsCount.forEach((operator) => {
      if (!operator.count) {
        // eslint-disable-next-line @typescript-eslint/ban-ts-comment
        // @ts-ignore
        // TypeScript тупит... не видит, что ledger не может быть undefined, поэтому стоит ts ignore
        accounts.push(this.createWalletAccount(ledger.id, operator.name));
      }
    });

    if (accounts.length) {
      await this.saveAccounts.handle(accounts, transaction);
    }
  }

  async capitalAdequacy(ledger: LedgerDao, sum: number, transactionalEntityManager: EntityManager | null = null) {
    if (!transactionalEntityManager) {
      const accountsBalanceSum = await this.sumLedgerAccountsBalance.handle(ledger.id);
      return accountsBalanceSum >= sum;
    }

    const rawResult = await transactionalEntityManager.query(
      'SELECT SUM(balance) as sum from accounts where ledger_id = $1',
      [ledger.id],
    );
    const totalSum = rawResult[0]?.sum;
    return totalSum >= sum;
  }

  // Возврат средств
  async makeRefund(transactionalEntityManager: EntityManager, user: UserDao, sum: number, rawInfo: any = {}) {
    const ledger = await transactionalEntityManager.findOne(LedgerDao, {
      where: { user_id: user.id },
      relations: ['accounts'],
    });

    if (!ledger) {
      throw new HttpException({ ledger: ['Users ledger not found'] }, 404);
    }

    const account = ledger.accounts.find((acc) => acc.provider === 'Wipon');
    if (!account) throw new HttpException({ message: 'Users account not found' }, 404);
    account.balance = Number(account.balance) + Number(sum);
    account.updated_at = new Date();
    await transactionalEntityManager.save(account);
    const accountTransaction = this.addTransaction('Wipon', account, sum, rawInfo);
    await transactionalEntityManager.save(accountTransaction);
  }

  // Снятие суммы со счетов
  async chargeUser(transactionalEntityManager: EntityManager, user: UserDao, sum: number, rawInfo: any = {}) {
    const ledger = await transactionalEntityManager.findOne(LedgerDao, {
      where: { user_id: user.id },
      relations: ['accounts'],
    });

    if (!ledger) {
      throw new HttpException({ ledger: ['Users ledger not found'] }, 404);
    }

    const isUserHasEnoughMoney = await this.capitalAdequacy(ledger, sum, transactionalEntityManager);
    if (!isUserHasEnoughMoney) return false;

    let _sum = sum;
    const accounts = ledger.accounts;

    try {
      for (const acc of accounts) {
        if (_sum == 0) break;
        if (acc.balance <= 0) continue;

        if (acc.balance < _sum) {
          _sum -= acc.balance;
          const accountTransaction = this.addTransaction('Wipon', acc, -acc.balance, rawInfo);
          await transactionalEntityManager.save(accountTransaction);
          await transactionalEntityManager.update(AccountDao, acc.id, { balance: 0, updated_at: new Date() });
        } else {
          const accountTransaction = this.addTransaction('Wipon', acc, -_sum, rawInfo);
          await transactionalEntityManager.save(accountTransaction);
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
    } catch (e) {
      if (e?.message === 'Error in charging user') {
        return false;
      } else {
        throw e;
      }
    }

    return _sum == 0;
  }

  addTransaction(
    provider: string,
    account: AccountDao,
    sum: number,
    rawInfo: any = {},
    contracterId: null | number = null,
  ): AccountTransactionDao {
    let createdAt = new Date();
    let txnId: any = null;
    if (provider == 'qiwi' || provider == 'kaspi') {
      txnId = rawInfo.txn_id ? rawInfo.txn_id : null;
      createdAt = rawInfo.txn_date ? DateTime.fromFormat(rawInfo.txn_date, 'yMMddHHmmss').toJSDate() : new Date();
    } else if (provider == 'kassa24' || provider == 'cyberplat') {
      txnId = rawInfo.receipt ? rawInfo.receipt : null;
      createdAt = rawInfo.date ? new Date(rawInfo.date) : new Date();
    } else if (provider == 'wooppay' || provider == 'alfabank') {
      txnId = rawInfo.txn_id ? rawInfo.txn_id : null;
    }

    if (rawInfo.created_at) {
      createdAt = rawInfo.created_at;
    }

    const accountTransaction = new AccountTransactionDao();
    accountTransaction.account_id = account.id;
    accountTransaction.provider = provider;
    accountTransaction.txn_id = txnId;
    accountTransaction.sum = sum;
    accountTransaction.raw_info = rawInfo;
    accountTransaction.created_at = createdAt;
    accountTransaction.updated_at = new Date();
    accountTransaction.contracter_id = contracterId;

    return accountTransaction;
  }

  async generateLedgerCode() {
    let result = '7';
    do {
      result = this.rand(0, 9);
    } while (result === '7');

    for (let i = 0; i < 9; i++) {
      result += this.rand(0, 9);
    }

    const isLedgerExists = await LedgerDao.findOne({ where: { code: result } });
    if (isLedgerExists) await this.generateLedgerCode();
    return result;
  }

  private createWalletAccount(ledgerId: number, provider: string) {
    const account = new AccountDao();
    account.ledger_id = ledgerId;
    account.provider = provider;
    account.created_at = new Date();
    account.updated_at = new Date();
    return account;
  }

  private rand(min: number, max: number): string {
    let result: number;
    if (min == 0) {
      result = Math.floor(Math.random() * max + 0);
    } else {
      result = Math.floor(Math.random() * (max - min + 1)) + min;
    }
    return String(result);
  }
}
