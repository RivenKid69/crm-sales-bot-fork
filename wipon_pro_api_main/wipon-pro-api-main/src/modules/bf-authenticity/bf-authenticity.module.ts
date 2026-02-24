import { CacheModule, Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { ProductsModule } from '../products/products.module';
import { BfAuthenticityService } from './bf-authenticity.service';
import { DoomguyService } from '../../common/services/doomguy/doomguy.service';
import * as redisStore from 'cache-manager-redis-store';
import redisConfig from '../../config/redis.config';

@Module({
  imports: [
    HttpModule,
    ProductsModule,
    CacheModule.register({
      store: redisStore,
      host: redisConfig.host,
      port: Number(redisConfig.port),
    }),
  ],
  providers: [BfAuthenticityService, DoomguyService],
  exports: [BfAuthenticityService],
})
export class BfAuthenticityModule {}
