import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ItemsRepository } from './data/items.repository';
import { FindOrCreateItemUseCase } from './domain/use-cases/find-or-create-item.use-case';
import { CountItemByExciseCodeUseCase } from './domain/use-cases/count-item-by-excise-code.use-case';
import { SetItemAndProductRelationUseCase } from './domain/use-cases/set-item-and-product-relation.use-case';
import { DisassociateItemFromProductUseCase } from './domain/use-cases/disassociate-item-from-product.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([ItemsRepository])],
  providers: [
    FindOrCreateItemUseCase,
    CountItemByExciseCodeUseCase,
    SetItemAndProductRelationUseCase,
    DisassociateItemFromProductUseCase,
  ],
  exports: [
    FindOrCreateItemUseCase,
    CountItemByExciseCodeUseCase,
    SetItemAndProductRelationUseCase,
    DisassociateItemFromProductUseCase,
  ],
})
export class ItemsModule {}
