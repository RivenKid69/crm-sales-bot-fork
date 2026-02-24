import { forwardRef, Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { StoresRepository } from './data/stores.repository';
import { FindUsersStoreUseCase } from './domain/use-cases/find-users-store.use-case';
import { RegionsModule } from '../regions/regions.module';
import { DgdsModule } from '../dgds/dgds.module';
import { SubscriptionsModule } from '../subscriptions/subscriptions.module';
import { FindUsersStoreByUserIdAndBinUseCase } from './domain/use-cases/find-users-store-by-user-id-and-bin.use-case';
import { StoresService } from './domain/stores.service';
import { StoresController } from './presenter/stores.controller';
import { UsersModule } from '../users/users.module';

@Module({
  controllers: [StoresController],
  imports: [
    TypeOrmModule.forFeature([StoresRepository]),
    RegionsModule,
    DgdsModule,
    forwardRef(() => SubscriptionsModule),
    UsersModule,
  ],
  providers: [StoresService, FindUsersStoreUseCase, FindUsersStoreByUserIdAndBinUseCase],
  exports: [StoresService, FindUsersStoreUseCase, FindUsersStoreByUserIdAndBinUseCase],
})
export class StoresModule {}
