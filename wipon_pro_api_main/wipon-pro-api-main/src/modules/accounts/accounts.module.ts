import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AccountsRepository } from './data/accounts.repository';
import { AccountsService } from './domain/accounts.service';
import { UsersModule } from '../users/users.module';
import { AccountsController } from './presenter/accounts.controller';
import { UpdateUserAccountsLedgerUseCase } from './domain/use-cases/update-user-accounts-ledger.use-case';
import { SaveAccountsUseCase } from './domain/use-cases/save-accounts.use-case';
import { CountLedgerAccountsProvidersUseCase } from './domain/use-cases/count-ledger-accounts-providers.use-case';
import { FindUsersAccountsWithTransactionsUseCase } from './domain/use-cases/find-users-accounts-with-transactions.use-case';
import { SumLedgerAccountsBalanceUseCase } from './domain/use-cases/sum-ledger-accounts-balance.use-case';
import { FindLedgersAccountsUseCase } from './domain/use-cases/find-ledgers-accounts.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([AccountsRepository]), UsersModule],
  providers: [
    AccountsService,
    UpdateUserAccountsLedgerUseCase,
    SaveAccountsUseCase,
    CountLedgerAccountsProvidersUseCase,
    FindUsersAccountsWithTransactionsUseCase,
    SumLedgerAccountsBalanceUseCase,
    FindLedgersAccountsUseCase,
  ],
  controllers: [AccountsController],
  exports: [
    UpdateUserAccountsLedgerUseCase,
    SaveAccountsUseCase,
    CountLedgerAccountsProvidersUseCase,
    FindUsersAccountsWithTransactionsUseCase,
    SumLedgerAccountsBalanceUseCase,
    FindLedgersAccountsUseCase,
  ],
})
export class AccountsModule {}
