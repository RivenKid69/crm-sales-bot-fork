import { Module } from '@nestjs/common';
import { TransactionsController } from './presenter/transactions.controller';
import { TransactionsService } from './domain/transactions.service';
import { UsersModule } from '../users/users.module';
import { AccountsModule } from '../accounts/accounts.module';
import { BillingService } from '../../common/services/billing/billing.service';
import { SubscriptionsModule } from '../subscriptions/subscriptions.module';
import { FcmModule } from '../fcm/fcm.module';
import { PushService } from '../../common/services/push/push.service';
import { SubscriptionChargeProducerService } from '../../common/services/subscription/subscriptionCharge.producer.service';
import { BullModule } from '@nestjs/bull';
import { SubscriptionChargeConsumer } from '../../common/services/consumer/subscriptionCharge.consumer';

@Module({
  providers: [
    TransactionsService,
    BillingService,
    PushService,
    SubscriptionChargeProducerService,
    SubscriptionChargeConsumer,
  ],
  controllers: [TransactionsController],
  imports: [
    UsersModule,
    AccountsModule,
    SubscriptionsModule,
    FcmModule,
    BullModule.registerQueue({ name: 'billing_pro' }),
  ],
})
export class TransactionsModule {}
