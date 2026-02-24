import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { AccountsRepository } from '../data/accounts.repository';
import { FindUsersLedgerUseCase } from '../../users/domain/use-cases/find-users-ledger.use-case';
import { AccountDao } from '../../../common/dao/account.dao';
import { LedgerDao } from '../../../common/dao/ledger.dao';
import { UserDao } from '../../../common/dao/user.dao';

@Injectable()
export class AccountsService {
  constructor(
    @InjectRepository(AccountsRepository) private readonly accountsRepo: AccountsRepository,
    private readonly findUsersLedger: FindUsersLedgerUseCase,
  ) {}

  async getUsersAccounts(user: UserDao) {
    const ledger = await this.findUsersLedger.handle(user.id);
    if (!ledger) return [];
    return this.formatAccountsToResponse(ledger.accounts, ledger);
  }

  private formatAccountsToResponse(accounts: AccountDao[], ledger: LedgerDao) {
    return accounts.map((account) => {
      return {
        id: account.id,
        number: ledger.code,
        provider: account.provider,
        balance: account.balance,
      };
    });
  }
}
