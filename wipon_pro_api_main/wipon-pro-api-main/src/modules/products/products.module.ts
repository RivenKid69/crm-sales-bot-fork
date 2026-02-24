import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ProductsRepository } from './data/products.repository';
import { FindOrCreateProductUseCase } from './domain/use-cases/find-or-create-product.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([ProductsRepository])],
  providers: [FindOrCreateProductUseCase],
  exports: [FindOrCreateProductUseCase],
})
export class ProductsModule {}
