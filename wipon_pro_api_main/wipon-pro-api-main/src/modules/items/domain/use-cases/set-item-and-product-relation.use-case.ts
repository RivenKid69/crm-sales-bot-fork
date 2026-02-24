import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ItemsRepository } from '../../data/items.repository';
import { UpdateResult } from 'typeorm';

@Injectable()
export class SetItemAndProductRelationUseCase {
  constructor(@InjectRepository(ItemsRepository) private readonly itemsRepository: ItemsRepository) {}

  handle(itemId: number, productId: number): Promise<UpdateResult> {
    return this.itemsRepository.update(itemId, { product_id: productId });
  }
}
