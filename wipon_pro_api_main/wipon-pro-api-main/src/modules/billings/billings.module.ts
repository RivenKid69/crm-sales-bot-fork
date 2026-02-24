import { CacheModule, Module } from '@nestjs/common';
import { UsersModule } from '../users/users.module';
import { BillingsService } from './domain/billings.service';
import { BillingsController } from './presenter/billings.controller';
import { AccountsModule } from '../accounts/accounts.module';
import { SslService } from '../../common/services/ssl/ssl.service';
import * as redisStore from 'cache-manager-redis-store';
import redisConfig from '../../config/redis.config';

@Module({
  providers: [BillingsService, SslService],
  controllers: [BillingsController],
  imports: [
    UsersModule,
    AccountsModule,
    CacheModule.register({
      store: redisStore,
      host: redisConfig.host,
      port: Number(redisConfig.port),
    }),
  ],
})
export class BillingsModule {}
