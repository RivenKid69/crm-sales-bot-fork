import { Module } from '@nestjs/common';
import { LedgersService } from './domain/ledgers.service';
import { BillingService } from '../../common/services/billing/billing.service';
import { LedgersController } from './presenter/ledgers.controller';
import { UsersModule } from '../users/users.module';
import { AccountsModule } from '../accounts/accounts.module';

@Module({
  imports: [UsersModule, AccountsModule],
  providers: [LedgersService, BillingService],
  controllers: [LedgersController],
})
export class LedgersModule {}
