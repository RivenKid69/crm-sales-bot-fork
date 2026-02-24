import { Injectable } from '@nestjs/common';
import { AccountsRepository } from '../../data/accounts.repository';
import { InjectRepository } from '@nestjs/typeorm';
import { AccountDao } from '../../../../common/dao/account.dao';
import { EntityManager } from 'typeorm';

@Injectable()
export class SaveAccountsUseCase {
  constructor(@InjectRepository(AccountsRepository) private readonly accountsRepo: AccountsRepository) {}

  async handle(accounts: Array<AccountDao>, transaction: null | EntityManager = null): Promise<AccountDao[]> {
    if (!transaction) return await this.accountsRepo.save(accounts);
    else return await transaction.save(accounts);
  }
}
