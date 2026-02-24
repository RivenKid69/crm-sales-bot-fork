import { Injectable } from '@nestjs/common';
import { AccountsRepository } from '../../data/accounts.repository';
import { InjectRepository } from '@nestjs/typeorm';
import { EntityManager, UpdateResult } from 'typeorm';
import { AccountDao } from '../../../../common/dao/account.dao';

@Injectable()
export class UpdateUserAccountsLedgerUseCase {
  constructor(@InjectRepository(AccountsRepository) private readonly accountsRepo: AccountsRepository) {}

  async handle(userId: number, ledgerId: number, transaction: null | EntityManager = null): Promise<UpdateResult> {
    if (!transaction) {
      return await this.accountsRepo.update({ user_id: userId }, { ledger_id: ledgerId });
    } else {
      return await transaction.update(AccountDao, { user_id: userId }, { ledger_id: ledgerId });
    }
  }
}
