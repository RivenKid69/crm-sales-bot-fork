import { Injectable } from '@nestjs/common';
import { AccountsRepository } from '../../data/accounts.repository';
import { InjectRepository } from '@nestjs/typeorm';
import { AccountDao } from '../../../../common/dao/account.dao';

@Injectable()
export class FindLedgersAccountsUseCase {
  constructor(@InjectRepository(AccountsRepository) private readonly accountsRepo: AccountsRepository) {}

  handle(ledgerId: number | null, provider: string): Promise<AccountDao | undefined> {
    return this.accountsRepo.findOne({ where: { ledger_id: ledgerId, provider } });
  }
}
