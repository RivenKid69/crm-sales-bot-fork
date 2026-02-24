import { forwardRef, Module } from '@nestjs/common';
import { SubscriptionRepository } from './data/subscription.repository';
import { TypeOrmModule } from '@nestjs/typeorm';
import { CountUsersActiveSubscriptionUseCase } from './domain/use-cases/count-users-active-subscription.use-case';
import { SubscriptionsController } from './presenter/subscriptions.controller';
import { SubscriptionsService } from './domain/subscriptions.service';
import { UsersModule } from '../users/users.module';
import { FindUsersAllSubscriptionsUseCase } from './domain/use-cases/find-users-all-subscriptions.use-case';
import { PushService } from '../../common/services/push/push.service';
import { FindUsersActiveSubscriptionUseCase } from './domain/use-cases/find-users-active-subscription.use-case';
import { ActivateUsersSubscriptionUseCase } from './domain/use-cases/activate-users-subscription.use-case';
import { StoresModule } from '../stores/stores.module';
import { BullModule } from '@nestjs/bull';
import { PushProducerService } from '../../common/services/push/push.producer.service';
import { BillingService } from '../../common/services/billing/billing.service';
import { AccountsModule } from '../accounts/accounts.module';
import { HttpModule } from '@nestjs/axios';
import { DevicesModule } from '../devices/devices.module';
import { FindUsersAllDevicesByAtUseCase } from '../devices/domain/use-cases/find-users-all-devices-by-at.use-case';

@Module({
  imports: [
    TypeOrmModule.forFeature([SubscriptionRepository]),
    UsersModule,
    AccountsModule,
    HttpModule,
    DevicesModule,
    forwardRef(() => StoresModule),
    BullModule.registerQueue({
      name: 'push_pro',
    }),
  ],
  controllers: [SubscriptionsController],
  providers: [
    SubscriptionsService,
    CountUsersActiveSubscriptionUseCase,
    FindUsersAllSubscriptionsUseCase,
    PushService,
    FindUsersActiveSubscriptionUseCase,
    ActivateUsersSubscriptionUseCase,
    PushProducerService,
    BillingService,
  ],
  exports: [
    CountUsersActiveSubscriptionUseCase,
    FindUsersAllSubscriptionsUseCase,
    FindUsersActiveSubscriptionUseCase,
    ActivateUsersSubscriptionUseCase,
  ],
})
export class SubscriptionsModule {}
