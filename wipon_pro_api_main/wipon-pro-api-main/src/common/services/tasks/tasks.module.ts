import { CacheModule, Module } from '@nestjs/common';
import { TasksService } from './tasks.service';
import { SendPushToExpiringSubsTask } from './send-push-to-expiring-subs.task';
import { PushService } from '../push/push.service';
import { FcmModule } from '../../../modules/fcm/fcm.module';
import { UsersModule } from '../../../modules/users/users.module';
import redisConfig from '../../../config/redis.config';
import * as redisStore from 'cache-manager-redis-store';
import { LinkStoreToLicenseTask } from './link-store-to-license.task';
// import { PaymentFiscalizationTask } from './payment-fiscalization.task';
import { HttpModule } from '@nestjs/axios';

@Module({
  imports: [
    CacheModule.register({
      store: redisStore,
      host: redisConfig.host,
      port: Number(redisConfig.port),
    }),
    FcmModule,
    UsersModule,
    HttpModule,
  ],
  providers: [
    TasksService,
    SendPushToExpiringSubsTask,
    PushService,
    LinkStoreToLicenseTask,
    // PaymentFiscalizationTask
  ],
})
export class TasksModule {}
