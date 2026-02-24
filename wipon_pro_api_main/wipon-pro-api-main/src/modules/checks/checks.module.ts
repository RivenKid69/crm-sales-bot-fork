import { CacheModule, Module } from '@nestjs/common';
import { ChecksController } from './presenter/checks.controller';
import { SubscriptionsModule } from '../subscriptions/subscriptions.module';
import { ChecksService } from './domain/checks.service';
import { UsersModule } from '../users/users.module';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ChecksRepository } from './data/checks.repository';
import { HttpModule } from '@nestjs/axios';
import { StoresModule } from '../stores/stores.module';
import { ItemsModule } from '../items/items.module';
import { BfAuthenticityModule } from '../bf-authenticity/bf-authenticity.module';
import { ExciseHashesModule } from '../excise-hashes/excise-hashes.module';
import { DoomguyService } from '../../common/services/doomguy/doomguy.service';
import * as redisStore from 'cache-manager-redis-store';
import redisConfig from '../../config/redis.config';

@Module({
  imports: [
    TypeOrmModule.forFeature([ChecksRepository]),
    SubscriptionsModule,
    UsersModule,
    HttpModule,
    StoresModule,
    ItemsModule,
    BfAuthenticityModule,
    ExciseHashesModule,
    CacheModule.register({
      store: redisStore,
      host: redisConfig.host,
      port: Number(redisConfig.port),
    }),
  ],
  providers: [ChecksService, DoomguyService],
  controllers: [ChecksController],
})
export class ChecksModule {}
// export class ChecksModule implements NestModule {
//   configure(consumer: MiddlewareConsumer): any {
//     consumer.apply(CheckSubscriptionMiddleware).forRoutes(ChecksController);
//   }
// } Это логика guarda для проверки subscriptions
