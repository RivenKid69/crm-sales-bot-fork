import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { StoreTypesRepository } from './data/store-types.repository';
import { FindStoresTypeByNameUseCase } from './domain/use-cases/find-stores-type-by-name.use-case';
import { StoreTypesService } from './domain/store-types.service';
import { StoreTypesController } from './presenter/store-types.controller';

@Module({
  imports: [TypeOrmModule.forFeature([StoreTypesRepository])],
  providers: [StoreTypesService, FindStoresTypeByNameUseCase],
  controllers: [StoreTypesController],
  exports: [FindStoresTypeByNameUseCase],
})
export class StoreTypesModule {}
