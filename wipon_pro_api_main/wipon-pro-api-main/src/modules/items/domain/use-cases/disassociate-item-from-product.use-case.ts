import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ItemsRepository } from '../../data/items.repository';
import { UpdateResult } from 'typeorm';

@Injectable()
export class DisassociateItemFromProductUseCase {
  constructor(@InjectRepository(ItemsRepository) private readonly itemsRepository: ItemsRepository) {}

  handle(itemId: number): Promise<UpdateResult> {
    return this.itemsRepository.update(itemId, { product_id: null });
  }
}
