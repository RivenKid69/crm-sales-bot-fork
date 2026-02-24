import { Injectable } from '@nestjs/common';
import { AccountsRepository } from '../../data/accounts.repository';
import { InjectRepository } from '@nestjs/typeorm';

@Injectable()
export class SumLedgerAccountsBalanceUseCase {
  constructor(@InjectRepository(AccountsRepository) private readonly accountsRepo: AccountsRepository) {}

  async handle(ledgerId: number): Promise<number> {
    const { sum } = await this.accountsRepo
      .createQueryBuilder('account')
      .where('ledger_id = :ledgerId', { ledgerId })
      .select('SUM(account.balance)', 'sum')
      .getRawOne();
    return sum;
  }
}
