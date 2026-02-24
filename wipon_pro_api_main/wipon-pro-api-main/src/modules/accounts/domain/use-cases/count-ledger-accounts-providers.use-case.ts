import { Injectable } from '@nestjs/common';
import { AccountsRepository } from '../../data/accounts.repository';
import { InjectRepository } from '@nestjs/typeorm';

@Injectable()
export class CountLedgerAccountsProvidersUseCase {
  constructor(@InjectRepository(AccountsRepository) private readonly accountsRepo: AccountsRepository) {}

  async handle(ledgerId: number, providerName: string): Promise<number> {
    return await this.accountsRepo.count({ where: { ledger_id: ledgerId, provider: providerName } });
  }
}
